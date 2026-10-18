#!/usr/bin/env python3
"""Build and validate the combined 16-motor MuJoCo scenes.

The Sim2Real fit is performed per motor because each hardware trajectory is an
independent 1-DOF record. This script places those 16 independent mechanisms
in one MuJoCo model while retaining the fitted values for every motor and
controller. Contacts are disabled, so layout is visual only and the 16
mechanisms remain dynamically independent.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
BASE_MODELS = ROOT / "additional_material/models/source_single"
PARAMETERS = ROOT / "additional_material/data/fitted_parameters.csv"
OUTPUT = ROOT / "additional_material/models/models"
NOTE = ROOT / "additional_material/models/LAYOUT_AND_METHOD.txt"
VALIDATION = ROOT / "additional_material/results/COMBINED_16_MOTOR_VALIDATION.json"
RENDER = ROOT / "additional_material/results/combined_16_motor_layout_B2_H1.png"
GALLERY_RENDERS = {
    "B0_H1": ROOT / "additional_material/results/combined_16_motor_layout_B0_H1.png",
    "B2_H1": RENDER,
    "G1_H2": ROOT / "additional_material/results/combined_16_motor_layout_G1_H2.png",
}

CONFIGURATIONS = ("M0", "B0", "B1", "B2", "G1")
CONTROLLERS = {
    "H1": {"kp": 1.579836, "kv": 0.202115},
    "H2": {"kp": 2.106448, "kv": 0.202115},
}
EFFORT_LIMIT_NM = 0.1551
DT = 0.002
EQUIVALENCE_STEPS = 500

# Camera-derived ID arrangement supplied with the experiment. The first ID
# in each pair is placed on face 1 and the second on the opposing face.
LOWER_PAIRS = ((0, 1), (2, 3), (4, 5), (6, 7))
UPPER_PAIRS = ((10, 8), (12, 9), (14, 11), (15, 13))

# The along-row pitch, stagger, and row spacing follow the supplied layout.
# Front-to-back depth is visual only because that distance was not measured.
COLUMN_SPACING_M = 0.270
FACE_STAGGER_M = 0.135
ROW_SPACING_M = 0.500
FACE_SPACING_M = 0.12


def load_fitted_parameters() -> dict[tuple[str, int], dict[str, float]]:
    result: dict[tuple[str, int], dict[str, float]] = {}
    with PARAMETERS.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["model"] != "hardware_fitted":
                continue
            key = (row["controller_id"], int(row["motor_id"]))
            result[key] = {
                "armature": float(row["armature_kg_m2"]),
                "damping": float(row["damping_Nm_s_per_rad"]),
                "frictionloss": float(row["frictionloss_Nm"]),
            }
    expected = {(controller, motor) for controller in CONTROLLERS for motor in range(16)}
    if set(result) != expected:
        missing = sorted(expected - set(result))
        extra = sorted(set(result) - expected)
        raise ValueError(f"unexpected fitted-parameter coverage; missing={missing}, extra={extra}")
    return result


def layout() -> dict[int, dict[str, float | int | str]]:
    result: dict[int, dict[str, float | int | str]] = {}
    for row_name, pairs, row_index in (
        ("lower", LOWER_PAIRS, 0),
        ("upper", UPPER_PAIRS, 1),
    ):
        for column, pair in enumerate(pairs):
            base_x = (column - 1.5) * COLUMN_SPACING_M
            for face_index, motor_id in enumerate(pair):
                result[motor_id] = {
                    "column": column + 1,
                    "row": row_name,
                    "face": f"face_{face_index + 1}",
                    "x_m": base_x + face_index * FACE_STAGGER_M,
                    "y_m": (-0.5 if face_index == 0 else 0.5) * FACE_SPACING_M,
                    "z_m": row_index * ROW_SPACING_M,
                    "yaw_rad": 0.0 if face_index == 0 else math.pi,
                }
    if set(result) != set(range(16)):
        raise RuntimeError("layout does not cover motor IDs 0 through 15 exactly once")
    return result


def suffixed_station(source: ET.Element, motor_id: int, values: dict[str, float]) -> ET.Element:
    station = copy.deepcopy(source)
    suffix = f"_m{motor_id:02d}"
    name_map: dict[str, str] = {}
    for node in station.iter():
        old_name = node.get("name")
        if old_name:
            name_map[old_name] = old_name + suffix
            node.set("name", name_map[old_name])
        if node.tag == "geom":
            node.set("contype", "0")
            node.set("conaffinity", "0")
    for node in station.iter():
        for attribute in ("joint", "actuator", "body", "site", "geom", "tendon"):
            old_reference = node.get(attribute)
            if old_reference in name_map:
                node.set(attribute, name_map[old_reference])
    joint = station.find(f".//joint[@name='actuator_joint{suffix}']")
    if joint is None:
        raise ValueError("source station has no actuator_joint")
    for field, value in values.items():
        joint.set(field, f"{value:.15g}")
    return station


def add_actuator(root: ET.Element, controller: str, motor_id: int) -> None:
    gains = CONTROLLERS[controller]
    section = root.find("actuator")
    assert section is not None
    ET.SubElement(
        section,
        "general",
        {
            "name": f"xc330_position_m{motor_id:02d}",
            "joint": f"actuator_joint_m{motor_id:02d}",
            "gear": "1",
            "dyntype": "none",
            "gaintype": "fixed",
            "gainprm": "1",
            "biastype": "affine",
            "biasprm": f"0 {-gains['kp']:.15g} {-gains['kv']:.15g}",
            "ctrllimited": "false",
            "forcelimited": "true",
            "forcerange": f"{-EFFORT_LIMIT_NM:.15g} {EFFORT_LIMIT_NM:.15g}",
        },
    )


def add_sensors(root: ET.Element, motor_id: int) -> None:
    section = root.find("sensor")
    assert section is not None
    joint = f"actuator_joint_m{motor_id:02d}"
    actuator = f"xc330_position_m{motor_id:02d}"
    ET.SubElement(section, "jointpos", {"name": f"q_m{motor_id:02d}", "joint": joint})
    ET.SubElement(section, "jointvel", {"name": f"qdot_m{motor_id:02d}", "joint": joint})
    ET.SubElement(
        section,
        "actuatorfrc",
        {"name": f"tau_actuator_m{motor_id:02d}", "actuator": actuator},
    )


def build_model(configuration: str, controller: str, parameters: dict) -> Path:
    source_path = BASE_MODELS / f"{configuration}.xml"
    source_root = ET.parse(source_path).getroot()
    source_station = source_root.find("./worldbody/body[@name='station']")
    if source_station is None:
        raise ValueError(f"{source_path} has no station body")

    root = ET.Element("mujoco", {"model": f"combined-16-{configuration}-{controller}"})
    compiler = copy.deepcopy(source_root.find("compiler"))
    option = copy.deepcopy(source_root.find("option"))
    visual = copy.deepcopy(source_root.find("visual"))
    asset = copy.deepcopy(source_root.find("asset"))
    if compiler is None or option is None or visual is None or asset is None:
        raise ValueError(f"{source_path} is missing a required top-level section")
    root.extend((compiler, option, visual, asset))
    for mesh in asset.findall("mesh"):
        mesh_file = Path(mesh.get("file", "")).name
        mesh.set("file", f"../assets/{mesh_file}")

    worldbody = ET.SubElement(root, "worldbody")
    source_worldbody = source_root.find("worldbody")
    assert source_worldbody is not None
    for child in source_worldbody:
        if child.tag != "body":
            worldbody.append(copy.deepcopy(child))

    locations = layout()
    for motor_id in range(16):
        location = locations[motor_id]
        mount = ET.SubElement(
            worldbody,
            "body",
            {
                "name": f"mount_m{motor_id:02d}",
                "pos": f"{location['x_m']:.15g} {location['y_m']:.15g} {location['z_m']:.15g}",
                "euler": f"0 0 {location['yaw_rad']:.15g}",
            },
        )
        mount.append(suffixed_station(source_station, motor_id, parameters[(controller, motor_id)]))

    ET.SubElement(root, "actuator")
    ET.SubElement(root, "sensor")
    for motor_id in range(16):
        add_actuator(root, controller, motor_id)
        add_sensors(root, motor_id)
    keyframe = ET.SubElement(root, "keyframe")
    ET.SubElement(
        keyframe,
        "key",
        {
            "name": "home",
            "qpos": " ".join("0" for _ in range(16)),
            "ctrl": " ".join("0" for _ in range(16)),
        },
    )

    ET.indent(root, space="  ")
    destination = OUTPUT / f"{configuration}_{controller}.xml"
    ET.ElementTree(root).write(destination, encoding="unicode", xml_declaration=False)
    with destination.open("a", encoding="utf-8") as stream:
        stream.write("\n")
    add_support_bars(destination)
    return destination


def add_support_bars(path: Path) -> None:
    """Add illustrative rack bars as world geoms, with no mass or contacts."""
    tree = ET.parse(path)
    worldbody = tree.getroot().find("worldbody")
    assert worldbody is not None
    for geom in list(worldbody.findall("geom")):
        if geom.get("name", "").startswith("visual_support_"):
            worldbody.remove(geom)
    original_scene = ET.tostring(tree.getroot())

    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    locations = layout()
    bounds = {}
    for motor_id in range(16):
        geom_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_GEOM, f"motor_mesh_1_visual_m{motor_id:02d}"
        )
        if geom_id < 0:
            raise ValueError(f"missing motor mesh for ID {motor_id}")
        mesh_id = int(model.geom_dataid[geom_id])
        start = int(model.mesh_vertadr[mesh_id])
        count = int(model.mesh_vertnum[mesh_id])
        vertices = model.mesh_vert[start:start + count]
        vertices = vertices @ data.geom_xmat[geom_id].reshape(3, 3).T + data.geom_xpos[geom_id]
        bounds[motor_id] = (vertices.min(axis=0), vertices.max(axis=0))

    left = min(float(point["x_m"]) for point in locations.values()) - 0.13
    right = max(float(point["x_m"]) for point in locations.values()) + 0.13
    center_x = (left + right) / 2
    half_length = (right - left) / 2
    half_height = 0.010
    half_width = 0.015
    rails = {}

    def bar(name: str, position: tuple, size: tuple) -> None:
        ET.SubElement(worldbody, "geom", {
            "name": f"visual_support_{name}", "type": "box",
            "pos": " ".join(f"{value:.12g}" for value in position),
            "size": " ".join(f"{value:.12g}" for value in size),
            "rgba": "0.52 0.57 0.62 1", "density": "0",
            "contype": "0", "conaffinity": "0", "group": "2",
        })

    for row in ("lower", "upper"):
        for face in ("face_1", "face_2"):
            ids = [motor for motor, point in locations.items()
                   if point["row"] == row and point["face"] == face]
            center_y = float(np.mean([(bounds[motor][0][1] + bounds[motor][1][1]) / 2
                                      for motor in ids]))
            center_z = min(float(bounds[motor][0][2]) for motor in ids) - half_height
            rails[row, face] = (center_y, center_z)
            bar(f"rail_{row}_{face}", (center_x, center_y, center_z),
                (half_length, half_width, half_height))

    for end, x in (("left", left), ("right", right)):
        for face in ("face_1", "face_2"):
            y, top = rails["upper", face]
            bar(f"post_{end}_{face}", (x, y, top / 2),
                (half_width, half_width, top / 2))
        for row in ("lower", "upper"):
            y1, z = rails[row, "face_1"]
            y2, _ = rails[row, "face_2"]
            bar(f"end_{row}_{end}", (x, (y1 + y2) / 2, z),
                (half_width, abs(y2 - y1) / 2 + half_width, half_height))

    # Removing the visual world geoms must recover the original model tree.
    unchanged = copy.deepcopy(tree.getroot())
    unchanged_world = unchanged.find("worldbody")
    assert unchanged_world is not None
    for geom in list(unchanged_world.findall("geom")):
        if geom.get("name", "").startswith("visual_support_"):
            unchanged_world.remove(geom)
    assert ET.tostring(unchanged) == original_scene
    ET.indent(tree.getroot(), space="  ")
    tree.write(path, encoding="unicode", xml_declaration=False)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\n")


def configure_individual_model(
    configuration: str, controller: str, motor_id: int, parameters: dict
) -> mujoco.MjModel:
    model = mujoco.MjModel.from_xml_path(str(BASE_MODELS / f"{configuration}.xml"))
    gains = CONTROLLERS[controller]
    model.actuator_gaintype[0] = mujoco.mjtGain.mjGAIN_FIXED
    model.actuator_biastype[0] = mujoco.mjtBias.mjBIAS_AFFINE
    model.actuator_gainprm[0] = 0.0
    model.actuator_gainprm[0, 0] = 1.0
    model.actuator_biasprm[0] = 0.0
    model.actuator_biasprm[0, 1] = -gains["kp"]
    model.actuator_biasprm[0, 2] = -gains["kv"]
    model.actuator_ctrllimited[0] = 0
    model.actuator_forcelimited[0] = 1
    model.actuator_forcerange[0] = (-EFFORT_LIMIT_NM, EFFORT_LIMIT_NM)
    values = parameters[(controller, motor_id)]
    model.dof_armature[0] = values["armature"]
    model.dof_damping[0] = values["damping"]
    model.dof_frictionloss[0] = values["frictionloss"]
    return model


def validate_dynamics(
    path: Path, configuration: str, controller: str, parameters: dict, steps: int = 500
) -> dict:
    combined = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(combined)
    references = [
        configure_individual_model(configuration, controller, motor_id, parameters)
        for motor_id in range(16)
    ]
    reference_data = [mujoco.MjData(model) for model in references]
    for model, one_data in zip(references, reference_data):
        mujoco.mj_setConst(model, one_data)
    q_addresses: list[int] = []
    v_addresses: list[int] = []
    actuator_ids: list[int] = []
    gains = CONTROLLERS[controller]
    locations = layout()
    fitted_values_match = True
    controller_values_match = True
    layout_values_match = True

    for motor_id in range(16):
        joint_name = f"actuator_joint_m{motor_id:02d}"
        actuator_name = f"xc330_position_m{motor_id:02d}"
        joint_id = mujoco.mj_name2id(combined, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        actuator_id = mujoco.mj_name2id(combined, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_name)
        if joint_id < 0 or actuator_id < 0:
            raise ValueError(f"missing motor {motor_id} joint or actuator")
        q_address = int(combined.jnt_qposadr[joint_id])
        v_address = int(combined.jnt_dofadr[joint_id])
        q_addresses.append(q_address)
        v_addresses.append(v_address)
        actuator_ids.append(actuator_id)
        values = parameters[(controller, motor_id)]
        fitted_values_match = fitted_values_match and bool(
            np.allclose(
                [combined.dof_armature[v_address], combined.dof_damping[v_address], combined.dof_frictionloss[v_address]],
                [values["armature"], values["damping"], values["frictionloss"]],
                atol=1e-14,
                rtol=0.0,
            )
        )
        controller_values_match = controller_values_match and bool(
            np.allclose(combined.actuator_gainprm[actuator_id, :1], [1.0])
            and np.allclose(combined.actuator_biasprm[actuator_id, :3], [0.0, -gains["kp"], -gains["kv"]])
            and np.allclose(combined.actuator_forcerange[actuator_id], [-EFFORT_LIMIT_NM, EFFORT_LIMIT_NM])
            and combined.actuator_forcelimited[actuator_id]
            and not combined.actuator_ctrllimited[actuator_id]
        )
        body_id = mujoco.mj_name2id(combined, mujoco.mjtObj.mjOBJ_BODY, f"mount_m{motor_id:02d}")
        location = locations[motor_id]
        expected_position = [location["x_m"], location["y_m"], location["z_m"]]
        expected_quaternion = [math.cos(location["yaw_rad"] / 2.0), 0.0, 0.0, math.sin(location["yaw_rad"] / 2.0)]
        layout_values_match = layout_values_match and bool(
            body_id >= 0
            and np.allclose(combined.body_pos[body_id], expected_position, atol=1e-14)
            and np.isclose(abs(np.dot(combined.body_quat[body_id], expected_quaternion)), 1.0)
        )
        q0 = 0.08 * math.sin(0.37 * (motor_id + 1))
        v0 = 0.03 * math.cos(0.29 * (motor_id + 1))
        data.qpos[q_address] = q0
        data.qvel[v_address] = v0
        reference_data[motor_id].qpos[0] = q0
        reference_data[motor_id].qvel[0] = v0

    mujoco.mj_forward(combined, data)
    for model, one_data in zip(references, reference_data):
        mujoco.mj_forward(model, one_data)

    per_motor_max_difference = np.zeros((16, 3), dtype=float)
    all_finite = True
    for step in range(steps):
        time_s = step * DT
        for motor_id in range(16):
            phase = 0.31 * motor_id
            frequency = 0.22 + 0.015 * (motor_id % 4)
            omega = 2.0 * math.pi * frequency
            qref = 0.22 * math.sin(omega * time_s + phase)
            vref = 0.22 * omega * math.cos(omega * time_s + phase)
            control = gains["kp"] * qref + gains["kv"] * vref
            data.ctrl[actuator_ids[motor_id]] = control
            reference_data[motor_id].ctrl[0] = control
        mujoco.mj_step(combined, data)
        for model, one_data in zip(references, reference_data):
            mujoco.mj_step(model, one_data)

        q_combined = np.asarray(data.qpos)[q_addresses]
        v_combined = np.asarray(data.qvel)[v_addresses]
        f_combined = np.asarray(data.actuator_force)[actuator_ids]
        q_reference = np.array([one_data.qpos[0] for one_data in reference_data])
        v_reference = np.array([one_data.qvel[0] for one_data in reference_data])
        f_reference = np.array([one_data.actuator_force[0] for one_data in reference_data])
        all_finite &= bool(
            np.all(np.isfinite(q_combined))
            and np.all(np.isfinite(v_combined))
            and np.all(np.isfinite(f_combined))
        )
        step_difference = np.column_stack(
            (
                np.abs(q_combined - q_reference),
                np.abs(v_combined - v_reference),
                np.abs(f_combined - f_reference),
            )
        )
        if step < EQUIVALENCE_STEPS:
            per_motor_max_difference = np.maximum(per_motor_max_difference, step_difference)
    max_q_difference = float(np.max(per_motor_max_difference[:, 0]))
    max_v_difference = float(np.max(per_motor_max_difference[:, 1]))
    max_force_difference = float(np.max(per_motor_max_difference[:, 2]))

    collision_disabled = all(
        int(combined.geom_contype[index]) == 0 and int(combined.geom_conaffinity[index]) == 0
        for index in range(combined.ngeom)
    )
    tolerance = 1e-10
    checks = {
        "dimensions_are_16_16_16": [combined.nq, combined.nv, combined.nu] == [16, 16, 16],
        "forty_eight_sensors": combined.nsensor == 48,
        "timestep_is_0p002_s": bool(np.isclose(combined.opt.timestep, DT)),
        "all_fitted_motor_values_match": fitted_values_match,
        "controller_and_effort_limit_match": controller_values_match,
        "layout_matches_supplied_arrangement": layout_values_match,
        "all_contacts_disabled": collision_disabled,
        "finite_for_1_second": all_finite,
        "matches_individual_1dof_models_over_1s": bool(
            max_q_difference <= tolerance
            and max_v_difference <= tolerance
            and max_force_difference <= tolerance
        ),
    }
    return {
        "configuration": configuration,
        "controller": controller,
        "path": str(path.relative_to(ROOT)),
        "steps": steps,
        "duration_s": steps * DT,
        "dimensions": {"nq": combined.nq, "nv": combined.nv, "nu": combined.nu},
        "sensor_count": combined.nsensor,
        "equivalence_duration_s": EQUIVALENCE_STEPS * DT,
        "max_abs_difference_vs_individual_over_1s": {
            "q_rad": max_q_difference,
            "qdot_rad_s": max_v_difference,
            "actuator_force_Nm": max_force_difference,
        },
        "per_motor_max_abs_difference_vs_individual_over_1s": [
            {
                "motor_id": motor_id,
                "face": layout()[motor_id]["face"],
                "q_rad": float(per_motor_max_difference[motor_id, 0]),
                "qdot_rad_s": float(per_motor_max_difference[motor_id, 1]),
                "actuator_force_Nm": float(per_motor_max_difference[motor_id, 2]),
            }
            for motor_id in range(16)
        ],
        "checks": checks,
        "passed": all(checks.values()),
    }


def write_note() -> None:
    NOTE.write_text(
        """COMBINED 16-MOTOR MODEL

