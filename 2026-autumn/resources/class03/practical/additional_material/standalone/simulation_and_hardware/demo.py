#!/usr/bin/env python3
"""Compare prepared model mass records with accepted as-built fixture records."""

from __future__ import annotations

import json
from pathlib import Path

import mujoco

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "M0": {"external_mass_g": 0.0, "positions_mm": []},
    "B0": {"external_mass_g": 110.0, "positions_mm": [-60, 60]},
    "B1": {"external_mass_g": 110.0, "positions_mm": [-80, 80]},
    "B2": {"external_mass_g": 110.0, "positions_mm": [-100, 100]},
    "G1": {"external_mass_g": 110.0, "positions_mm": [60, 100]},
}


def model_external_mass_g(config: str) -> float:
    if config == "M0":
        return 0.0
    model = mujoco.MjModel.from_xml_path(str(ROOT / "models" / f"1DOF-{config}.xml"))
    names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) or "" for i in range(model.nbody)]
    return 1000.0 * sum(float(model.body_mass[i]) for i, name in enumerate(names) if name == "Link" or name.startswith("Pin_") or name.startswith("Payload_"))


def main() -> None:
    rows = []
    for config, record in EXPECTED.items():
        model_mass = model_external_mass_g(config)
        rows.append({"configuration": config, **record, "model_external_mass_g": model_mass, "mass_difference_g": model_mass - record["external_mass_g"]})
    report = {
        "classification": "model-to-record comparison; physical values come from the accepted as-built note",
        "records": rows,
        "inertia_boundary": "model/CAD inertia is not independently measured inertia",
    }
    output = ROOT / "outputs" / "model_physical_comparison.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
