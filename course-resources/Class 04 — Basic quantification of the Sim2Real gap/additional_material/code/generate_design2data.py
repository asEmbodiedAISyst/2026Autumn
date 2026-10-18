#!/usr/bin/env python3
"""Build, run, and verify the fixture-grounded Design2Data release.

This script never opens a serial port.  It first audits the supplied MJCF files,
then creates unactuated mechanical-normalization copies, validates/renders those,
and only then derives the Source/Nominal C1/C2 simulation models.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import os
import platform
import shutil
import sys
import traceback
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib
import matplotlib.pyplot as plt
import mujoco
import numpy as np


PACKAGE = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE.parent
CONTRACT_PATH = PACKAGE / "configs" / "experiment_contract.json"
SOURCE_ROOT = PROJECT_ROOT / "1_Claim2Design" / "01_MJCF_and_Meshes" / "Original"
RAW_HARDWARE_PARENT = PROJECT_ROOT / "4_Model2Prototype" / "06_Raw_asBrain_Box_Logs"
MODELS = PACKAGE / "models"
DATA = PACKAGE / "data"
PLOTS = PACKAGE / "plots"
REVIEW = PACKAGE / "review"
VALIDATION = PACKAGE / "validation"
DOCS = PACKAGE / "docs"
PLATFORM_SOURCE = PACKAGE / "source_assets" / "AsBrainBox_Platform.stl"


def discover_hardware_root() -> Path:
    expected_episodes = 153
    candidates = []
    for dataset_root in sorted(RAW_HARDWARE_PARENT.iterdir()):
        if not dataset_root.is_dir():
            continue
        episode_count = 0
        for summary_path in dataset_root.glob("*/episode-summary.csv"):
            with summary_path.open(newline="", encoding="utf-8") as handle:
                episode_count += sum(
                    row.get("role") in {"calibration", "model_selection", "held_out"}
                    for row in csv.DictReader(handle)
                )
        if episode_count == expected_episodes:
            candidates.append(dataset_root)
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected one {expected_episodes}-episode recorded hardware dataset "
            f"under {RAW_HARDWARE_PARENT}, found {len(candidates)}"
        )
    return candidates[0]


HARDWARE_ROOT = discover_hardware_root()


NUMERIC_FIELDS = [
    "time_s",
    "t_command_s",
    "t_state_s",
    "position_cmd_rad",
    "position_applied_rad",
    "source_position_true_rad",
    "source_position_meas_rad",
    "source_velocity_true_rad_s",
    "source_velocity_meas_rad_s",
    "source_acceleration_true_rad_s2",
    "source_actuator_torque_Nm",
    "source_bias_torque_Nm",
    "source_passive_torque_Nm",
    "source_constraint_torque_Nm",
    "source_tracking_error_rad",
    "source_saturated",
    "nominal_position_true_rad",
    "nominal_position_meas_rad",
    "nominal_velocity_true_rad_s",
    "nominal_velocity_meas_rad_s",
    "nominal_acceleration_true_rad_s2",
    "nominal_actuator_torque_Nm",
    "nominal_bias_torque_Nm",
    "nominal_passive_torque_Nm",
    "nominal_constraint_torque_Nm",
    "nominal_tracking_error_rad",
    "nominal_saturated",
    "nominal_minus_source_position_meas_rad",
    "valid",
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def neutral_hardware_reference(path: Path) -> str:
    relative = path.relative_to(HARDWARE_ROOT)
    run_key = relative.parts[0].rsplit("-", 1)[-1]
    return str(Path(f"run-{run_key}", *relative.parts[1:]))


def clean_generated_outputs() -> None:
    for path in (MODELS, DATA, PLOTS, REVIEW, VALIDATION):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)


def source_path(contract: dict, fixture_id: str) -> Path:
    return SOURCE_ROOT / contract["fixtures"][fixture_id]["source_xml"]


def xml_duplicate_names(root: ET.Element) -> dict[str, list[str]]:
    duplicates = {}
    for tag in ("mesh", "body", "geom", "joint", "actuator", "sensor"):
        names = [node.get("name") for node in root.iter(tag) if node.get("name")]
        dup = sorted(name for name, count in Counter(names).items() if count > 1)
        if dup:
            duplicates[tag] = dup
    return duplicates


def audit_supplied_sources(contract: dict) -> list[dict]:
    output = []
    copied_root = MODELS / "supplied_original"
    for fixture_id in contract["fixtures"]:
        path = source_path(contract, fixture_id)
        tree = ET.parse(path)
        root = tree.getroot()
        record = {
            "fixture_id": fixture_id,
            "path": str(path.relative_to(PROJECT_ROOT)),
            "sha256": sha256_file(path),
            "actuator_definition_present": root.find("./actuator") is not None,
            "joint_count_in_xml": len(root.findall(".//joint")),
            "duplicate_names": xml_duplicate_names(root),
        }
        positions = []
        for body in root.findall(".//body[@name='Pin']"):
            positions.append(float(body.get("pos", "0 0 0").split()[0]))
        record["payload_station_x_positions_m"] = positions
        moving_mass = 0.0
        if fixture_id != "M0":
            fixture_body = root.find(".//body[@name='Link']")
            if fixture_body is not None:
                for inertial in fixture_body.iter("inertial"):
                    moving_mass += float(inertial.get("mass", "0"))
        record["declared_external_moving_mass_kg"] = moving_mass
        try:
            model = mujoco.MjModel.from_xml_path(str(path.resolve()))
            record.update(
                load_status="pass",
                load_error=None,
                nq=int(model.nq),
                nu=int(model.nu),
                nbody=int(model.nbody),
            )
        except Exception as exc:  # evidence must retain the exact parser failure
            record.update(
                load_status="fail",
                load_error=f"{type(exc).__name__}: {str(exc).strip()}",
                nq=None,
                nu=None,
                nbody=None,
            )
        destination = copied_root / f"1DOF-{fixture_id}"
        shutil.copytree(path.parent, destination)
        output.append(record)
    write_json(VALIDATION / "01_supplied_xml_audit.json", output)
    return output


def set_scaled_inertial(inertial: ET.Element, target_mass: float) -> None:
    original_mass = float(inertial.get("mass", "0"))
    if original_mass <= 0:
        raise ValueError("cannot scale a non-positive source inertia")
    scale = target_mass / original_mass
    if "fullinertia" in inertial.attrib:
        values = [float(value) * scale for value in inertial.get("fullinertia", "").split()]
        inertial.set("fullinertia", " ".join(f"{value:.16g}" for value in values))
    elif "diaginertia" in inertial.attrib:
        values = [float(value) * scale for value in inertial.get("diaginertia", "").split()]
        inertial.set("diaginertia", " ".join(f"{value:.16g}" for value in values))
    else:
        raise ValueError("source inertial has neither fullinertia nor diaginertia")
    inertial.set("mass", f"{target_mass:.16g}")


def add_common_model_settings(root: ET.Element, contract: dict) -> None:
    simulation = contract["simulation"]
    compiler = root.find("compiler")
    if compiler is None:
        compiler = ET.Element("compiler")
        root.insert(0, compiler)
    compiler.set("angle", "radian")
    compiler.set("eulerseq", "XYZ")
    compiler.set("inertiafromgeom", "false")
    compiler.set("autolimits", "true")
    option = root.find("option")
    if option is None:
        option = ET.Element("option")
        root.insert(list(root).index(compiler) + 1, option)
    option.set("timestep", str(simulation["physics_timestep_s"]))
    option.set("integrator", simulation["integrator"])
    option.set("gravity", f"0 0 {-float(simulation['gravity_m_s2'])}")
    visual = root.find("visual")
    if visual is None:
        visual = ET.Element("visual")
        root.insert(list(root).index(option) + 1, visual)
    global_visual = visual.find("global")
    if global_visual is None:
        global_visual = ET.SubElement(visual, "global")
    global_visual.set("offwidth", "960")
    global_visual.set("offheight", "640")


def normalize_asset_table(root: ET.Element, asset_prefix: str) -> None:
    asset = root.find("asset")
    if asset is None:
        raise ValueError("missing asset block")
    seen = set()
    for mesh in list(asset.findall("mesh")):
        old_name = mesh.get("name")
        if old_name in seen:
            asset.remove(mesh)
            continue
        seen.add(old_name)
    name_map = {
        "XC330-M288-T": "motor_mesh",
        "Link": "link_mesh",
        "Pin": "pin_mesh",
        "Payload": "payload_mesh",
    }
    for mesh in asset.findall("mesh"):
        old_name = mesh.get("name")
        mesh.set("name", name_map.get(old_name, old_name or "unnamed_mesh"))
        mesh.set("file", f"{asset_prefix}/{Path(mesh.get('file', '')).name}")
    for geom in root.findall(".//geom[@mesh]"):
        geom.set("mesh", name_map.get(geom.get("mesh"), geom.get("mesh", "")))


def normalize_visuals_and_names(root: ET.Element, fixture_id: str) -> None:
    world = root.find("worldbody")
    if world is None:
        raise ValueError("missing worldbody")
    plane = world.find("geom[@type='plane']")
    if plane is not None:
        plane.set("name", "reference_ground_visual")
        plane.set("contype", "0")
        plane.set("conaffinity", "0")
        plane.set("rgba", "0.82 0.84 0.88 1")
    light = world.find("light")
    if light is not None:
        light.set("pos", "-0.25 -0.35 1.2")
        light.set("dir", "0.15 0.25 -1")
    station = next((body for body in world.findall("body")), None)
    if station is None:
        raise ValueError("missing root station body")
    station.set("name", "station")
    source_pos = [float(value) for value in station.get("pos", "0 0 0").split()]
    source_pos[2] = 0.125
    station.set("pos", " ".join(f"{value:.16g}" for value in source_pos))
    colors = {
        "motor_mesh": "0.20 0.23 0.28 1",
        "link_mesh": "0.14 0.42 0.80 1",
        "pin_mesh": "0.72 0.73 0.75 1",
        "payload_mesh": "0.94 0.38 0.14 1",
    }
    counts = Counter()
    for geom in root.findall(".//geom[@mesh]"):
        mesh_name = geom.get("mesh", "mesh")
        counts[mesh_name] += 1
        geom.set("name", f"{mesh_name}_{counts[mesh_name]}_visual")
        geom.set("contype", "0")
        geom.set("conaffinity", "0")
        geom.set("group", "2")
        geom.set("rgba", colors.get(mesh_name, "0.6 0.6 0.6 1"))
    if fixture_id == "M0":
        return
    children = station.findall("body")
    if len(children) != 1:
        raise ValueError(f"{fixture_id}: expected one fixture body")
    fixture = children[0]
    fixture.set("name", "fixture")
    pins = fixture.findall("body")
    if len(pins) != 2:
        raise ValueError(f"{fixture_id}: expected two payload station bodies")
    for index, pin in enumerate(pins, start=1):
        pin.set("name", f"pin_{index}")
        payloads = pin.findall("body")
        if len(payloads) != 1:
            raise ValueError(f"{fixture_id}: station {index} missing payload body")
        payloads[0].set("name", f"payload_{index}")


def add_asbrain_platform(root: ET.Element, asset_prefix: str) -> None:
    """Place the mechanism in the approved asBrain Box platform pose."""
    asset = root.find("asset")
    world = root.find("worldbody")
    station = root.find("./worldbody/body[@name='station']")
    if asset is None or world is None or station is None:
        raise ValueError("missing asset, worldbody, or station")
    ET.SubElement(asset, "mesh", {
        "name": "asbrain_platform",
        "file": f"{asset_prefix}/AsBrainBox_Platform.stl",
        "scale": "0.001 0.001 0.001",
    })
    ET.SubElement(asset, "material", {
        "name": "platform_material", "rgba": "0.70 0.74 0.79 1",
        "specular": "0.16", "shininess": "0.22",
    })
    platform = ET.Element("geom", {
        "name": "platform_visual", "type": "mesh", "mesh": "asbrain_platform",
        "euler": "1.5707963 0 -1.5707963", "material": "platform_material",
        "contype": "0", "conaffinity": "0", "group": "2",
    })
    world.insert(list(world).index(station), platform)
    plane = world.find("geom[@type='plane']")
    if plane is not None:
        plane.set("pos", "0 0 -0.2975")
    station.set("pos", "-0.21 0.01 0.37")
    station.set("euler", "1.5707963267948954 0 0")


def correct_mechanical_mass_and_joint(root: ET.Element, fixture_id: str, contract: dict) -> None:
    simulation = contract["simulation"]
    source_parameters = contract["plants"]["source"]
    station = root.find("./worldbody/body")
    if station is None:
        raise ValueError("missing station")
    if fixture_id == "M0":
        output = ET.SubElement(
            station,
            "body",
            {"name": "output", "pos": "0 0 0.008", "euler": "-1.5707963267948968 0 0"},
        )
        joint = ET.SubElement(output, "joint")
        ET.SubElement(
            output,
            "inertial",
            {"mass": "0.000001", "pos": "0 0 0", "diaginertia": "1e-12 1e-12 1e-12"},
        )
        ET.SubElement(
            output,
            "geom",
            {
                "name": "output_marker",
                "type": "cylinder",
                "pos": "0 0.0015 0",
                "euler": "1.5707963267948966 0 0",
                "size": "0.008 0.002",
                "contype": "0",
                "conaffinity": "0",
                "density": "0",
                "rgba": "0.95 0.55 0.15 1",
            },
        )
        ET.SubElement(
            output,
            "site",
            {
                "name": "positive_q_marker",
                "type": "sphere",
                "pos": "0.006 0.0015 0",
                "size": "0.0015",
                "rgba": "0.90 0.18 0.12 1",
            },
        )
    else:
        fixture = station.find("body[@name='fixture']")
        if fixture is None:
            raise ValueError("missing fixture")
        joint = fixture.find("joint")
        if joint is None:
            raise ValueError("missing fixture hinge")
        link_inertial = fixture.find("inertial")
        if link_inertial is None:
            raise ValueError("missing link inertial")
        set_scaled_inertial(link_inertial, float(contract["fixtures"][fixture_id]["link_mass_kg"]))
        for pin in fixture.findall("body"):
            pin_inertial = pin.find("inertial")
            payload = pin.find("body")
            payload_inertial = payload.find("inertial") if payload is not None else None
            if pin_inertial is None or payload_inertial is None:
                raise ValueError("missing payload-station inertial")
            original_pin = float(pin_inertial.get("mass", "0"))
            original_payload = float(payload_inertial.get("mass", "0"))
            target_total = float(
                contract["fixtures"][fixture_id]["complete_payload_mass_each_kg"]
            )
            station_scale = target_total / (original_pin + original_payload)
            set_scaled_inertial(pin_inertial, original_pin * station_scale)
            set_scaled_inertial(payload_inertial, original_payload * station_scale)
    joint.set("name", "actuator_joint")
    joint.set("type", "hinge")
    # The supplied +Y world axis is opposite the recorded hardware convention.
    joint.set("axis", "0 -1 0")
    joint.set("limited", "true")
    joint.set("range", " ".join(map(str, simulation["joint_range_rad"])))
    for key in ("armature", "damping", "frictionloss"):
        joint.set(key, str(source_parameters[key]))


def remove_dynamic_blocks(root: ET.Element) -> None:
    for tag in ("actuator", "sensor", "keyframe"):
        for block in list(root.findall(tag)):
            root.remove(block)


def build_mechanical_models(contract: dict) -> tuple[dict[str, Path], list[dict]]:
    assets = MODELS / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    asset_sources = {
        "XC330-M288-T.stl": SOURCE_ROOT / "1DOF-M0" / "meshes" / "XC330-M288-T.stl",
        "Link.stl": SOURCE_ROOT / "1DOF-B0" / "meshes" / "Link.stl",
        "Pin.stl": SOURCE_ROOT / "1DOF-B0" / "meshes" / "Pin.stl",
        "Payload.stl": SOURCE_ROOT / "1DOF-B0" / "meshes" / "Payload.stl",
        "AsBrainBox_Platform.stl": PLATFORM_SOURCE,
    }
    for name, path in asset_sources.items():
        shutil.copy2(path, assets / name)
    paths = {}
    validation = []
    for fixture_id, fixture in contract["fixtures"].items():
        source = source_path(contract, fixture_id)
        tree = ET.parse(source)
        root = tree.getroot()
        root.set("model", f"mechanics-{fixture_id}-validated-unactuated")
        add_common_model_settings(root, contract)
        normalize_asset_table(root, "../assets")
        normalize_visuals_and_names(root, fixture_id)
        add_asbrain_platform(root, "../assets")
        correct_mechanical_mass_and_joint(root, fixture_id, contract)
        remove_dynamic_blocks(root)
        destination = MODELS / "mechanics_validated_unactuated" / f"{fixture_id}.xml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        ET.indent(tree, space="  ")
        tree.write(destination, encoding="unicode")
        model = mujoco.MjModel.from_xml_path(str(destination.resolve()))
        moving_mass = float(model.body_mass[2:].sum()) if fixture_id == "M0" else float(
            model.body_mass[2:].sum()
        )
        positions = []
        for name in ("pin_1", "pin_2"):
            body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
            if body_id >= 0:
                positions.append(float(model.body_pos[body_id, 0]))
        record = {
            "fixture_id": fixture_id,
            "path": str(destination.relative_to(PACKAGE)),
            "sha256": sha256_file(destination),
            "load_status": "pass",
            "nq": int(model.nq),
            "nu": int(model.nu),
            "joint_name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, 0),
            "joint_axis_local": model.jnt_axis[0].tolist(),
            "payload_station_x_positions_m": positions,
            "declared_moving_body_mass_kg": moving_mass,
            "hardware_external_moving_mass_kg": fixture["external_moving_mass_kg"],
            "actuator_present": bool(model.nu),
        }
        expected = float(fixture["external_moving_mass_kg"])
        if fixture_id == "M0":
            record["mass_note"] = "1e-6 kg numerical output marker; external hardware mass remains zero"
            record["mass_match"] = abs(moving_mass - 1e-6) < 1e-12
        else:
            record["mass_match"] = abs(moving_mass - expected) < 1e-12
        validation.append(record)
        paths[fixture_id] = destination
    write_json(VALIDATION / "02_unactuated_mechanics_validation.json", validation)
    return paths, validation


def render_mechanical_review(paths: dict[str, Path]) -> list[dict]:
    records = []
    for fixture_id, path in paths.items():
        record = {"fixture_id": fixture_id, "model": str(path.relative_to(PACKAGE))}
        try:
            model = mujoco.MjModel.from_xml_path(str(path.resolve()))
            data = mujoco.MjData(model)
            renderer = mujoco.Renderer(model, height=480, width=640)
            camera = mujoco.MjvCamera()
            camera.type = mujoco.mjtCamera.mjCAMERA_FREE
            camera.lookat[:] = (0.0, 0.0, 0.08)
            camera.azimuth = 135.0
            camera.elevation = -18.0
            camera.distance = 1.05
            fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), constrained_layout=True)
            for axis, q in zip(axes, (-0.65, 0.0, 0.65), strict=True):
                data.qpos[0] = q
                data.qvel[0] = 0.0
                mujoco.mj_forward(model, data)
                renderer.update_scene(data, camera=camera)
                axis.imshow(renderer.render())
                axis.set_title(f"q = {q:+.2f} rad")
                axis.axis("off")
            fig.suptitle(f"{fixture_id}: validated unactuated mechanics (view from -Y)")
            destination = REVIEW / "mechanics" / f"{fixture_id}_minus065_zero_plus065.png"
            destination.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(destination, dpi=140)
            plt.close(fig)
            renderer.close()
            record.update(status="pass", image=str(destination.relative_to(PACKAGE)), error=None)
        except Exception as exc:
            record.update(
                status="fail",
                image=None,
                error=f"{type(exc).__name__}: {exc}",
                traceback=traceback.format_exc(),
            )
        records.append(record)
    write_json(VALIDATION / "03_mechanical_render_validation.json", records)
    if any(record["status"] != "pass" for record in records):
        raise RuntimeError("one or more mechanical review renders failed")
    return records


def add_actuator_blocks(root: ET.Element, controller: dict) -> None:
    actuator = ET.SubElement(root, "actuator")
    ET.SubElement(
        actuator,
        "position",
        {
            "name": "xc330_position",
            "joint": "actuator_joint",
            "gear": "1",
            "kp": str(controller["kp_Nm_per_rad"]),
            "kv": str(controller["kv_Nm_s_per_rad"]),
            "ctrllimited": "true",
            "ctrlrange": "-0.9 0.9",
            "forcelimited": "true",
            "forcerange": "-0.5 0.5",
        },
    )
    sensors = ET.SubElement(root, "sensor")
    ET.SubElement(sensors, "jointpos", {"name": "q", "joint": "actuator_joint"})
    ET.SubElement(sensors, "jointvel", {"name": "qdot", "joint": "actuator_joint"})
    ET.SubElement(
        sensors, "actuatorfrc", {"name": "tau_actuator", "actuator": "xc330_position"}
    )
    keyframe = ET.SubElement(root, "keyframe")
    ET.SubElement(keyframe, "key", {"name": "home", "qpos": "0", "ctrl": "0"})


def build_actuated_models(contract: dict, mechanical_paths: dict[str, Path]):
    paths = defaultdict(lambda: defaultdict(dict))
    records = []
    for plant_id, parameters in contract["plants"].items():
        for controller_id, controller in contract["controllers"].items():
            for fixture_id, mechanical_path in mechanical_paths.items():
                tree = ET.parse(mechanical_path)
                root = tree.getroot()
                root.set("model", f"{plant_id}-{controller_id}-{fixture_id}")
                for mesh in root.findall("./asset/mesh"):
                    mesh.set("file", f"../../../assets/{Path(mesh.get('file', '')).name}")
                joint = root.find(".//joint[@name='actuator_joint']")
                if joint is None:
                    raise ValueError("missing actuator_joint")
                for key in ("armature", "damping", "frictionloss"):
                    joint.set(key, str(parameters[key]))
                remove_dynamic_blocks(root)
                add_actuator_blocks(root, controller)
                destination = MODELS / "simulation" / plant_id / controller_id / f"{fixture_id}.xml"
                destination.parent.mkdir(parents=True, exist_ok=True)
                ET.indent(tree, space="  ")
                tree.write(destination, encoding="unicode")
                model = mujoco.MjModel.from_xml_path(str(destination.resolve()))
                actuator_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_ACTUATOR, "xc330_position"
                )
                joint_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_JOINT, "actuator_joint"
                )
                transmission_joint_id = int(model.actuator_trnid[actuator_id, 0])
                checks = {
                    "one_joint": int(model.njnt) == 1,
                    "one_actuator": int(model.nu) == 1,
                    "correct_joint_target": transmission_joint_id == joint_id,
                    "unit_gear": abs(float(model.actuator_gear[actuator_id, 0]) - 1.0) < 1e-12,
                    "ctrlrange_exact": np.allclose(model.actuator_ctrlrange[actuator_id], [-0.9, 0.9]),
                    "forcerange_exact": np.allclose(model.actuator_forcerange[actuator_id], [-0.5, 0.5]),
                    "kp_mapping_exact": abs(float(model.actuator_gainprm[actuator_id, 0]) - controller["kp_Nm_per_rad"]) < 1e-12,
                    "position_feedback_exact": abs(float(model.actuator_biasprm[actuator_id, 1]) + controller["kp_Nm_per_rad"]) < 1e-12,
                    "velocity_feedback_exact": abs(float(model.actuator_biasprm[actuator_id, 2]) + controller["kv_Nm_s_per_rad"]) < 1e-12,
                    "joint_armature_exact": abs(float(model.dof_armature[0]) - parameters["armature"]) < 1e-12,
                    "joint_damping_exact": abs(float(model.dof_damping[0]) - parameters["damping"]) < 1e-12,
                    "joint_frictionloss_exact": abs(float(model.dof_frictionloss[0]) - parameters["frictionloss"]) < 1e-12,
                }
                record = {
                    "plant_id": plant_id,
                    "controller_id": controller_id,
                    "fixture_id": fixture_id,
                    "path": str(destination.relative_to(PACKAGE)),
                    "sha256": sha256_file(destination),
                    "nq": int(model.nq),
                    "nu": int(model.nu),
                    "checks": checks,
                    "passed": all(checks.values()),
                }
                records.append(record)
                paths[plant_id][controller_id][fixture_id] = destination
    write_json(VALIDATION / "04_actuator_model_validation.json", records)
    if not all(record["passed"] for record in records):
        raise RuntimeError("actuator mapping validation failed")
    return paths, records


def smooth_transition(start: float, stop: float, count: int) -> np.ndarray:
    phase = np.linspace(0.0, 1.0, count, endpoint=False)
    return start + (stop - start) * (0.5 - 0.5 * np.cos(np.pi * phase))


def build_profile(spec: dict, dt: float) -> tuple[np.ndarray, np.ndarray]:
    kind = spec["kind"]
    if kind == "smooth_levels":
        hold_count = round(float(spec["hold_s"]) / dt)
        transition_count = round(float(spec["transition_s"]) / dt)
        levels = [float(value) for value in spec["levels_rad"]]
        pieces = [np.full(hold_count, levels[0])]
        for start, stop in zip(levels[:-1], levels[1:], strict=True):
            pieces.append(smooth_transition(start, stop, transition_count))
            pieces.append(np.full(hold_count, stop))
        command = np.concatenate(pieces)
        return np.arange(command.size, dtype=float) * dt, command
    duration = float(spec["duration_s"])
    time = np.arange(round(duration / dt) + 1, dtype=float) * dt
    if kind == "triangle":
        phase = 2 * np.pi * float(spec["frequency_hz"]) * time
        command = float(spec["center_rad"]) + float(spec["amplitude_rad"]) * (
            2 / np.pi
        ) * np.arcsin(np.sin(phase))
    elif kind == "multisine":
        command = np.full_like(time, float(spec["center_rad"]))
        for amplitude, frequency, phase in zip(
            spec["amplitudes_rad"], spec["frequencies_hz"], spec["phases_rad"], strict=True
        ):
            command += float(amplitude) * np.sin(2 * np.pi * float(frequency) * time + float(phase))
    elif kind == "chirp":
        start_frequency = float(spec["start_frequency_hz"])
        end_frequency = float(spec["end_frequency_hz"])
        phase = 2 * np.pi * (
            start_frequency * time
            + 0.5 * (end_frequency - start_frequency) / duration * time**2
        )
        command = float(spec["center_rad"]) + float(spec["amplitude_rad"]) * np.sin(phase)
    elif kind == "sine":
        command = float(spec["center_rad"]) + float(spec["amplitude_rad"]) * np.sin(
            2 * np.pi * float(spec["frequency_hz"]) * time
        )
    elif kind == "composite":
        command = np.zeros_like(time)
        for amplitude, frequency, phase in zip(
            spec["amplitudes_rad"], spec["frequencies_hz"], spec["phases_rad"], strict=True
        ):
            command += float(amplitude) * np.sin(2 * np.pi * float(frequency) * time + float(phase))
        switches = spec["switch_times_s"]
        offsets = spec["center_offsets_rad"]
        command += np.select(
            [time < float(switches[0]), time < float(switches[1])],
            [float(offsets[0]), float(offsets[1])],
            default=float(offsets[2]),
        )
    elif kind == "sine_hold":
        center = float(spec["center_rad"])
        amplitude = float(spec["amplitude_rad"])
        frequency = float(spec["frequency_hz"])
        active = float(spec["active_duration_s"])
        transition = float(spec["transition_s"])
        hold = float(spec["hold_position_rad"])
        command = center + amplitude * np.sin(2 * np.pi * frequency * time)
        start_value = center + amplitude * math.sin(2 * math.pi * frequency * active)
        mask = (time >= active) & (time < active + transition)
        blend = 0.5 - 0.5 * np.cos(np.pi * (time[mask] - active) / transition)
        command[mask] = start_value + (hold - start_value) * blend
        command[time >= active + transition] = hold
    else:
        raise ValueError(f"unsupported profile kind {kind}")
    return time, command.astype(float)


def build_all_profiles(contract: dict) -> dict[str, dict[str, np.ndarray]]:
    dt = 1.0 / float(contract["simulation"]["sample_rate_hz"])
    resolution = float(contract["simulation"]["position_resolution_rad"])
    output = {}
    rows = []
    for profile_id, spec in contract["profiles"].items():
        time, requested = build_profile(spec, dt)
        applied = np.round(requested / resolution) * resolution
        output[profile_id] = {"time": time, "requested": requested, "applied": applied}
        for index in range(time.size):
            rows.append(
                {
                    "profile_id": profile_id,
                    "split": spec["split"],
                    "sample_index": index,
                    "time_s": f"{time[index]:.8f}",
                    "position_cmd_rad": f"{requested[index]:.16g}",
                    "position_applied_rad": f"{applied[index]:.16g}",
                }
            )
    path = DATA / "command_trajectories.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summaries = []
    for profile_id, arrays in output.items():
        velocity = np.gradient(arrays["applied"], dt)
        summaries.append(
            {
                "profile_id": profile_id,
                "split": contract["profiles"][profile_id]["split"],
                "samples": int(arrays["time"].size),
                "duration_s": float(arrays["time"][-1]),
                "requested_min_rad": float(arrays["requested"].min()),
                "requested_max_rad": float(arrays["requested"].max()),
                "applied_min_rad": float(arrays["applied"].min()),
                "applied_max_rad": float(arrays["applied"].max()),
                "maximum_abs_applied_velocity_rad_s": float(np.abs(velocity).max()),
            }
        )
    write_json(DATA / "command_trajectory_summary.json", summaries)
    return output


def episode_specs(contract: dict) -> list[dict]:
    specs = []
    for split, block in contract["episode_matrix"].items():
        for controller_id in block["controllers"]:
            for fixture_id in block["fixtures"]:
                for profile_id in block["profiles"]:
                    specs.append(
                        {
                            "episode_id": f"{fixture_id}__{controller_id}__{profile_id}__{block['repetition']}",
                            "split": split,
                            "fixture_id": fixture_id,
                            "profile_id": profile_id,
                            "controller_id": controller_id,
                            "repetition": block["repetition"],
                        }
                    )
        for fixture_id, profile_id, controller_id in block.get("additional_pairs", []):
            specs.append(
                {
                    "episode_id": f"{fixture_id}__{controller_id}__{profile_id}__{block['repetition']}",
                    "split": split,
                    "fixture_id": fixture_id,
                    "profile_id": profile_id,
                    "controller_id": controller_id,
                    "repetition": block["repetition"],
                }
            )
    return specs


def simulate(model_path: Path, time: np.ndarray, applied: np.ndarray, contract: dict) -> dict:
    model = mujoco.MjModel.from_xml_path(str(model_path.resolve()))
    data = mujoco.MjData(model)
    simulation = contract["simulation"]
    sample_dt = 1.0 / float(simulation["sample_rate_hz"])
    substeps_float = sample_dt / float(model.opt.timestep)
    substeps = round(substeps_float)
    if not np.isclose(substeps, substeps_float):
        raise ValueError("sample interval is not an integer multiple of the physics step")
    data.qpos[0] = float(applied[0])
    data.qvel[0] = 0.0
    data.ctrl[0] = float(applied[0])
    mujoco.mj_forward(model, data)
    for _ in range(round(float(simulation["pre_roll_s"]) / float(model.opt.timestep))):
        mujoco.mj_step(model, data)
    arrays = {
        "position_true_rad": np.empty(time.size),
        "velocity_true_rad_s": np.empty(time.size),
        "acceleration_true_rad_s2": np.empty(time.size),
        "actuator_torque_Nm": np.empty(time.size),
        "bias_torque_Nm": np.empty(time.size),
        "passive_torque_Nm": np.empty(time.size),
        "constraint_torque_Nm": np.empty(time.size),
        "saturated": np.zeros(time.size, dtype=bool),
    }
    force_limit = max(abs(float(value)) for value in simulation["forcerange_Nm"])
    for index, command in enumerate(applied):
        data.ctrl[0] = float(command)
        mujoco.mj_forward(model, data)
        arrays["position_true_rad"][index] = data.qpos[0]
        arrays["velocity_true_rad_s"][index] = data.qvel[0]
        arrays["acceleration_true_rad_s2"][index] = data.qacc[0]
        arrays["actuator_torque_Nm"][index] = data.qfrc_actuator[0]
        arrays["bias_torque_Nm"][index] = data.qfrc_bias[0]
        arrays["passive_torque_Nm"][index] = data.qfrc_passive[0]
        arrays["constraint_torque_Nm"][index] = data.qfrc_constraint[0]
        arrays["saturated"][index] = abs(data.qfrc_actuator[0]) >= force_limit - 1e-7
        if index + 1 < time.size:
            for _ in range(substeps):
                mujoco.mj_step(model, data)
    q_resolution = float(simulation["position_resolution_rad"])
    v_resolution = float(simulation["velocity_resolution_rad_s"])
    arrays["position_meas_rad"] = np.round(arrays["position_true_rad"] / q_resolution) * q_resolution
    arrays["velocity_meas_rad_s"] = np.round(arrays["velocity_true_rad_s"] / v_resolution) * v_resolution
    return arrays


def episode_arrays(spec: dict, profiles: dict, models, contract: dict) -> dict[str, np.ndarray]:
    profile = profiles[spec["profile_id"]]
    time = profile["time"]
    requested = profile["requested"]
    applied = profile["applied"]
    source = simulate(models["source"][spec["controller_id"]][spec["fixture_id"]], time, applied, contract)
    nominal = simulate(models["nominal"][spec["controller_id"]][spec["fixture_id"]], time, applied, contract)
    arrays = {
        "time_s": time,
        "t_command_s": time,
        "t_state_s": time,
        "position_cmd_rad": requested,
        "position_applied_rad": applied,
    }
    for plant_id, result in (("source", source), ("nominal", nominal)):
        for name, values in result.items():
            arrays[f"{plant_id}_{name}"] = values
        arrays[f"{plant_id}_tracking_error_rad"] = result["position_meas_rad"] - applied
    arrays["nominal_minus_source_position_meas_rad"] = (
        nominal["position_meas_rad"] - source["position_meas_rad"]
    )
    arrays["valid"] = np.ones(time.size, dtype=bool)
    return arrays


def write_episode_csv(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(NUMERIC_FIELDS)
        for index in range(arrays["time_s"].size):
            row = []
            for field in NUMERIC_FIELDS:
                value = arrays[field][index]
                if isinstance(value, (np.bool_, bool)):
                    row.append(int(value))
                else:
                    row.append(f"{float(value):.16g}")
            writer.writerow(row)


def run_episodes(contract: dict, profiles: dict, models):
    specs = episode_specs(contract)
    episode_list = []
    summaries = []
    failures = []
    combined = defaultdict(list)
    offsets = [0]
    successful_specs = []
    for spec in specs:
        try:
            arrays = episode_arrays(spec, profiles, models, contract)
            path = DATA / "raw_simulation" / f"{spec['episode_id']}.csv.gz"
            write_episode_csv(path, arrays)
            source_error = arrays["source_tracking_error_rad"]
            nominal_gap = arrays["nominal_minus_source_position_meas_rad"]
            summary = {
                **spec,
                "completion_status": "complete",
                "sample_count": int(arrays["time_s"].size),
                "duration_s": float(arrays["time_s"][-1]),
                "source_tracking_rmse_rad": float(np.sqrt(np.mean(source_error**2))),
                "source_tracking_mae_rad": float(np.mean(np.abs(source_error))),
                "source_peak_abs_tracking_error_rad": float(np.max(np.abs(source_error))),
                "source_saturation_fraction": float(np.mean(arrays["source_saturated"])),
                "source_peak_abs_actuator_torque_Nm": float(np.max(np.abs(arrays["source_actuator_torque_Nm"]))),
                "nominal_to_source_rmse_rad": float(np.sqrt(np.mean(nominal_gap**2))),
                "nominal_to_source_peak_abs_gap_rad": float(np.max(np.abs(nominal_gap))),
                "maximum_abs_source_velocity_rad_s": float(np.max(np.abs(arrays["source_velocity_true_rad_s"]))),
                "raw_result": str(path.relative_to(PACKAGE)),
                "raw_result_sha256": sha256_file(path),
                "source_model": str(models["source"][spec["controller_id"]][spec["fixture_id"]].relative_to(PACKAGE)),
                "nominal_model": str(models["nominal"][spec["controller_id"]][spec["fixture_id"]].relative_to(PACKAGE)),
            }
            summaries.append(summary)
            episode_list.append(
                {
                    **spec,
                    "source_plant": "source",
                    "comparison_plant": "nominal",
                    "simulation_instance_note": "R01 is the single deterministic instance required by the frozen 38-episode design",
                    "completion_status": "complete",
                    "raw_result": str(path.relative_to(PACKAGE)),
                }
            )
            for field in NUMERIC_FIELDS:
                combined[field].append(np.asarray(arrays[field]))
            offsets.append(offsets[-1] + arrays["time_s"].size)
            successful_specs.append(spec)
        except Exception as exc:
            failures.append(
                {
                    **spec,
                    "stage": "simulation",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
            episode_list.append({**spec, "completion_status": "failed", "raw_result": ""})
    DATA.mkdir(parents=True, exist_ok=True)
    write_csv_dicts(DATA / "episode_list.csv", episode_list)
    write_csv_dicts(DATA / "episode_summary.csv", summaries)
    failure_fields = [
        "episode_id", "split", "fixture_id", "profile_id", "controller_id", "repetition", "stage", "error_type", "error", "traceback"
    ]
    write_csv_dicts(VALIDATION / "failed_or_incomplete_simulation_runs.csv", failures, failure_fields)
    if successful_specs:
        archive = {field: np.concatenate(values) for field, values in combined.items()}
        archive.update(
            episode_id=np.asarray([spec["episode_id"] for spec in successful_specs]),
            split=np.asarray([spec["split"] for spec in successful_specs]),
            fixture_id=np.asarray([spec["fixture_id"] for spec in successful_specs]),
            profile_id=np.asarray([spec["profile_id"] for spec in successful_specs]),
            controller_id=np.asarray([spec["controller_id"] for spec in successful_specs]),
            repetition=np.asarray([spec["repetition"] for spec in successful_specs]),
            episode_offsets=np.asarray(offsets, dtype=np.int64),
        )
        np.savez_compressed(DATA / "raw_simulation_combined.npz", **archive)
    return specs, summaries, failures


def write_csv_dicts(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_hardware_episode_index() -> list[dict]:
    rows = []
    for summary_path in sorted(HARDWARE_ROOT.glob("*/episode-summary.csv")):
        run_dir = summary_path.parent
        with summary_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                role = row.get("role", "")
                if role not in {"calibration", "model_selection", "held_out"}:
                    continue
                episode_id = row["episode_id"]
                episode_dir_matches = list((run_dir / "episodes").glob(f"{episode_id}*"))
                rows.append(
                    {
                        "episode_id": episode_id,
                        "configuration": episode_id.split("__", 1)[0],
                        "profile": row.get("profile_id", ""),
                        "hardware_controller": row.get("controller_id", ""),
                        "hardware_position_p_gain_raw": row.get("hardware_position_p_gain_raw", ""),
                        "hardware_position_i_gain_raw": row.get("hardware_position_i_gain_raw", ""),
                        "hardware_position_d_gain_raw": row.get("hardware_position_d_gain_raw", ""),
                        "repetition": row.get("repeat_id", ""),
                        "intended_data_split": role,
                        "completion_status": row.get("completion_status", ""),
                        "canonical_episode_directory": neutral_hardware_reference(episode_dir_matches[0]) if episode_dir_matches else "MISSING",
                    }
                )
    write_csv_dicts(DATA / "recorded_hardware_episode_index.csv", rows)
    return rows


def create_plots(summaries: list[dict]) -> None:
    example_id = "G1__C1__P06_heldout_composite__R01"
    path = DATA / "raw_simulation" / f"{example_id}.csv.gz"
    values = np.genfromtxt(path, delimiter=",", names=True)
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True, constrained_layout=True)
    axes[0].plot(values["time_s"], values["position_applied_rad"], "k--", lw=1.5, label="applied command")
    axes[0].plot(values["time_s"], values["source_position_meas_rad"], lw=1.2, label="Source measured output")
    axes[0].plot(values["time_s"], values["nominal_position_meas_rad"], lw=1.1, label="Nominal measured output")
    axes[0].set_ylabel("position (rad)")
    axes[0].set_title(f"Input-output example: {example_id}")
    axes[0].grid(alpha=0.25)
    axes[0].legend(ncol=3, fontsize=8)
    axes[1].plot(values["time_s"], values["nominal_minus_source_position_meas_rad"], color="tab:red", lw=1.0)
    axes[1].axhline(0, color="0.3", lw=0.7)
    axes[1].set_xlabel("time (s)")
    axes[1].set_ylabel("Nominal − Source (rad)")
    axes[1].grid(alpha=0.25)
    PLOTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOTS / "input_output_example.png", dpi=180)
    plt.close(fig)

    split_colors = {"calibration": "tab:blue", "model_selection": "tab:orange", "held_out": "tab:green"}
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.7), constrained_layout=True)
    for split in split_colors:
        subset = [row for row in summaries if row["split"] == split]
        axes[0].scatter(
            [row["source_peak_abs_actuator_torque_Nm"] / 0.5 for row in subset],
            [row["nominal_to_source_rmse_rad"] for row in subset],
            label=f"{split} (n={len(subset)})",
            color=split_colors[split],
            alpha=0.8,
        )
    axes[0].set_xlabel("Source peak effort / 0.5 N·m limit")
    axes[0].set_ylabel("Nominal-to-Source RMSE (rad)")
    axes[0].set_title("Effort utilization and model-gap coverage")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    labels = []
    values = []
    colors = []
    for fixture in ("M0", "B0", "B1", "B2", "G1"):
        for controller in ("C1", "C2"):
            subset = [row for row in summaries if row["fixture_id"] == fixture and row["controller_id"] == controller]
            if subset:
                labels.append(f"{fixture}-{controller}")
                values.append(max(row["source_peak_abs_actuator_torque_Nm"] for row in subset) / 0.5)
                colors.append("tab:blue" if controller == "C1" else "tab:purple")
    axes[1].bar(labels, values, color=colors)
    axes[1].axhline(1.0, color="tab:red", ls="--", lw=1, label="force limit")
    axes[1].set_ylabel("maximum effort utilization")
    axes[1].set_title("Configuration/controller coverage")
    axes[1].tick_params(axis="x", rotation=45)
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(fontsize=8)
    fig.savefig(PLOTS / "data_quality_and_coverage.png", dpi=180)
    plt.close(fig)


def validate_release(contract: dict, supplied: list[dict], mechanical: list[dict], model_records: list[dict], specs: list[dict], summaries: list[dict], failures: list[dict], hardware_rows: list[dict]) -> dict:
    expected_split = {"calibration": 24, "model_selection": 8, "held_out": 6}
    actual_split = Counter(row["split"] for row in summaries)
    all_finite = True
    hash_checks = True
    command_exact = True
    saturation_fractions = []
    for row in summaries:
        result_path = PACKAGE / row["raw_result"]
        hash_checks &= sha256_file(result_path) == row["raw_result_sha256"]
        values = np.genfromtxt(result_path, delimiter=",", names=True)
        for name in values.dtype.names:
            all_finite &= bool(np.all(np.isfinite(values[name])))
        resolution = float(contract["simulation"]["position_resolution_rad"])
        command_exact &= bool(
            np.allclose(values["position_applied_rad"], np.round(values["position_cmd_rad"] / resolution) * resolution)
        )
        saturation_fractions.append(float(np.mean(values["source_saturated"])))
    gap_values = [row["nominal_to_source_rmse_rad"] for row in summaries]
    checks = {
        "runtime_mujoco_matches_required_3_3_7": mujoco.__version__ == contract["simulation"]["required_mujoco_version"],
        "supplied_xmls_preserved_and_audited": len(supplied) == 5,
        "four_supplied_weighted_xml_failures_recorded": sum(row["load_status"] == "fail" for row in supplied) == 4,
        "supplied_m0_static_limitation_recorded": next(row for row in supplied if row["fixture_id"] == "M0")["nq"] == 0,
        "all_unactuated_corrected_mechanics_load": all(row["load_status"] == "pass" for row in mechanical),
        "all_unactuated_corrected_mechanics_have_no_actuator": all(not row["actuator_present"] for row in mechanical),
        "all_weighted_corrected_masses_match_0_110kg": all(row["mass_match"] for row in mechanical),
        "all_20_actuated_models_load_and_map_exactly": len(model_records) == 20 and all(row["passed"] for row in model_records),
        "exact_38_episode_matrix": len(specs) == 38 and len(summaries) == 38,
        "split_counts_exact": dict(actual_split) == expected_split,
        "no_failed_or_incomplete_simulation_runs": not failures,
        "all_archive_values_finite": all_finite,
        "raw_episode_hashes_match_summary": hash_checks,
        "applied_command_is_quantized_request": command_exact,
        "zero_command_delay_declared": float(contract["simulation"]["command_delay_s"]) == 0.0,
        "source_saturation_below_rejection_fraction": max(saturation_fractions, default=1.0) < float(contract["simulation"]["source_saturation_rejection_fraction"]),
        "nominal_source_gap_is_measurable": float(np.median(gap_values)) > 0.0,
        "dynamic_g1_absent_from_calibration": not any(row["fixture_id"] == "G1" and row["split"] == "calibration" for row in summaries),
        "recorded_hardware_scientific_index_has_153_rows": len(hardware_rows) == 153,
        "all_recorded_hardware_scientific_rows_complete": all(row["completion_status"] == "complete" for row in hardware_rows),
    }
    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "counts": {
            "supplied_xmls": len(supplied),
            "mechanical_models": len(mechanical),
            "actuated_models": len(model_records),
            "simulation_episodes": len(summaries),
            "recorded_hardware_scientific_episodes_indexed": len(hardware_rows),
        },
        "metrics": {
            "maximum_source_saturation_fraction": max(saturation_fractions, default=None),
            "maximum_source_effort_utilization": max((row["source_peak_abs_actuator_torque_Nm"] / 0.5 for row in summaries), default=None),
            "median_nominal_to_source_rmse_rad": float(np.median(gap_values)) if gap_values else None,
            "maximum_nominal_to_source_rmse_rad": max(gap_values, default=None),
        },
        "note": "qfrc_actuator is simulator-only context, not calibrated hardware torque and not part of the primary fitting boundary.",
    }
    write_json(VALIDATION / "05_final_verification.json", report)
    if not report["passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"release verification failed: {failed}")
    return report


def write_documentation(contract: dict, supplied: list[dict], verification: dict) -> None:
    timestamp = datetime.now(ZoneInfo("Asia/Dubai"))
    note = f"""Date, time, and timezone: {timestamp.strftime('%-d %B %Y, %H:%M:%S')}, Asia/Dubai (UTC+04:00)
