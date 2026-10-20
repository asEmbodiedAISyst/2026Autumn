from pathlib import Path

import mujoco
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_models_and_compact_episode() -> None:
    for family in ("Synthetic_Baseline", "Hardware_Fitted"):
        model = mujoco.MjModel.from_xml_path(str(ROOT / "models" / family / "H2" / "B1.xml"))
        assert (model.nq, model.nu) == (1, 1)
    frame = pd.read_csv(ROOT / "data" / "minimal_heldout_episode_B1_H2_P06_R01.csv.gz")
    assert len(frame) == 2200
    assert set(frame["split"]) == {"held_out"}


def test_frozen_fit_improves_selected_episode() -> None:
    frame = pd.read_csv(ROOT / "data" / "minimal_heldout_episode_B1_H2_P06_R01.csv.gz")
    baseline = np.sqrt(np.mean((frame.synthetic_baseline_position_rad - frame.hardware_position_rad) ** 2))
    fitted = np.sqrt(np.mean((frame.hardware_fitted_position_rad - frame.hardware_position_rad) ** 2))
    assert fitted < baseline
