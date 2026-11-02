#!/usr/bin/env python3
"""Generate six ArUco face markers and a true-size printable SVG sheet."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from cube_model import dictionary_from_name, load_cube_model


HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "cube_config.json")
    parser.add_argument("--output", type=Path, default=HERE / "markers")
    parser.add_argument("--pixels", type=int, default=1200, help="Individual PNG resolution")
    return parser.parse_args()


def marker_svg_cells(dictionary, marker_id: int, x: float, y: float, size_mm: float) -> str:
    border_bits = 1
    side_cells = int(dictionary.markerSize) + 2 * border_bits
    cells = cv2.aruco.generateImageMarker(
        dictionary, marker_id, side_cells, borderBits=border_bits
    )
    cell_size = size_mm / side_cells
    rectangles: list[str] = []
    for row in range(side_cells):
        for column in range(side_cells):
            if int(cells[row, column]) == 0:
                rectangles.append(
                    f'<rect x="{x + column * cell_size:.6f}" y="{y + row * cell_size:.6f}" '
                    f'width="{cell_size:.6f}" height="{cell_size:.6f}" fill="black"/>'
                )
    return "\n".join(rectangles)


def individual_svg(dictionary, marker_id: int, face_name: str, size_mm: float, attachment: str) -> str:
    margin = 10.0
    label_height = 20.0
    width = size_mm + 2 * margin
    height = size_mm + 2 * margin + label_height
    cells = marker_svg_cells(dictionary, marker_id, margin, margin, size_mm)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <rect x="5" y="5" width="{size_mm+10}" height="{size_mm+10}" fill="none" stroke="#999" stroke-width="0.25" stroke-dasharray="2 1"/>
  {cells}
  <text x="{width/2}" y="{margin+size_mm+18}" text-anchor="middle" font-family="sans-serif" font-size="4.5" font-weight="bold">ID {marker_id} = face {face_name}</text>
  <text x="{width/2}" y="{margin+size_mm+24}" text-anchor="middle" font-family="sans-serif" font-size="2.7">{attachment}</text>
</svg>
'''


def sheet_svg(model, dictionary) -> str:
    page_width, page_height = 210.0, 297.0
    marker_size = model.marker_size_m * 1000.0
    if marker_size > 55.0:
        raise ValueError("The A4 sheet layout supports marker_size_m up to 0.055")
    slot_x = (25.0, 125.0)
    slot_y = (25.0, 115.0, 205.0)
    content: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{page_width}mm" height="{page_height}mm" viewBox="0 0 {page_width} {page_height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="105" y="9" text-anchor="middle" font-family="sans-serif" font-size="5" font-weight="bold">ArUco cube faces — print at 100% / Actual Size</text>',
        f'<text x="105" y="15" text-anchor="middle" font-family="sans-serif" font-size="3">Black marker square must measure exactly {marker_size:.2f} mm</text>',
    ]
    for index, face in enumerate(model.faces):
        x, y = slot_x[index % 2], slot_y[index // 2]
        content.append(marker_svg_cells(dictionary, face.marker_id, x, y, marker_size))
        content.append(
            f'<rect x="{x-5}" y="{y-5}" width="{marker_size+10}" height="{marker_size+10}" fill="none" stroke="#999" stroke-width="0.25" stroke-dasharray="2 1"/>'
        )
        content.append(
            f'<text x="{x+marker_size/2}" y="{y+marker_size+18}" text-anchor="middle" font-family="sans-serif" font-size="4.5" font-weight="bold">ID {face.marker_id} = face {face.name}</text>'
        )
        content.append(
            f'<text x="{x+marker_size/2}" y="{y+marker_size+24}" text-anchor="middle" font-family="sans-serif" font-size="2.6">{face.attachment}</text>'
        )
    content.append('</svg>')
    return "\n".join(content) + "\n"


def main() -> int:
    args = parse_args()
    model = load_cube_model(args.config)
    dictionary = dictionary_from_name(model.dictionary_name)
    args.output.mkdir(parents=True, exist_ok=True)

    for face in model.faces:
        marker = cv2.aruco.generateImageMarker(dictionary, face.marker_id, args.pixels, borderBits=1)
        png_path = args.output / f"face_{face.name.replace('+', 'plus').replace('-', 'minus')}_id_{face.marker_id}.png"
        cv2.imwrite(str(png_path), marker)
        svg_path = png_path.with_suffix(".svg")
        svg_path.write_text(
            individual_svg(dictionary, face.marker_id, face.name, model.marker_size_m * 1000.0, face.attachment),
            encoding="utf-8",
        )

    sheet_path = args.output / "aruco_cube_sheet_A4.svg"
    sheet_path.write_text(sheet_svg(model, dictionary), encoding="utf-8")
    print(f"Generated six markers and printable sheet in {args.output.resolve()}")
    print(f"Print {sheet_path.name} at 100% / Actual Size; do not use Fit to Page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