Prepared by: Mohamad Halwani

What we are trying to achieve:
Create a repeatable MuJoCo dataset for the five hardware configurations.

What is available now:
- Five source XML packages and five loadable mechanical models.
- Twenty actuated MJCF models and 38 repeatable simulation episodes.
- Command tables, episode data, plots and validation checks.

What is planned but not yet tested:
Fit armature, damping and friction loss to the H1 and H2 hardware data. Check output torque separately if torque validation is needed.

Important decisions:
The source XMLs stay unchanged. The derived models use the measured 22 g link and two 44 g payload assemblies. C1 and C2 are MuJoCo gains, not hardware register values.

Known problems or missing information:
The supplied loaded-fixture XMLs have duplicate names, and M0 has no moving joint. Hardware current is not output torque.

What should happen next:
Fit with the calibration episodes, choose the model with the selection episodes and leave the held-out episodes for the final check.
"""
    (PACKAGE / "00_Milestone_Note.txt").write_text(note, encoding="utf-8")

    source_rows = []
    for row in supplied:
        source_rows.append(
            f"| {row['fixture_id']} | {row['load_status']} | {row['joint_count_in_xml']} | {row['declared_external_moving_mass_kg']:.9f} | {row['payload_station_x_positions_m']} | {row['load_error'] or 'none'} |"
        )
    validation_doc = """# Supplied XML versus recorded hardware validation

