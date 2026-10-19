"""Claude as the high-level controller of the pusher tool: the model looks at the phone image and decides the
next motion, the existing executor (software limits, IK, speed limits) carries it out.

Each control step is one API call: the model receives the current phone image with a 5 cm table grid drawn
on it (projected with the known camera pose), the pusher-tip position and what happened so far, and must call
exactly one tool:

* ``move`` -- up to three sequential **relative** moves of the pusher tip in the robot base frame
  (dx forward, dy left, dz up, in cm; optional yaw). Every move is checked (workspace box, reach / joint limits
  via IK, length) and **rejected with a reason** instead of being clipped; nothing after a rejected move runs;
* ``locate`` -- the model gives a pixel; the script returns its table coordinates (the model does the perception,
  the script the geometry);
* ``push`` (``--mode push`` only) -- the model marks the cube and the goal in pixel coordinates, the script
  reprojects them onto the table and performs the whole push with a deterministic primitive (MOKA-style);
* ``done`` -- the model considers the task finished (or impossible).

Works with the simulated arm + simulated phone (``--robot sim``, success is evaluated automatically) and with
the real robot (same code path as ``rollout_real.py``; the operator judges success with the arrow keys).

The API key is read from ``ANTHROPIC_API_KEY``, ``CLAUDE_API_KEY`` or the ``.claude.env`` file at the package root.

Examples::

    uv run python scripts/agent_control.py --robot sim --episodes 5 --model claude-haiku-5-5
    uv run python scripts/agent_control.py --robot sim --episodes 5 --model claude-sonnet-5-5 --mode push
    uv run python scripts/agent_control.py --robot real --can-port can0 --camera-ip 10.42.0.23 --episodes 3
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import queue
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from teleop_real import KEY_LEFT, KEY_RIGHT, KEY_SPACE, Status, add_robot_args, connect, make_env, open_viewer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TASKS = {
    "push_cube": "Push the black cube so that it ends up centred on the green square (the goal area). "
                 "The cube is 4 cm wide; the goal square is 6 cm wide. Success = cube centre within 1.5 cm of the goal centre.",
    "push_t": "Push the black T-shaped block so that it lies exactly on the green T outline on the table.",
}
# Anthropic API list prices, USD per million tokens (input, output, cache read); for the cost report only
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
}
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-5"}  # server-side refusal fallback
GRID_CM = 5
PUSH_HEIGHT = 0.008  # m, rod tip above the table while pushing
SAFE_HEIGHT = 0.07
CUBE_HALF, ROD_RADIUS = 0.02, 0.005
MAX_PUSH_M = 0.06  # one push call travels at most this far: the model re-observes and corrects (open loop otherwise)


# ----------------------------------------------------------------------------- camera geometry
def camera_model(env) -> tuple[np.ndarray, np.ndarray, float]:
    """Phone camera pose (world) and focal length in pixels from the kinematic twin (after tool_pose())."""
    import mujoco

    kin = env.kin
    mujoco.mj_camlight(kin.model, kin.data)  # camera poses are not updated by mj_kinematics alone
    cam = kin.data.cam("phone")
    cid = cam.id
    h = env.camera_hw[0] if hasattr(env, "camera_hw") else 480
    f = (h / 2) / np.tan(np.radians(kin.model.cam_fovy[cid]) / 2)
    return cam.xpos.copy(), cam.xmat.reshape(3, 3).copy(), float(f)


def project(points: np.ndarray, c: np.ndarray, R: np.ndarray, f: float, hw: tuple[int, int]) -> np.ndarray:
    """World points -> pixel (u, v); NaN for points behind the camera. MuJoCo camera: x right, y up, looks -z."""
    pc = (np.asarray(points, dtype=float) - c) @ R  # = R^T (p - c)
    h, w = hw
    with np.errstate(divide="ignore", invalid="ignore"):
        u = w / 2 + f * pc[:, 0] / -pc[:, 2]
        v = h / 2 - f * pc[:, 1] / -pc[:, 2]
    uv = np.stack([u, v], axis=1)
    uv[pc[:, 2] >= -1e-6] = np.nan
    return uv


def pixel_to_table(u: float, v: float, c: np.ndarray, R: np.ndarray, f: float, hw: tuple[int, int],
                   z: float = 0.0) -> np.ndarray | None:
    """Pixel -> point on the plane z = ``z`` (the table); None if the ray does not hit it."""
    h, w = hw
    d_cam = np.array([(u - w / 2) / f, -(v - h / 2) / f, -1.0])
    d = R @ d_cam
    if abs(d[2]) < 1e-6:
        return None
    t = (z - c[2]) / d[2]
    if t <= 0:
        return None
    return c + t * d


def draw_grid(image: np.ndarray, env, tip: np.ndarray) -> np.ndarray:
    """Table grid (every GRID_CM) with labels, the tip projection and the "forward" direction on the image."""
    from PIL import Image, ImageDraw

    c, R, f = camera_model(env)
    hw = image.shape[:2]
    img = Image.fromarray(image).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    step = GRID_CM / 100
    xs = np.arange(0.20, 0.60 + 1e-9, step)
    ys = np.arange(-0.25, 0.25 + 1e-9, step)

    def seg(pts, color, width=1):
        uv = project(np.array(pts), c, R, f, hw)
        for a, b in zip(uv[:-1], uv[1:]):
            if not (np.isnan(a).any() or np.isnan(b).any()):
                d.line([tuple(a), tuple(b)], fill=color, width=width)

    for x in xs:
        seg([(x, y, 0.0) for y in np.linspace(ys[0], ys[-1], 11)], (255, 255, 0, 110), 2 if round(x * 100) % 10 == 0 else 1)
    for y in ys:
        seg([(x, y, 0.0) for x in np.linspace(xs[0], xs[-1], 9)], (0, 255, 255, 110), 2 if round(y * 100) % 10 == 0 else 1)
    # labels at the grid intersections every 10 cm
    for x in xs[::2]:
        for y in ys[::2]:
            uv = project(np.array([[x, y, 0.0]]), c, R, f, hw)[0]
            if not np.isnan(uv).any() and 0 <= uv[0] < hw[1] and 0 <= uv[1] < hw[0]:
                d.text((uv[0] + 2, uv[1] + 2), f"{x * 100:.0f},{y * 100:.0f}", fill=(255, 255, 255, 230))
    # tip projection and the forward (+x) arrow at the tip, on the table plane
    uv = project(np.array([[tip[0], tip[1], 0.0], [tip[0] + 0.05, tip[1], 0.0]]), c, R, f, hw)
    if not np.isnan(uv).any():
        d.ellipse([uv[0][0] - 5, uv[0][1] - 5, uv[0][0] + 5, uv[0][1] + 5], outline=(255, 60, 60, 255), width=2)
        d.line([tuple(uv[0]), tuple(uv[1])], fill=(255, 60, 60, 255), width=2)
        d.text((uv[1][0] + 3, uv[1][1]), "+x (forward)", fill=(255, 60, 60, 255))
    return np.asarray(img)


def jpeg_b64(image: np.ndarray, quality: int = 85) -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(image).save(buf, format="JPEG", quality=quality)
    return base64.standard_b64encode(buf.getvalue()).decode()


MODEL_NAMES = {"claude-haiku-5-5": "Claude Haiku 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5",
               "claude-opus-5-5": "Claude Opus 5.5", "claude-sonnet-5": "Claude Sonnet 5", "claude-opus-5": "Claude Opus 5"}
_FONTS: dict[int, object] = {}


def _font(size: int):
    from PIL import ImageFont

    if size not in _FONTS:
        try:
            _FONTS[size] = ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            _FONTS[size] = ImageFont.load_default()
    return _FONTS[size]


def _describe_call(name: str, inp: dict) -> str:
    """One-line description of a tool call for the video caption."""
    why = str(inp.get("why", inp.get("reason", ""))).strip()
    if name == "move":
        parts = [f"({m.get('dx_cm', 0):+.0f}, {m.get('dy_cm', 0):+.0f}, {m.get('dz_cm', 0):+.0f}) cm" for m in inp.get("moves", [])]
        what = "move " + " -> ".join(parts)
    elif name == "push":
        what = "push cube -> goal"
    elif name == "locate":
        what = f"locate {inp.get('what', '')}"
    elif name == "done":
        what = "done (success)" if inp.get("success") else "done (give up)"
    else:
        what = name
    return what + (f'   "{why}"' if why else "")


def _with_banner(image: np.ndarray, header: str, caption: str, height: int = 96) -> np.ndarray:
    """Dark banner above ``image`` with the episode header and the current decision (wrapped to 2 lines)."""
    from PIL import Image, ImageDraw

    w = image.shape[1]
    banner = Image.new("RGB", (w, height), (22, 24, 28))
    d = ImageDraw.Draw(banner)
    d.text((14, 8), header, fill=(255, 210, 90), font=_font(22))
    f = _font(19)
    words, lines, cur = caption.split(" "), [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=f) > w - 28 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    lines.append(cur)
    for i, line in enumerate(lines[:2]):
        d.text((14, 40 + 25 * i), line if i == 0 or len(lines) <= 2 else line + " ...", fill=(235, 235, 235), font=f)
    return np.concatenate([np.asarray(banner), image], axis=0)


# ----------------------------------------------------------------------------- robot primitives
class Executor:
    """Runs motion primitives on a RealToolPushEnv (sim or real), checking every target before moving."""

    def __init__(self, env, viewer=None, view_sim=None, max_move_cm: float = 15.0, record: bool = False) -> None:
        self.env = env
        self.viewer, self.view_sim = viewer, view_sim
        # optional video: phone view | third-person view of the simulated scene, one frame per control tick
        self.record, self.frames, self._renderer, self._cam = record, [], None, None
        self.header, self.caption = "", ""  # video banner: episode header and the current decision
        self.keys: queue.Queue | None = None  # real robot: Space pauses mid-motion, arrows end the episode
        self.operator_end: bool | None = None
        self.mocap_id = view_sim.model.body("ee_target").mocapid[0] if view_sim is not None else None
        self.max_move_cm = max_move_cm
        # pushing height of the rod tip: never below the allowed minimum height (+2 mm margin)
        self.push_height = max(PUSH_HEIGHT, env.ctrl.limits.z[0] + 0.002)
        self.last_obs, self.last_info = None, {"is_success": False, "image_age": 0.0}
        self.success = False

    def tip(self) -> np.ndarray:
        return self.env.ctrl.target_pos.copy()

    def check_target(self, p: np.ndarray, R: np.ndarray | None = None) -> str | None:
        """Reason the target is not acceptable, or None."""
        lim = self.env.ctrl.limits
        for name, val, (lo, hi) in (("x", p[0], lim.x), ("y", p[1], lim.y), ("z", p[2], lim.z)):
            if not lo <= val <= hi:
                return f"{name} = {val * 100:.1f} cm is outside the allowed range {lo * 100:.0f}..{hi * 100:.0f} cm"
        R = self.env.ctrl.target_rot if R is None else R
        res = self.env.ik.solve(p, R, self.env.q_cmd, max_iters=100)
        if not res.success:
            return "the arm cannot reach that position (joint limits)"
        return None

    def goto(self, p: np.ndarray, R: np.ndarray | None = None, timeout_s: float = 6.0, tol: float = 0.004) -> dict:
        """Move the rod tip to ``p`` (world) at the speed limit; returns the final info dict."""
        R = self.env.ctrl.target_rot if R is None else R
        t0 = time.monotonic()
        info = self.last_info
        paused = False
        while time.monotonic() - t0 < timeout_s or paused:
            tick = time.perf_counter()
            if self.keys is not None:
                while not self.keys.empty():
                    k = self.keys.get_nowait()
                    if k == KEY_SPACE:
                        paused = not paused
                        print("\npaused (Space continues)" if paused else "\ncontinued")
                    elif k in (KEY_LEFT, KEY_RIGHT):
                        self.operator_end = k == KEY_RIGHT
                if self.operator_end is not None:
                    break
                if paused:
                    self.env.hold()
                    if self.viewer is not None:
                        self.viewer.sync()
                    time.sleep(1.0 / self.env.fps)
                    continue
            obs, _, _, _, info = self.env.step(self.env.action_to(p, R))
            self.last_obs, self.last_info = obs, info
            if self.record:
                self.frames.append(self._frame(obs))
            if self.view_sim is not None:
                self.view_sim.data.mocap_pos[self.mocap_id] = self.env.ctrl.target_pos
            if self.viewer is not None:
                self.viewer.sync()
            if info.get("is_success"):
                self.success = True
                break
            meas, _ = self.env.kin.tcp_pose()
            if np.linalg.norm(meas - p) < tol and np.linalg.norm(self.env.ctrl.target_pos - p) < 1e-4:
                break
            dt = time.perf_counter() - tick
            if self.env.arm.__class__.__name__ != "SimArm" and dt < 1.0 / self.env.fps:
                time.sleep(1.0 / self.env.fps - dt)
        return info

    def _frame(self, obs) -> np.ndarray:
        """Video frame: banner (header + current decision) over the grid-annotated phone view (what the model sees)
        next to a third-person render of the simulated scene."""
        import mujoco

        phone = obs["pixels"]["phone"]
        if phone is None:
            phone = np.zeros((480, 640, 3), np.uint8)
        else:
            phone = draw_grid(phone, self.env, self.tip())
        if not hasattr(self.env.arm, "sim"):
            return _with_banner(phone, self.header, self.caption)
        sim = self.env.arm.sim
        if self._renderer is None:
            self._renderer = mujoco.Renderer(sim.model, 480, 640)
            self._cam = mujoco.MjvCamera()
            self._cam.lookat[:] = (0.38, 0.0, 0.03)
            self._cam.distance, self._cam.azimuth, self._cam.elevation = 0.8, 150, -35
            self._opt = mujoco.MjvOption()
            self._opt.geomgroup[1] = 0
        self._renderer.update_scene(sim.data, self._cam, self._opt)
        return _with_banner(np.concatenate([phone, self._renderer.render()], axis=1), self.header, self.caption)

    def hold(self, caption: str, seconds: float) -> None:
        """Freeze the current view for ``seconds`` of video with a caption (the decision moment)."""
        if not self.record or self.last_obs is None:
            return
        self.caption = caption
        frame = self._frame(self.last_obs)
        self.frames.extend([frame] * int(seconds * self.env.fps))

    def move_relative(self, moves: list[dict]) -> tuple[str, bool]:
        """Execute up to three relative moves; stops at the first rejected one. Returns (report, success)."""
        from rebot_sim.pose import rot_z

        lines = []
        if self.operator_end is not None:
            return "episode ended by the operator", self.success
        if not moves:
            return "no moves given", self.success
        if len(moves) > 3:
            lines.append(f"only the first 3 of {len(moves)} moves are executed")
            moves = moves[:3]
        for i, mv in enumerate(moves):
            d = np.array([mv.get("dx_cm", 0.0), mv.get("dy_cm", 0.0), mv.get("dz_cm", 0.0)], dtype=float) / 100
            if np.linalg.norm(d) > self.max_move_cm / 100:
                lines.append(f"move {i + 1} rejected: longer than {self.max_move_cm:.0f} cm")
                break
            target = self.tip() + d
            R = rot_z(np.radians(float(mv.get("dyaw_deg", 0.0)))) @ self.env.ctrl.target_rot
            why = self.check_target(target, R)
            if why:
                lines.append(f"move {i + 1} rejected: {why}; the tip stays at ({self.tip()[0] * 100:.1f}, "
                             f"{self.tip()[1] * 100:.1f}, {self.tip()[2] * 100:.1f}) cm")
                break
            info = self.goto(target, R)
            p = self.tip()
            lines.append(f"move {i + 1} done: tip at ({p[0] * 100:.1f}, {p[1] * 100:.1f}, {p[2] * 100:.1f}) cm"
                         + ("" if info.get("ik_ok", True) else " (partially: reach limit)"))
            if self.success:
                lines.append("TASK SUCCESS detected by the simulator")
                break
        return "\n".join(lines), self.success

    def push(self, cube_xy: np.ndarray, goal_xy: np.ndarray) -> str:
        """Deterministic push: approach behind the cube, descend, push along the cube->goal line, retreat, lift."""
        u = goal_xy - cube_xy
        dist = float(np.linalg.norm(u))
        if dist < 0.01:
            return "cube and goal are at the same place: nothing to push"
        u /= dist
        standoff = CUBE_HALF + ROD_RADIUS + 0.015
        approach = np.r_[cube_xy - u * standoff, SAFE_HEIGHT]
        travel = min(dist, MAX_PUSH_M)  # cube displacement this call
        end = np.r_[cube_xy + u * travel - u * (CUBE_HALF + ROD_RADIUS), self.push_height]
        for name, p in (("lift", np.r_[self.tip()[:2], SAFE_HEIGHT]), ("approach", approach),
                        ("descend", np.r_[approach[:2], self.push_height]), ("push", end)):
            why = self.check_target(p)
            if why:
                return f"push aborted at '{name}': {why}"
            self.goto(p, timeout_s=10.0)
            if self.success:
                return "TASK SUCCESS detected by the simulator"
            if self.operator_end is not None:
                return "episode ended by the operator"
        back = np.r_[end[:2] - u * 0.02, self.push_height]
        self.goto(back)
        self.goto(np.r_[back[:2], SAFE_HEIGHT])
        p = self.tip()
        note = "" if travel >= dist - 1e-6 else f" (pushed {travel * 100:.0f} of {dist * 100:.0f} cm; check the image and push again)"
        return f"push done{note}; tip lifted at ({p[0] * 100:.1f}, {p[1] * 100:.1f}, {p[2] * 100:.1f}) cm"


# ----------------------------------------------------------------------------- the agent
def load_api_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    if os.environ.get("CLAUDE_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = os.environ["CLAUDE_API_KEY"]
        return
    env_file = ROOT / ".claude.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"):
                    os.environ["ANTHROPIC_API_KEY"] = v.strip().strip('"').strip("'")
                    return
    sys.exit("no API key found: set ANTHROPIC_API_KEY or CLAUDE_API_KEY, or write CLAUDE_API_KEY=... in .claude.env at the package root")


def tool_specs(mode: str) -> list[dict]:
    move = {
        "name": "move",
        "description": "Move the rod tip by small relative displacements, up to 3 moves executed in order. "
                       "Frame: x = forward (away from the robot base, up in the image), y = left, z = up; units cm. "
                       "Each move is checked before it runs (allowed box, reach); a rejected move and everything "
                       "after it are skipped and the reason is returned. Keep single moves <= 15 cm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "moves": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dx_cm": {"type": "number", "description": "forward (+) / backward (-)"},
                            "dy_cm": {"type": "number", "description": "left (+) / right (-)"},
                            "dz_cm": {"type": "number", "description": "up (+) / down (-)"},
                            "dyaw_deg": {"type": "number", "description": "turn the tool left (+) / right (-), usually 0"},
                        },
                        "required": ["dx_cm", "dy_cm", "dz_cm", "dyaw_deg"],
                        "additionalProperties": False,
                    },
                },
                "why": {"type": "string", "description": "one short sentence: what you see and what this move is for"},
            },
            "required": ["moves", "why"],
            "additionalProperties": False,
        },
        "strict": True,
    }
    push = {
        "name": "push",
        "description": "Push the cube towards the goal: give the pixel coordinates (u right, v down, image is 512x384) "
                       "of the CUBE CENTRE and of the GOAL CENTRE; the robot approaches from behind the cube and pushes "
                       "it along the straight line to the goal (at most 6 cm per call), then lifts. Check the image and "
                       "call it again until the cube sits on the goal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cube_px": {"type": "array", "items": {"type": "number"}, "description": "[u, v] of the cube centre"},
                "goal_px": {"type": "array", "items": {"type": "number"}, "description": "[u, v] of the goal centre"},
                "why": {"type": "string"},
            },
            "required": ["cube_px", "goal_px", "why"],
            "additionalProperties": False,
        },
        "strict": True,
    }
    locate = {
        "name": "locate",
        "description": "Convert a pixel position (u right, v down, image 512x384) into table coordinates in cm. Use it "
                       "to find exactly where the cube and the goal are before planning moves. The point is assumed to "
                       "lie on the table (for the cube, point at the centre of its top face).",
        "input_schema": {
            "type": "object",
            "properties": {"u": {"type": "number"}, "v": {"type": "number"},
                           "what": {"type": "string", "description": "cube / goal / other"}},
            "required": ["u", "v", "what"],
            "additionalProperties": False,
        },
        "strict": True,
    }
    done = {
        "name": "done",
        "description": "Finish the episode: the task is complete (success) or cannot be completed.",
        "input_schema": {
            "type": "object",
            "properties": {"success": {"type": "boolean"}, "reason": {"type": "string"}},
            "required": ["success", "reason"],
            "additionalProperties": False,
        },
        "strict": True,
    }
    return [locate, move, push, done] if mode == "push" else [locate, move, done]


def system_prompt(task_text: str, mode: str, lim) -> str:
    return f"""You control the rod tip of a small robot arm that pushes objects on a table. You see the table through a phone camera mounted on the tool, looking down: the rod is the grey bar in the lower middle of the image, its tip is the red circle. Image up = forward (+x, away from the robot base), image left = +y.

