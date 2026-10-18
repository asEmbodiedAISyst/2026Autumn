"""Render the four RS06 fixture models (M0, B0, B1, G1) and the gravity torque of each fixture.

Run from this folder (``rs06_fixtures/``) with mujoco, numpy and matplotlib installed::

    MUJOCO_GL=egl python render_rs06_models.py --out figures

Outputs:

* ``figures/rs06_model_loads.png``: the four MJCF files loaded in MuJoCo, same camera, joint at 0 rad, without the
  ground plane of the export;
* ``figures/rs06_gravity_torque.png``: the gravity torque about the joint over the joint range, computed by
  MuJoCo (``qfrc_bias`` at zero velocity) for each fixture.

The script only loads and renders the models; it runs no experiment.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURES = {
    "M0": "motor only",
    "B0": "balanced link",
    "B1": "balanced link and both payloads",
    "G1": "one-sided payload",
}


def render(model: mujoco.MjModel, data: mujoco.MjData, size=(640, 480)) -> np.ndarray:
    """The fixture alone on a white background: the ground plane of the export is hidden."""
    for g in range(model.ngeom):
        if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE:
            model.geom_rgba[g, 3] = 0.0
    renderer = mujoco.Renderer(model, size[1], size[0])
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = [0.0, 0.0, 0.03]
    cam.distance, cam.azimuth, cam.elevation = 0.55, 135.0, -30.0
    renderer.update_scene(data, cam)
    img = renderer.render().copy()
    renderer.enable_depth_rendering()
    renderer.update_scene(data, cam)
    depth = renderer.render()
    renderer.close()
    img[depth >= 0.999 * depth.max()] = 255  # empty background (far plane) -> white
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="figures")
    args = ap.parse_args()
    out = HERE / args.out
    out.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(9, 7), dpi=150)
    torque = {}
    for ax, (fid, label) in zip(axes.ravel(), FIXTURES.items()):
        model = mujoco.MjModel.from_xml_path(str(HERE / "model-sources" / f"{fid}.xml"))
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        ax.imshow(render(model, data))
        ax.set_title(f"{fid}: {label}", fontsize=11)
        ax.axis("off")
        lo, hi = model.jnt_range[0]
        qs = np.linspace(lo, hi, 111)
        tau = []
        for q in qs:
            data.qpos[0], data.qvel[0] = q, 0.0
            mujoco.mj_forward(model, data)
            tau.append(data.qfrc_bias[0])
        torque[fid] = (qs, np.array(tau))
    fig.tight_layout()
    fig.savefig(out / "rs06_model_loads.png", facecolor="white")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150)
    for fid, (qs, tau) in torque.items():
        ax.plot(qs, tau, label=fid)
    ax.set_xlabel("joint angle q (rad)")
    ax.set_ylabel("gravity torque (N m)")
    ax.grid(alpha=0.3)
    ax.legend(title="fixture")
    fig.tight_layout()
    fig.savefig(out / "rs06_gravity_torque.png", facecolor="white")
    print("wrote", out / "rs06_model_loads.png", out / "rs06_gravity_torque.png")
    for fid, (qs, tau) in torque.items():
        print(f"{fid}: max |gravity torque| {np.abs(tau).max():.3f} N m over q in [{qs[0]:.2f}, {qs[-1]:.2f}] rad")


if __name__ == "__main__":
    main()