The files under `models/supplied_original/` are exact copies of the supplied inputs. They were audited before any actuator was created. They cannot be certified as directly simulation-ready.

| Config | Original MuJoCo load | XML joints | XML moving mass (kg) | Station x positions (m) | Finding |
|---|---|---:|---:|---|---|
""" + "\n".join(source_rows) + """

The geometry locations do match the recorded arrangements: M0 has no external fixture; B0 is +/-60 mm; B1 is +/-80 mm; B2 is +/-100 mm; and G1 is +60/+100 mm. Hardware setup photographs also show these qualitative arrangements.

The corrected unactuated copies fix only what is required for a faithful dynamic boundary:

- duplicate mesh/body/geom names are made unique;
- M0 receives a nearly massless numerical output rotor because no external horn/link is installed;
- the weighted link inertia tensor is linearly scaled to the measured 22 g link mass;
- each CAD pin/payload pair is scaled together to the measured 44 g complete-assembly mass, preserving its CAD mass ratio and inertia shape;
- the hinge world axis is flipped from +Y to -Y so positive simulated position matches the recorded encoder/camera sign;
- the assembly is staged at 0.125 m for free visual sweep and all CAD meshes/ground are non-colliding, matching the real fixture's free-sweep mounting rather than treating the drawn plane as a contact surface;
- source orientation is retained: its existing 90-degree X rotation already makes the motor upright and puts the shaft on the horizontal Y axis.