Task: {task_text}

The image has a 5 cm grid drawn on the table plane (yellow lines = constant x, cyan lines = constant y; labels "x,y" in cm at every 10 cm). Use it to estimate distances. The rod tip position in cm is given in the text.

How to plan: the red circle is the rod tip projected onto the table and the red arrow points forward (+x). Read the cube and goal positions from the grid labels or call `locate` on their pixels; then the required displacement is (target - tip) in cm. Moves are relative to the current tip position, which is given in the text every turn.

Rules:
- Call exactly one tool per turn. Think briefly; do not write long explanations.
- Pushing works only with the tip low: z about {max(0.8, lim.z[0] * 100 + 0.2):.1f}-{max(1.5, lim.z[0] * 100 + 0.8):.1f} cm when touching the cube (the cube is 4 cm tall). Move above objects at z >= 5 cm first, then descend behind the cube (on the side opposite to the goal), then push straight towards the goal in a few moves, checking the image after each.
- Allowed tip box: x {lim.x[0] * 100:.0f}..{lim.x[1] * 100:.0f} cm, y {lim.y[0] * 100:.0f}..{lim.y[1] * 100:.0f} cm, z {lim.z[0] * 100:.1f}..{lim.z[1] * 100:.0f} cm. Rejected moves are reported; adjust and continue.
- Do not push the cube past the goal; if it overshoots or rotates, go around and push it back.
- When the cube sits on the goal, lift the tip (z 5 cm) and call done(success=true).
""" + ("- The 'push' tool does the whole push for you from pixel coordinates; prefer it, then verify with the image.\n" if mode == "push" else "")


def run_episode(client, model: str, mode: str, executor: Executor, env, task_text: str, args, log_dir: Path | None,
                ep: int, keys: queue.Queue | None) -> dict:
    import anthropic

    tools = tool_specs(mode)
    system = [{"type": "text", "text": system_prompt(task_text, mode, env.ctrl.limits), "cache_control": {"type": "ephemeral"}}]
    messages: list[dict] = []
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    transcript = []
    hw = executor.last_obs["pixels"]["phone"].shape[:2]
    env.camera_hw = hw

    def observation_blocks(note: str) -> list[dict]:
        obs = executor.last_obs
        image = obs["pixels"]["phone"]
        if image is None:
            return [{"type": "text", "text": note + "\n(no camera image available)"}]
        env.tool_pose()  # refresh the twin so the camera pose is current
        annotated = draw_grid(image, env, executor.tip())
        if log_dir is not None:
            from PIL import Image

            Image.fromarray(annotated).save(log_dir / f"ep{ep:02d}_step{len(transcript):02d}.jpg", quality=85)
        p = executor.tip()
        text = f"{note}\nRod tip now at x={p[0] * 100:.1f}, y={p[1] * 100:.1f}, z={p[2] * 100:.1f} cm."
        from PIL import Image as _Image

        small = np.asarray(_Image.fromarray(annotated).resize((512, 384), _Image.LANCZOS))  # fewer image tokens
        return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": jpeg_b64(small)}},
                {"type": "text", "text": text}]

    messages.append({"role": "user", "content": observation_blocks("Episode start. Decide the first action.")})
    result = {"success": False, "calls": 0, "ended_by": "max_calls"}
    nudges = 0
    for call in range(args.max_calls):
        if keys is not None:  # real robot: operator can end the episode (also mid-motion, see Executor.goto)
            while not keys.empty():
                k = keys.get_nowait()
                if k == KEY_RIGHT:
                    executor.operator_end = True
                elif k == KEY_LEFT:
                    executor.operator_end = False
            if executor.operator_end is not None:
                result.update(success=executor.operator_end, ended_by="operator")
                break
        kwargs = dict(model=model, max_tokens=4000, system=system, tools=tools, messages=messages,
                      output_config={"effort": args.effort})
        try:
            if model in FALLBACK_MODELS:
                resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
            else:
                resp = client.messages.create(**kwargs)
        except anthropic.RateLimitError as e:
            wait = int(e.response.headers.get("retry-after", "20"))
            print(f"\nrate limited: retry in {wait} s"); time.sleep(wait); continue
        except anthropic.APIStatusError as e:
            print(f"\nAPI error {e.status_code}: {e.message}"); result["ended_by"] = "api_error"; break
        u = resp.usage
        usage["input"] += u.input_tokens; usage["output"] += u.output_tokens
        usage["cache_read"] += u.cache_read_input_tokens or 0; usage["cache_write"] += u.cache_creation_input_tokens or 0
        result["calls"] = call + 1
        if resp.stop_reason == "refusal":
            print("\nthe model refused the request"); result["ended_by"] = "refusal"; break
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            nudges += 1
            text = " ".join(b.text for b in resp.content if b.type == "text")[:200]
            transcript.append({"call": call, "text": text})
            if nudges > 2:
                result["ended_by"] = "no_tool_call"; break
            messages.append({"role": "user", "content": "Respond with exactly one tool call."})
            continue
        results = []
        episode_over = False
        for tu in tool_uses:
            inp = tu.input
            executor.caption = f"call {call + 1}  {_describe_call(tu.name, inp)}"
            executor.hold(executor.caption, 1.5)
            if tu.name == "done":
                claimed = bool(inp.get("success"))
                if env.sim_task is not None:  # simulation: the simulator decides, not the model's claim
                    actual = bool(env.sim_task.evaluate(env.arm.sim).success)
                    result.update(success=actual, ended_by="done" if actual == claimed else "done_false_claim")
                else:
                    result.update(success=claimed, ended_by="done")
                result["claimed_success"] = claimed
                transcript.append({"call": call, "tool": "done", "input": inp})
                episode_over = True
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "ok"})
                continue
            if tu.name == "locate":
                c, R, f = camera_model(env)
                z = CUBE_HALF if "cube" in str(inp.get("what", "")).lower() else 0.0
                pt = pixel_to_table(float(inp["u"]) * hw[1] / 512, float(inp["v"]) * hw[0] / 384, c, R, f, hw, z=z)
                tip = executor.tip()
                report = ("that pixel does not hit the table" if pt is None else
                          f"{inp.get('what', 'point')} at x={pt[0] * 100:.1f}, y={pt[1] * 100:.1f} cm; from the tip that is "
                          f"dx={(pt[0] - tip[0]) * 100:+.1f}, dy={(pt[1] - tip[1]) * 100:+.1f} cm")
                transcript.append({"call": call, "tool": "locate", "input": inp, "report": report})
                executor.hold(f"call {call + 1}  locate {inp.get('what', '')}: {report.split(';')[0]}", 1.0)
                print(f"ep {ep + 1} call {call + 1}: locate {inp} -> {report}")
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": report})
                continue
            if tu.name == "move":
                report, success = executor.move_relative(inp["moves"])
            elif tu.name == "push":
                c, R, f = camera_model(env)
                ok_px = len(inp.get("cube_px", [])) == 2 and len(inp.get("goal_px", [])) == 2
                sx, sy = hw[1] / 512, hw[0] / 384  # the model sees a 512x384 copy
                cube = pixel_to_table(inp["cube_px"][0] * sx, inp["cube_px"][1] * sy, c, R, f, hw, z=CUBE_HALF) if ok_px else None
                goal = pixel_to_table(inp["goal_px"][0] * sx, inp["goal_px"][1] * sy, c, R, f, hw, z=0.0) if ok_px else None
                if cube is None or goal is None:
                    report, success = "could not project those pixels onto the table", False
                else:
                    report = (f"cube at ({cube[0] * 100:.1f}, {cube[1] * 100:.1f}) cm, goal at ({goal[0] * 100:.1f}, "
                              f"{goal[1] * 100:.1f}) cm. " + executor.push(cube[:2], goal[:2]))
                    success = executor.success
            else:
                report, success = f"unknown tool {tu.name}", False
            transcript.append({"call": call, "tool": tu.name, "input": inp, "report": report})
            status_line = f"ep {ep + 1} call {call + 1}: {tu.name} {json.dumps(inp, ensure_ascii=False)[:90]} -> {report.splitlines()[-1][:70]}"
            print(status_line)
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": observation_blocks(report)})
            if success:
                result.update(success=True, ended_by="sim_success")
                episode_over = True
        if episode_over:
            break
        messages.append({"role": "user", "content": results})
    if executor.record:
        verdict = "SUCCESS - cube on the goal" if result["success"] else f"not completed ({result['ended_by']})"
        executor.hold(f"{verdict}   |   {result['calls']} Claude calls", 2.5)
    price = PRICES.get(model, (0, 0, 0))
    result["cost_usd"] = (usage["input"] * price[0] + usage["output"] * price[1] + usage["cache_read"] * price[2]
                          + usage["cache_write"] * price[0] * 1.25) / 1e6
    result["usage"] = usage
    if log_dir is not None:
        (log_dir / f"ep{ep:02d}.json").write_text(json.dumps({"result": result, "transcript": transcript}, indent=1, ensure_ascii=False))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_robot_args(ap)
    ap.add_argument("--model", default="claude-sonnet-5-5", help="Claude model id (claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5, ...)")
    ap.add_argument("--mode", choices=["step", "push"], default="step", help="step: the model gives relative moves step by step; push: the model marks the cube and goal pixels and the script does the whole push")
    ap.add_argument("--effort", choices=["low", "medium", "high"], default="medium")
    ap.add_argument("--episodes", type=int, default=5)
    ap.add_argument("--max-calls", type=int, default=25, help="maximum number of API calls per episode")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log-dir", default=None, help="directory for the grid image of every step and the conversation log")
    ap.add_argument("--video", action="store_true", help="record a video of every episode to --log-dir (phone view | third-person view)")
    ap.add_argument("--push-height", type=float, default=PUSH_HEIGHT,
                    help="height of the pusher tip above the table during the push primitive, m (default 0.008; never below --z-min + 0.002)")
    ap.add_argument("--auto", action="store_true", help="real robot: start at once without Space (the simulation always starts at once)")
    args = ap.parse_args()
    args.action_mode = "episode"
    load_api_key()
    import anthropic

    client = anthropic.Anthropic()
    env = make_env(args)
    task_text = TASKS[args.task]
    log_dir = Path(args.log_dir) if args.log_dir else None
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
    keys: queue.Queue[int] = queue.Queue()
    viewer = None
    results = []
    try:
        connect(env, args)
        viewer, view_sim = open_viewer(env, keys, not args.no_viewer)
        executor = Executor(env, viewer, view_sim, record=args.video and log_dir is not None)
        executor.push_height = max(args.push_height, env.ctrl.limits.z[0] + 0.002)
        print(f"lowest pusher tip height {env.ctrl.limits.z[0] * 100:.1f} cm, push height {executor.push_height * 100:.1f} cm")
        for ep in range(args.episodes):
            executor.frames = []
            print(f"\n== episode {ep + 1}/{args.episodes}: the arm moves to the start pose")
            obs, info = env.reset(seed=args.seed + ep)
            executor.last_obs, executor.last_info, executor.success = obs, info, False
            executor.operator_end = None
            executor.keys = keys if args.robot == "real" else None
            executor.header = (f"{MODEL_NAMES.get(args.model, args.model)}  |  mode: {args.mode}  |  "
                               f"{'simulation' if args.robot == 'sim' else 'real robot'}  |  episode {ep + 1}")
            executor.caption = "Task: " + TASKS[args.task].split(".")[0]
            if args.robot == "real" and not args.auto:
                print("Place the objects, then press Space in the MuJoCo window to start; Right = end as success, Left = end as failure")
                while True:
                    k = keys.get()
                    if k == KEY_SPACE:
                        break
            t0 = time.monotonic()
            r = run_episode(client, args.model, args.mode, executor, env, task_text, args, log_dir, ep,
                            keys if args.robot == "real" else None)
            r["seconds"] = time.monotonic() - t0
            results.append(r)
            if executor.record and executor.frames:
                from eval_policy import save_video

                save_video(executor.frames, log_dir / f"ep{ep:02d}.mp4", env.fps)
                print(f"video: {log_dir / f'ep{ep:02d}.mp4'}")
            print(f"[episode {ep + 1}] {'success' if r['success'] else 'failure'} ({r['ended_by']}, {r['calls']} calls, "
                  f"{r['seconds']:.0f} s, ${r['cost_usd']:.3f})")
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        if results:
            n = len(results)
            print(f"\n{args.model} {args.mode}: success rate {sum(r['success'] for r in results)}/{n}, mean "
                  f"{np.mean([r['calls'] for r in results]):.1f} calls per episode, total cost ${sum(r['cost_usd'] for r in results):.3f}")
            if log_dir:
                (log_dir / "summary.json").write_text(json.dumps({"model": args.model, "mode": args.mode, "episodes": results}, indent=1))
        print("the arm returns to its zero pose; torque off...")
        env.close()
        if viewer is not None:
            from rebot_sim.viewer_utils import close_viewer

            close_viewer(viewer)


if __name__ == "__main__":
    main()