Each XML contains all 16 motors in one MuJoCo simulation. Every motor has its own joint, actuator, position sensor, velocity sensor, force sensor, and fitted armature, damping, and friction-loss values. Separate H1 and H2 XMLs preserve their exact fitted values and controller gains.

LAYOUT
The supplied camera mapping is represented as four columns, two rows, and two opposing faces. Lower pairs from left to right are (0,1), (2,3), (4,5), and (6,7). Upper pairs are (10,8), (12,9), (14,11), and (15,13). Motors on the same face have a 0.270 m pitch. Each opposing-face motor is staggered 0.135 m along the row. Row spacing is 0.500 m. Front-to-back depth was not measured and is used only to separate the two faces visually.

DYNAMICS
The 16 mechanisms are fixed independently to the world. All contacts are disabled, so one motor cannot mechanically affect another. This matches the physical test, where the fixtures share a rack but do not form a connected mechanism. Turning the opposing face by 180 degrees around the vertical axis changes only its view, not its 1-DOF gravity dynamics.

CONTROL
H1: kp=1.579836, kv=0.202115.
H2: kp=2.106448, kv=0.202115.
For both controllers the effort limit is +/-0.1551 N m. For a recorded reference, set each control input to kp*qref + kv*vref. The actuator then applies clip(kp*(qref-q) + kv*(vref-qdot), -0.1551, +0.1551).