"""
    (DOCS / "XML_HARDWARE_VALIDATION.md").write_text(validation_doc, encoding="utf-8")

    interface_doc = """# Simulation input/output correspondence to hardware

The primary comparison boundary is position command to measured output:

`position_applied_rad(t) -> [position_meas_rad(t), velocity_meas_rad_s(t)]`

For simulation, `position_cmd_rad` is the continuous profile and `position_applied_rad` is rounded to `2*pi/4096` before reaching the actuator. With declared zero command delay, the applied sample is used immediately. Source/Nominal `*_position_meas_rad` and `*_velocity_meas_rad_s` are quantized with the declared encoder resolutions. True state and MuJoCo force channels are retained for audit only.

For recorded hardware, use each canonical `command_events.parquet` file's `t_command_s` and `position_applied_rad`, restricted to `active_profile_sample`, as input. Compare with the canonical `telemetry_events.parquet` primary output `position_meas_rad`; align/interpolate state using the recorded timestamps, never row number alone. Preserve the recorded calibration/model-selection/held-out labels.

C1/C2 and H1-H5 are different namespaces. C1/C2 are SI MuJoCo actuator gains. H1-H5 are raw DYNAMIXEL register settings. Matching profile/configuration labels does not make their numeric gains equivalent. A later hardware replay must either use a separately justified engineering mapping or identify an effective actuator model.

