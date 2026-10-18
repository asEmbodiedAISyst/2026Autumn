#!/usr/bin/env python3
"""Render the B1 and G1 hardware-fitted MuJoCo scenes used in the paper."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "additional_material" / "models" / "Hardware_Fitted" / "H2"
OUTPUT = ROOT / "additional_material" / "results" / "simulation_views"


def render(config: str) -> None:
    model = mujoco.MjModel.from_xml_path(str((MODELS / f"{config}.xml").resolve()))
    data = mujoco.MjData(model)
    if model.nq:
        data.qpos[0] = 0.0
    mujoco.mj_forward(model, data)

    renderer = mujoco.Renderer(model, height=640, width=960)
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = (-0.08, 0.0, 0.10)
    camera.distance = 0.88
    camera.azimuth = 132.0
    camera.elevation = -18.0
    renderer.update_scene(data, camera=camera)
    image = Image.fromarray(renderer.render())
    renderer.close()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT / f"{config}_H2_hardware_fitted.png")


def main() -> None:
    for config in ("B1", "G1"):
        render(config)
        print(OUTPUT / f"{config}_H2_hardware_fitted.png")


if __name__ == "__main__":
    main()
