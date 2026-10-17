#!/usr/bin/env python3
"""Generate the diagrams and comparison figures used in the Class 03 paper."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
PAPER_FIGURES = ROOT.parent / "paper" / "figures"
REGULAR = ROOT / "fonts" / "MiSans-Regular.ttf"
SEMIBOLD = ROOT / "fonts" / "MiSans-Semibold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(SEMIBOLD if bold else REGULAR), size=size)


def fitted(path: Path, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(Image.open(path).convert("RGB"), size, method=Image.Resampling.LANCZOS)

def contained(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    panel = Image.new("RGB", size, "white")
    panel.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return panel


def workflow() -> None:
    canvas = Image.new("RGB", (1800, 560), "white")
    draw = ImageDraw.Draw(canvas)
    boxes = [
        ("Physical fixture", "Measured mass and\npayload position"),
        ("CAD assembly", "Parts, joints and\nmaterial assumptions"),
        ("Robot description", "Bodies, frames, axis,\nmass and inertia"),
        ("MJCF model", "Visual mesh, limits,\ngravity and collision"),
        ("Load checks", "Compile, inspect and\nrecord assumptions"),
    ]
    colours = ["#EAF1FF", "#E9F8F0", "#FFF3DD", "#F2ECFF", "#E9F5F7"]
    for i, ((title, text), colour) in enumerate(zip(boxes, colours)):
        x0 = 45 + i * 350
        x1 = x0 + 290
        draw.rounded_rectangle((x0, 150, x1, 400), radius=24, fill=colour, outline="#53657A", width=3)
        draw.text((x0 + 24, 190), title, font=font(31, True), fill="#182433")
        draw.multiline_text((x0 + 24, 260), text, font=font(24), fill="#36475A", spacing=12)
        if i < len(boxes) - 1:
            draw.line((x1 + 14, 275, x1 + 48, 275), fill="#33465B", width=5)
            draw.polygon([(x1 + 48, 275), (x1 + 32, 264), (x1 + 32, 286)], fill="#33465B")
    draw.text((45, 55), "A validation-aware digitization chain", font=font(42, True), fill="#152132")
    draw.text((45, 470), "Each conversion preserves selected properties and introduces declared assumptions.", font=font(27), fill="#405269")
    canvas.save(PAPER_FIGURES / "digitization_workflow.png")


def configuration_schematic() -> None:
    canvas = Image.new("RGB", (1800, 980), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((50, 34), "Declared external moving assemblies", font=font(42, True), fill="#172333")
    rows = [
        ("M0", [], "0 g external moving mass"),
        ("B0", [-60, 60], "22 g link + 2 × 44 g assemblies = 110 g"),
        ("B1", [-80, 80], "22 g link + 2 × 44 g assemblies = 110 g"),
        ("B2", [-100, 100], "22 g link + 2 × 44 g assemblies = 110 g"),
        ("G1", [60, 100], "22 g link + 2 × 44 g assemblies = 110 g"),
    ]
    center_x = 700
    scale = 4.2
    for i, (name, positions, note) in enumerate(rows):
        y = 185 + i * 155
        draw.text((60, y - 28), name, font=font(34, True), fill="#182536")
        draw.line((center_x - 500, y, center_x + 500, y), fill="#316FB4", width=18 if positions else 5)
        draw.ellipse((center_x - 25, y - 25, center_x + 25, y + 25), fill="#202833")
        draw.text((center_x - 22, y + 38), "0", font=font(20), fill="#3B4B5E")
        for position in positions:
            x = int(center_x + position * scale)
            draw.line((x, y - 48, x, y + 48), fill="#5F6875", width=8)
            draw.rounded_rectangle((x - 44, y - 65, x + 44, y - 25), radius=9, fill="#42A66C")
            draw.text((x - 36, y - 61), "44 g", font=font(20, True), fill="white")
            label = f"{position:+d} mm"
            draw.text((x - 43, y + 55), label, font=font(20), fill="#34465A")
        draw.text((1260, y - 18), note, font=font(22), fill="#33465A")
    draw.text((50, 925), "Each 44 g value includes one pin and its payload. Position is measured from the XC330 output axis to the assembly centre.", font=font(23), fill="#44566A")
    canvas.save(PAPER_FIGURES / "configuration_mass_positions.png")


def component_figure() -> None:
    names = [("link.png", "Link"), ("pin.png", "Pin"), ("Payload.png", "Payload")]
    canvas = Image.new("RGB", (1800, 680), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((45, 30), "Fixture components in the CAD record", font=font(42, True), fill="#172333")
    for i, (filename, label) in enumerate(names):
        panel = fitted(ROOT / "design_screenshots" / filename, (540, 480))
        x = 45 + i * 585
        canvas.paste(panel, (x, 115))
        draw.rectangle((x, 115, x + 540, 595), outline="#53657A", width=3)
        draw.rounded_rectangle((x + 18, 130, x + 155, 180), radius=10, fill=(255, 255, 255))
        draw.text((x + 34, 139), label, font=font(27, True), fill="#182433")
    draw.text((45, 625), "CAD screenshots document shape and assembly intent; they are not physical mass measurements.", font=font(24), fill="#425469")
    canvas.save(PAPER_FIGURES / "fixture_components.png")


def actual_cad_mjcf() -> None:
    items = [
        (ROOT / "photos" / "260901-172518_B2_fixture-overview.jpg", "Physical B2 fixture"),
        (ROOT / "design_screenshots" / "1DOF-B2.png", "CAD assembly"),
        (ROOT / "results" / "model_loads" / "B2_model_loaded.png", "MJCF in MuJoCo"),
    ]
    canvas = Image.new("RGB", (1800, 720), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((45, 28), "Three views of the same declared configuration", font=font(42, True), fill="#172333")
    for i, (path, label) in enumerate(items):
        panel = fitted(path, (540, 500))
        x = 45 + i * 585
        canvas.paste(panel, (x, 110))
        draw.rectangle((x, 110, x + 540, 610), outline="#53657A", width=3)
        draw.text((x, 630), label, font=font(28, True), fill="#24364A")
    canvas.save(PAPER_FIGURES / "physical_cad_mjcf_comparison.png")


def model_grid() -> None:
    configs = ("M0", "B0", "B1", "B2", "G1")
    canvas = Image.new("RGB", (1800, 1320), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((45, 25), "Five MJCF load checks with the asBrain Box platform", font=font(42, True), fill="#172333")
    positions = [(45, 105), (915, 105), (45, 710), (915, 710), (480, 710)]
    # Use a compact two-row arrangement; G1 overlays the lower centre only after B1/B2 positions are set.
    positions = [(45, 105), (915, 105), (45, 710), (915, 710), (480, 710)]
    sizes = [(840, 560), (840, 560), (400, 560), (400, 560), (840, 560)]
    # A simple five-column strip is more legible in print.
    canvas = Image.new("RGB", (2000, 900), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((45, 25), "Five MJCF load checks with the asBrain Box platform", font=font(42, True), fill="#172333")
    for i, config in enumerate(configs):
        panel = fitted(ROOT / "results" / "model_loads" / f"{config}_model_loaded.png", (370, 690))
        x = 25 + i * 395
        canvas.paste(panel, (x, 105))
        draw.rectangle((x, 105, x + 370, 795), outline="#53657A", width=3)
        draw.text((x + 145, 812), config, font=font(30, True), fill="#22344A")
    canvas.save(PAPER_FIGURES / "all_model_loads.png")


def fusion_acdc_demo() -> None:
    source = ROOT / "demonstration" / "fusion_acdc"
    items = [
        ("Fusion_revolute_joint_preview.png", "Revolute joint and axis preview"),
        ("Fusion_physical_material.png", "Physical material assignment"),
        ("ACDC4Robot_selected.png", "ACDC4Robot loaded in Fusion"),
        ("ACDC4Robot_MJCF_export.png", "MJCF export selection"),
    ]
    canvas = Image.new("RGB", (1800, 1120), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((45, 25), "Recorded Fusion-to-MJCF workflow", font=font(42, True), fill="#172333")
    for i, (filename, label) in enumerate(items):
        x = 45 + (i % 2) * 875
        y = 105 + (i // 2) * 495
        panel = contained(source / filename, (830, 405))
        canvas.paste(panel, (x, y))
        draw.rectangle((x, y, x + 830, y + 405), outline="#53657A", width=3)
        draw.text((x, y + 418), label, font=font(25, True), fill="#24364A")
    canvas.save(PAPER_FIGURES / "fusion_acdc_workflow.png")

def rs06_reference() -> None:
    source = ROOT / "demonstration" / "rs06" / "RS06_outline_and_mounting_dimensions.png"
    canvas = Image.new("RGB", (1800, 1040), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((45, 25), "RS06 mechanical reference for prepared CAD inspection", font=font(42, True), fill="#172333")
    drawing = contained(source, (1120, 880))
    canvas.paste(drawing, (35, 105))
    draw.rectangle((35, 105, 1155, 985), outline="#53657A", width=3)
    draw.rounded_rectangle((1205, 145, 1755, 850), radius=24, fill="#EEF4FC", outline="#53657A", width=3)
    draw.text((1245, 190), "Manual values", font=font(34, True), fill="#172333")
    lines = [
        "Mass: 621 g ± 3 g",
        "Reduction ratio: 9:1",
        "Rated voltage: 48 VDC",
        "Operating range: 15–60 VDC",
        "Rated torque: 11 N·m at 100 rpm",
        "Peak torque: 36 N·m",
        "Direction: CW and CCW",
    ]
    draw.multiline_text((1245, 275), "\n\n".join(lines), font=font(25), fill="#33465A", spacing=10)
    draw.text((1205, 900), "Source: RS06 User Manual 260713", font=font(22), fill="#44566A")
    canvas.save(PAPER_FIGURES / "rs06_mechanical_reference.png")

def main() -> None:
    PAPER_FIGURES.mkdir(parents=True, exist_ok=True)
    workflow()
    configuration_schematic()
    component_figure()
    actual_cad_mjcf()
    model_grid()
    fusion_acdc_demo()
    rs06_reference()


if __name__ == "__main__":
    main()