MuJoCo `qfrc_actuator` is simulated joint effort. DYNAMIXEL Present Current in this dataset is input-supply current and is not calibrated output torque. Do not fit or report a torque match until an independent torque calibration exists.
"""
    (DOCS / "SIMULATION_HARDWARE_CORRESPONDENCE.md").write_text(interface_doc, encoding="utf-8")

    versions = f"""Runtime used for this release
Python: {platform.python_version()}
Python executable used: {sys.executable}
MuJoCo: {mujoco.__version__}
NumPy: {np.__version__}
Matplotlib: {matplotlib.__version__}
Platform: {platform.platform()}

Important simulation settings
Physics timestep: {contract['simulation']['physics_timestep_s']} s (500 Hz)
Archived command/state rate: {contract['simulation']['sample_rate_hz']} Hz
Pre-roll: {contract['simulation']['pre_roll_s']} s at first applied command
Integrator: {contract['simulation']['integrator']}
Solver: MuJoCo {mujoco.__version__} compiled/default solver (not overridden in MJCF)
Gravity: 0 0 -{contract['simulation']['gravity_m_s2']} m/s^2
Joint range: {contract['simulation']['joint_range_rad']} rad
Control range: {contract['simulation']['ctrlrange_rad']} rad
Force range: {contract['simulation']['forcerange_Nm']} N*m
Command delay: {contract['simulation']['command_delay_s']} s
Position resolution: {contract['simulation']['position_resolution_rad']} rad
Velocity resolution: {contract['simulation']['velocity_resolution_rad_s']} rad/s
Random sensor noise: disabled
Random seed: {contract['random_seed']}
"""
    (PACKAGE / "01_Versions_and_Settings.txt").write_text(versions, encoding="utf-8")

    readme = f"""# Design2Data

