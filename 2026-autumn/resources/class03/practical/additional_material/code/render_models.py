#!/usr/bin/env python3
"""Render the five source MJCFs on the complete platform with its laptop."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
from PIL import Image, ImageDraw, ImageFont


CONFIGS = ("M0", "B0", "B1", "B2", "G1")
LAPTOP_BODY = "Lenovo-PC_1__Screen-7_1"
PLATFORM_MODEL = (
    "AsBrainBox-Platform---XC330-B0"
    "/AsBrainBox-Platform---XC330-B0_mujoco_compatible.xml"
)


def complete_platform_laptop(
    platform_xml: Path,
) -> tuple[Path, tuple[float, ...], tuple[float, ...]]:
    """Return the laptop mesh and its world pose from the full platform export."""
    model = mujoco.MjModel.from_xml_path(str(platform_xml.resolve()))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, LAPTOP_BODY)
    if body_id < 0:
        raise ValueError(f"Laptop body {LAPTOP_BODY!r} is missing from {platform_xml}")

    tree = ET.parse(platform_xml)
    mesh = tree.getroot().find(f"./asset/mesh[@name='{LAPTOP_BODY}']")
    if mesh is None or not mesh.get("file"):
        raise ValueError(f"Laptop mesh {LAPTOP_BODY!r} is missing from {platform_xml}")
    mesh_path = (platform_xml.parent / mesh.get("file")).resolve()
    return (
        mesh_path,
        tuple(float(value) for value in data.xpos[body_id]),
        tuple(float(value) for value in data.xquat[body_id]),
    )


def platform_complete_scene(
    xml_path: Path,
    laptop: tuple[Path, tuple[float, ...], tuple[float, ...]],
) -> ET.ElementTree:
    """Add the full-export laptop to one validated fixture-and-platform MJCF."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    asset = root.find("asset")
    worldbody = root.find("worldbody")
    if asset is None or worldbody is None:
        raise ValueError(f"Incomplete MJCF structure: {xml_path}")

    for file_asset in asset.findall("./*"):
        file_name = file_asset.get("file")
        if file_name:
            file_asset.set("file", str((xml_path.parent / file_name).resolve()))

    mesh_path, position, quaternion = laptop
    ET.SubElement(
        asset,
        "texture",
        name="class03_sky",
        type="skybox",
        builtin="gradient",
        rgb1="0.82 0.90 0.98",
        rgb2="0.34 0.48 0.64",
        width="512",
        height="3072",
    )
    ET.SubElement(
        asset,
        "mesh",
        name="class03_laptop",
        file=str(mesh_path),
        scale="0.001 0.001 0.001",
    )
    laptop_body = ET.SubElement(
        worldbody,
        "body",
        name="class03_laptop",
        pos=" ".join(f"{value:.12g}" for value in position),
        quat=" ".join(f"{value:.12g}" for value in quaternion),
    )
    ET.SubElement(
        laptop_body,
        "geom",
        name="class03_laptop_visual",
        type="mesh",
        mesh="class03_laptop",
        rgba="0.24 0.26 0.29 1",
        contype="0",
        conaffinity="0",
        group="2",
    )
    return tree


def render_one(
    xml_path: Path,
    output_path: Path,
    laptop: tuple[Path, tuple[float, ...], tuple[float, ...]],
) -> None:
    scene = platform_complete_scene(xml_path, laptop)
    with tempfile.NamedTemporaryFile(suffix=".xml") as temporary_xml:
        scene.write(temporary_xml.name, encoding="unicode")
        model = mujoco.MjModel.from_xml_path(temporary_xml.name)
    data = mujoco.MjData(model)
    if model.nq:
        data.qpos[0] = 0.0
    mujoco.mj_forward(model, data)

    renderer = mujoco.Renderer(model, height=700, width=1000)
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = (-0.20, -0.04, 0.20)
    camera.distance = 1.08
    camera.azimuth = 125.0
    camera.elevation = -15.0
    renderer.update_scene(data, camera=camera)
    image = Image.fromarray(renderer.render())
    renderer.close()

    image.save(output_path, quality=95)


def make_grid(rendered: list[tuple[str, Path]], output_path: Path) -> None:
    """Place equal-scale simulation views in a labelled comparison figure."""
    panel_size = (700, 490)
    label_height = 65
    canvas = Image.new("RGB", (1480, 3 * (panel_size[1] + label_height)), "white")
    draw = ImageDraw.Draw(canvas)
    label_font = ImageFont.load_default(size=32)
    positions = ((20, 0), (760, 0), (20, 555), (760, 555), (390, 1110))
    for index, (config, path) in enumerate(rendered):
        panel = Image.open(path).convert("RGB").resize(panel_size, Image.Resampling.LANCZOS)
        x, y = positions[index]
        canvas.paste(panel, (x, y))
        draw.rectangle(
            (x, y, x + panel_size[0] - 1, y + panel_size[1]),
            outline="#53657A",
            width=2,
        )
        box = draw.textbbox((0, 0), config, font=label_font)
        draw.text(
            (x + (panel_size[0] - (box[2] - box[0])) / 2, y + panel_size[1] + 10),
            config,
            fill="#22344A",
            font=label_font,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, default=root / "models")
    parser.add_argument(
        "--platform-models",
        type=Path,
        default=root / "standalone" / "platform_models",
    )
    parser.add_argument("--output", type=Path, default=root / "results" / "model_loads")
    parser.add_argument(
        "--grid-output",
        type=Path,
        default=root.parent.parent / "figures" / "source" / "all-models.png",
    )
    parser.add_argument(
        "--b2-output",
        type=Path,
        default=root.parent.parent / "figures" / "source" / "B2_model_loaded.png",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    laptop = complete_platform_laptop(args.platform_models / PLATFORM_MODEL)

    rendered = []
    for config in CONFIGS:
        xml_path = args.models / f"1DOF-{config}.xml"
        output_path = args.output / f"{config}_model_loaded.png"
        render_one(xml_path, output_path, laptop)
        rendered.append((config, output_path))
        print(output_path)
    make_grid(rendered, args.grid_output)
    Image.open(dict(rendered)["B2"]).save(args.b2_output)
    print(args.b2_output)
    print(args.grid_output)


if __name__ == "__main__":
    main()
