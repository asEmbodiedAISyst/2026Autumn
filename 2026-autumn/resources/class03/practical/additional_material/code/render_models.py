#!/usr/bin/env python3
"""Render reproducible inspection images for the five Class 03 MJCF files."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
from PIL import Image


CONFIGS = ("M0", "B0", "B1", "B2", "G1")



def render_one(xml_path: Path, output_path: Path) -> None:
    model = mujoco.MjModel.from_xml_path(str(xml_path.resolve()))
    data = mujoco.MjData(model)
    if model.nq:
        data.qpos[0] = 0.0
    mujoco.mj_forward(model, data)

    renderer = mujoco.Renderer(model, height=700, width=1000)
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = (-0.08, 0.0, 0.10)
    camera.distance = 0.88
    camera.azimuth = 132.0
    camera.elevation = -18.0
    renderer.update_scene(data, camera=camera)
    image = Image.fromarray(renderer.render())
    renderer.close()

    image.save(output_path, quality=95)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, default=root / "models")
    parser.add_argument("--output", type=Path, default=root / "results" / "model_loads")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    for config in CONFIGS:
        xml_path = args.models / f"1DOF-{config}.xml"
        output_path = args.output / f"{config}_model_loaded.png"
        render_one(xml_path, output_path)
        print(output_path)


if __name__ == "__main__":
    main()