This release contains the exact source, corrected MJCFs, scripts, trajectories, raw synthetic simulation results, indexes, plots, and verification requested for the recorded five-fixture milestone.

Start with `00_Milestone_Note.txt`, then read `docs/XML_HARDWARE_VALIDATION.md` before using any model. The original XMLs are intentionally preserved under `models/supplied_original/`; the directly runnable files are under `models/mechanics_validated_unactuated/` and `models/simulation/`.

Reproduce from the parent project directory with the pinned environment:

```bash
python3 -m venv /tmp/design2data_venv
/tmp/design2data_venv/bin/pip install -r Design2Data/requirements-simulation.txt
/tmp/design2data_venv/bin/python Design2Data/scripts/generate_design2data.py
```

Final verification: **{'PASS' if verification['passed'] else 'FAIL'}**. Simulation episodes: {verification['counts']['simulation_episodes']}. Failed/incomplete simulation runs: 0. Indexed recorded scientific hardware episodes: {verification['counts']['recorded_hardware_scientific_episodes_indexed']}.
"""
    (PACKAGE / "README.md").write_text(readme, encoding="utf-8")


def write_inventory() -> None:
    inventory_path = PACKAGE / "inventory.sha256"
    files = sorted(
        path for path in PACKAGE.rglob("*") if path.is_file() and path != inventory_path
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(PACKAGE)}" for path in files]
    inventory_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    contract = read_json(CONTRACT_PATH)
    np.random.seed(int(contract["random_seed"]))
    clean_generated_outputs()
    supplied = audit_supplied_sources(contract)
    mechanical_paths, mechanical = build_mechanical_models(contract)
    render_mechanical_review(mechanical_paths)
    models, model_records = build_actuated_models(contract, mechanical_paths)
    profiles = build_all_profiles(contract)
    specs, summaries, failures = run_episodes(contract, profiles, models)
    hardware_rows = build_hardware_episode_index()
    create_plots(summaries)
    verification = validate_release(
        contract, supplied, mechanical, model_records, specs, summaries, failures, hardware_rows
    )
    write_documentation(contract, supplied, verification)
    write_inventory()
    print(json.dumps(verification, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
