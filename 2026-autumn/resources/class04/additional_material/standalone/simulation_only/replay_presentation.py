"""Focused MuJoCo replay viewer and live Sim2Real dashboard for Class 03/04."""
from __future__ import annotations

import time
from pathlib import Path

import matplotlib
import mujoco
import numpy as np

XC330_BODY = "1DOF-B0_1__XC330-M288-T_1"


def _dashboard(time_s: np.ndarray, hardware: np.ndarray, simulated: np.ndarray, title: str, details: str, output: Path, disabled: bool, baseline: np.ndarray | None):
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
    hw_deg = np.rad2deg(hardware); sim_deg = np.rad2deg(simulated)
    position.plot(time_s, hw_deg, lw=2.2, color="#4dd0e1", label="V5 hardware measurement")
    if baseline is not None:
        position.plot(time_s, np.rad2deg(baseline), lw=1.7, color="#aeb8c4", ls="--", label="before identification")
    position.plot(time_s, sim_deg, lw=2.1, color="#ffb347", label="after identification")
    position.set(title="Position: physical record vs model", ylabel="joint angle (deg)")
    position.legend(loc="upper right", frameon=False)
    if baseline is not None:
        residual.plot(time_s, np.rad2deg(baseline - hardware), lw=1.4, color="#aeb8c4", ls="--", label="before − hardware")
    residual.plot(time_s, np.rad2deg(simulated - hardware), lw=1.8, color="#ef5350", label="after − hardware")
    residual.axhline(0, color="#aeb8c4", lw=.8)
    residual.set(title="Sim2Real residual", xlabel="replay time (s)", ylabel="error (deg)")
    residual.legend(loc="upper right", frameon=False)
    cursor_a = position.axvline(time_s[0], color="white", lw=1.2, alpha=.85)
    cursor_b = residual.axvline(time_s[0], color="white", lw=1.2, alpha=.85)
    fitted_rmse = float(np.sqrt(np.mean((simulated - hardware) ** 2)))
    before_line = ""
    if baseline is not None:
        baseline_rmse = float(np.sqrt(np.mean((baseline - hardware) ** 2)))
        before_line = f"before: {baseline_rmse:.4f} rad\nafter:  {fitted_rmse:.4f} rad"
    else:
        before_line = f"{fitted_rmse:.4f} rad\n{np.rad2deg(fitted_rmse):.2f}°"
    card_axis.text(.05, .95, f"{title}\n────────────────\n{details}\n\nLIVE REPLAY\nwhite cursor = shown frame\ncyan = physical V5 record\ngray = before identification\norange = after identification\nred = after residual\n\nRMSE\n{before_line}", va="top", family="monospace", fontsize=11.0, linespacing=1.55, bbox={"boxstyle": "round,pad=.9", "facecolor": "#182433", "edgecolor": "#4dd0e1", "alpha": .95})
    if interactive:
        figure.canvas.manager.set_window_title(title + " — live dashboard")
        plt.show(block=False)
    progress = card_axis.text(.05, .14, "REPLAY PROGRESS\npreparing frame", va="top", family="monospace", fontsize=10.5, linespacing=1.45, color="#ffffff")
    return {"plt": plt, "figure": figure, "cursors": (cursor_a, cursor_b), "progress": progress, "interactive": interactive, "output": output}


def present(model_path: Path, time_s: np.ndarray, hardware: np.ndarray, simulated: np.ndarray, title: str, details: str, output: Path, *, no_viewer: bool, no_dashboard: bool, playback_speed: float, baseline: np.ndarray | None = None) -> Path | None:
    """Replay the post-identification response; optionally overlay its baseline on the dashboard."""
    dashboard = _dashboard(time_s, hardware, simulated, title, details, output, no_dashboard, baseline)
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, XC330_BODY)
    if body_id < 0:
        raise RuntimeError(f"Could not find moving XC330 body {XC330_BODY!r}")
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
                error_deg = np.rad2deg(simulated[index] - hardware[index])
                dashboard["progress"].set_text(f"REPLAY PROGRESS\n{time_s[index]:5.2f} / {time_s[-1]:5.2f} s\nframe {index + 1:,} / {len(time_s):,}\ncurrent residual {error_deg:+.2f}°")
                if dashboard["interactive"]:
                    dashboard["figure"].canvas.draw_idle(); dashboard["figure"].canvas.flush_events()
            if elapsed >= time_s[-1]:
                if window:
                    while window.is_running():
                        window.sync()
                        if dashboard and dashboard["interactive"]:
                            dashboard["figure"].canvas.flush_events()
                        time.sleep(.05)
                break
            time.sleep(.01)
    finally:
        if window:
            window.close()
    if dashboard:
        dashboard["figure"].canvas.draw()
        output.parent.mkdir(exist_ok=True)
        dashboard["figure"].savefig(output, dpi=160, facecolor=dashboard["figure"].get_facecolor())
        if dashboard["interactive"]:
            dashboard["plt"].show(block=True)
        dashboard["plt"].close(dashboard["figure"])
        return output
    return None
