"""Focused MuJoCo replay viewer and live Sim2Real dashboard for Class 03/04."""
from __future__ import annotations

import time
from pathlib import Path

import matplotlib
import mujoco
import numpy as np

MOVING_BODY_CANDIDATES = ("Link", "1DOF-B0_1__Link_1", "1DOF-B0_1__XC330-M288-T_1")


def _dashboard(time_s: np.ndarray, hardware: np.ndarray, simulated: np.ndarray, title: str, details: str, output: Path, disabled: bool):
    if disabled:
        return None
    try:
        import PyQt6  # noqa: F401
        matplotlib.use("QtAgg", force=True)
        interactive = True
    except ImportError:
        matplotlib.use("Agg", force=True)
        interactive = False
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    figure = plt.figure(figsize=(12, 6.5), facecolor="#101722")
    grid = figure.add_gridspec(2, 2, width_ratios=(2.5, 1), hspace=.35, wspace=.28)
    position = figure.add_subplot(grid[0, 0])
    residual = figure.add_subplot(grid[1, 0])
    card_axis = figure.add_subplot(grid[:, 1]); card_axis.set_axis_off()
    for axis in (position, residual):
        axis.set_facecolor("#182433"); axis.grid(alpha=.24)
    degrees = np.rad2deg(np.column_stack((hardware, simulated)))
    position.plot(time_s, degrees[:, 0], lw=2.2, color="#4dd0e1", label="V5 hardware measurement")
    position.plot(time_s, degrees[:, 1], lw=2.1, color="#ffb347", label="MuJoCo response")
    position.set(title="Position: hardware vs MuJoCo", ylabel="joint angle (deg)")
    position.legend(loc="upper right", frameon=False)
    error_deg = degrees[:, 1] - degrees[:, 0]
    residual.plot(time_s, error_deg, lw=1.8, color="#ef5350", label="simulation − hardware")
    residual.axhline(0, color="#aeb8c4", lw=.8)
    residual.set(title="Sim2Real residual", xlabel="replay time (s)", ylabel="error (deg)")
    residual.legend(loc="upper right", frameon=False)
    cursor_a = position.axvline(time_s[0], color="white", lw=1.2, alpha=.85)
    cursor_b = residual.axvline(time_s[0], color="white", lw=1.2, alpha=.85)
    rmse = float(np.sqrt(np.mean((simulated - hardware) ** 2)))
    card = card_axis.text(.05, .95, f"{title}\n────────────────\n{details}\n\nLIVE REPLAY\nwhite cursor = shown frame\ncyan = physical V5 record\norange = MuJoCo\nred = residual\n\nRMSE\n{rmse:.4f} rad\n{np.rad2deg(rmse):.2f}°", va="top", family="monospace", fontsize=11.5, linespacing=1.6, bbox={"boxstyle": "round,pad=.9", "facecolor": "#182433", "edgecolor": "#4dd0e1", "alpha": .95})
    if interactive:
        figure.canvas.manager.set_window_title(title + " — live dashboard")
        plt.show(block=False)
    return {"plt": plt, "figure": figure, "cursors": (cursor_a, cursor_b), "interactive": interactive, "output": output, "card": card}


def present(model_path: Path, time_s: np.ndarray, hardware: np.ndarray, simulated: np.ndarray, title: str, details: str, output: Path, *, no_viewer: bool, no_dashboard: bool, playback_speed: float) -> Path | None:
    """Replay a simulated joint trace at wall-clock speed in the B0 platform viewer."""
    dashboard = _dashboard(time_s, hardware, simulated, title, details, output, no_dashboard)
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    body_id = next(
        (candidate for name in MOVING_BODY_CANDIDATES if (candidate := mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)) >= 0),
        -1,
    )
    if body_id < 0:
        raise RuntimeError(f"Could not find a moving B0 body in {model_path}")
    window = None
    if not no_viewer:
        from mujoco import viewer
        window = viewer.launch_passive(model, data)
        window.cam.distance = .32; window.cam.azimuth = 140; window.cam.elevation = -18
    try:
        started = time.monotonic()
        while window is None or window.is_running():
            elapsed = (time.monotonic() - started) * playback_speed
            index = min(int(np.searchsorted(time_s, elapsed, side="right")), len(time_s) - 1)
            data.qpos[0] = simulated[index]
            if index:
                dt = max(time_s[index] - time_s[index - 1], 1e-6)
                data.qvel[0] = (simulated[index] - simulated[index - 1]) / dt
            mujoco.mj_forward(model, data)
            if window:
                window.cam.lookat[:] = data.xpos[body_id]
                window.sync()
            if dashboard:
                for cursor in dashboard["cursors"]:
                    cursor.set_xdata([time_s[index], time_s[index]])
                if dashboard["interactive"]:
                    dashboard["figure"].canvas.draw_idle(); dashboard["figure"].canvas.flush_events()
            if elapsed >= time_s[-1]:
                break
            time.sleep(.01)
    finally:
        if window:
            window.close()
    if dashboard:
        dashboard["figure"].canvas.draw()
        output.parent.mkdir(exist_ok=True)
        dashboard["figure"].savefig(output, dpi=160, facecolor=dashboard["figure"].get_facecolor())
        dashboard["plt"].close(dashboard["figure"])
        return output
    return None