MODEL FILES
There are ten XMLs: M0, B0, B1, B2, and G1, each with H1 and H2.

VISUAL SUPPORTS
The bars illustrate the rack beneath the motors. Their dimensions are illustrative; they have no mass or contact interaction.

VALIDATION
Every XML is stepped for one second and checked for finite state. The full one-second run is also compared with the corresponding independent 1-DOF models to confirm numerical equivalence.

REPRODUCTION
From the Class 05 folder run:
../../mujoco-journey/dynamixel-sim2real-system-identification/V5/.venv/bin/python additional_material/code/build_and_validate_combined_16.py

To refresh only the bars and screenshot, without fitting or stepping simulations:
../../mujoco-journey/dynamixel-sim2real-system-identification/V5/.venv/bin/python additional_material/code/build_and_validate_combined_16.py --visuals-only
""",
        encoding="utf-8",
    )


def render_overview(path: Path, destination: Path = RENDER) -> dict:
    try:
        import matplotlib.pyplot as plt

        model = mujoco.MjModel.from_xml_path(str(path))
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        camera = mujoco.MjvCamera()
        camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        camera.lookat[:] = (0.0, 0.0, 0.34)
        camera.distance = 1.8
        camera.azimuth = 138.0
        camera.elevation = -17.0
        with mujoco.Renderer(model, height=640, width=960) as renderer:
            renderer.update_scene(data, camera=camera)
            pixels = renderer.render()
        plt.imsave(destination, pixels)
        return {"created": True, "path": str(destination.relative_to(ROOT))}
    except Exception as error:  # rendering is optional; validation remains headless
        return {"created": False, "error": f"{type(error).__name__}: {error}"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visuals-only", action="store_true",
                        help="Refresh support bars and screenshot in existing models; no simulation runs.")
    args = parser.parse_args()
    if args.visuals_only:
        paths = [OUTPUT / f"{configuration}_{controller}.xml"
                 for configuration in CONFIGURATIONS for controller in CONTROLLERS]
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(path)
        for path in paths:
            add_support_bars(path)
        write_note()
        renders = {
            name: render_overview(OUTPUT / f"{name}.xml", destination)
            for name, destination in GALLERY_RENDERS.items()
        }
        print(json.dumps({"models_updated": len(paths), "renders": renders}, indent=2))
        if not all(record["created"] for record in renders.values()):
            raise SystemExit(1)
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    NOTE.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION.parent.mkdir(parents=True, exist_ok=True)
    RENDER.parent.mkdir(parents=True, exist_ok=True)
    parameters = load_fitted_parameters()
    records = []
    generated = []
    for configuration in CONFIGURATIONS:
        for controller in CONTROLLERS:
            path = build_model(configuration, controller, parameters)
            generated.append(path)
            records.append(validate_dynamics(path, configuration, controller, parameters))
    write_note()
    renders = {
        name: render_overview(OUTPUT / f"{name}.xml", destination)
        for name, destination in GALLERY_RENDERS.items()
    }
    report = {
        "created_at": datetime.now(ZoneInfo("Asia/Dubai")).isoformat(),
        "mujoco_version": mujoco.__version__,
        "source_models": str(BASE_MODELS.relative_to(ROOT)),
        "fitted_parameters": str(PARAMETERS.relative_to(ROOT)),
        "layout": {
            "basis": "supplied camera-to-motor mapping",
            "lower_pairs": [list(pair) for pair in LOWER_PAIRS],
            "upper_pairs": [list(pair) for pair in UPPER_PAIRS],
            "same_face_pitch_m": COLUMN_SPACING_M,
            "opposing_face_stagger_m": FACE_STAGGER_M,
            "vertical_row_spacing_m": ROW_SPACING_M,
            "front_back_depth": "visual only; not measured",
            "motor_locations": {str(key): value for key, value in sorted(layout().items())},
        },
        "controller_settings": {
            controller: {**values, "effort_limit_Nm": EFFORT_LIMIT_NM}
            for controller, values in CONTROLLERS.items()
        },
        "generated_models": [str(path.relative_to(ROOT)) for path in generated],
        "renders": renders,
        "models": records,
        "summary": {
            "models_expected": 10,
            "models_generated": len(generated),
            "models_passed": sum(record["passed"] for record in records),
            "all_models_passed": all(record["passed"] for record in records),
        },
    }
    VALIDATION.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"validation: {VALIDATION}")
    if not report["summary"]["all_models_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
