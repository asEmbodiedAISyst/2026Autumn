from __future__ import annotations

import json
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data/chapter-02/releases/rs06-sim-data-v1"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Rs06Chapter02ReleaseTests(unittest.TestCase):
    def test_source_mjcf_contract(self) -> None:
        paths = sorted((ROOT / "source-assets/mjcf").glob("*/*.xml"))
        self.assertEqual(len(paths), 4)
        for path in paths:
            root = ET.parse(path).getroot()
            self.assertIsNotNone(root.find(".//joint[@name='rs06_joint']"), path)
            self.assertIsNotNone(root.find(".//actuator/position[@name='rs06_position']"), path)
            self.assertEqual(root.find("compiler").get("inertiafromgeom"), "false")

        m0 = ET.parse(ROOT / "source-assets/mjcf/test_station_no_payload/test_station_no_payload.xml").getroot()
        visual = m0.find(".//geom[@name='playload-1_visual']")
        inertial = m0.find(".//body[@name='playload-1']/inertial")
        self.assertEqual((visual.get("density"), visual.get("contype"), visual.get("conaffinity")), ("0", "0", "0"))
        self.assertEqual(float(inertial.get("mass")), 1.0e-6)
        self.assertEqual(inertial.get("diaginertia"), "1e-12 1e-12 1e-12")

    def test_modified_matrix_and_generated_data(self) -> None:
        contract = read_json(RELEASE / "experiment-contract.json")
        manifest = read_json(RELEASE / "sim-position-manifest.json")
        torque = read_json(RELEASE / "sim-torque-manifest.json")
        self.assertEqual(set(contract["fixtures"]), {"M0", "B0", "B1", "G1"})
        self.assertNotIn("B2", contract["fixtures"])
        self.assertEqual(manifest["episode_count"], 32)
        self.assertEqual(Counter(e["split"] for e in manifest["episodes"]), Counter({"calibration": 18, "model_selection": 8, "held_out": 6}))
        self.assertEqual(torque["episode_count"], 32)
        self.assertEqual(torque["sample_count"], 170652)
        self.assertTrue(read_json(RELEASE / "verification.json")["passed"])

    def test_hardware_controller_and_repeat_plan(self) -> None:
        h1 = read_json(ROOT / "hardware/trajectory-suites/H1/manifest.json")["control_configuration"]
        h2 = read_json(ROOT / "hardware/trajectory-suites/H2/manifest.json")["control_configuration"]
        self.assertEqual((h1["controller_id"], h1["kp"], h1["kd"]), ("H1", 50.0, 3.38))
        self.assertEqual((h2["controller_id"], h2["kp"], h2["kd"]), ("H2", 100.0, 1.95))
        plan = read_json(ROOT / "hardware/frozen-episode-matrix.json")
        self.assertEqual(plan["unique_episode_count"], 32)
        self.assertEqual(plan["minimum_accepted_physical_run_count"], 108)
        with (ROOT / "hardware/minimum-run-plan.csv").open(encoding="utf-8") as handle:
            self.assertEqual(sum(1 for _ in handle) - 1, 108)

    def test_results_and_free_fall_boundary(self) -> None:
        position = read_json(RELEASE / "sim-position-results-v1/result.json")
        self.assertFalse(position["simulation_predictive_acceptance"]["sim_position_m1"]["accepted"])
        self.assertTrue(position["simulation_predictive_acceptance"]["sim_position_m2"]["accepted"])
        schema = read_json(ROOT / "hardware/g1-free-fall-schema.json")
        self.assertFalse(schema["relationship_to_frozen_matrix"]["part_of_32_closed_loop_episodes"])
        self.assertIn("release_event", schema["csv"]["required_columns"])


if __name__ == "__main__":
    unittest.main()
