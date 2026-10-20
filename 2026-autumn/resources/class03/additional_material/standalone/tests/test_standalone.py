from pathlib import Path

import mujoco

ROOT = Path(__file__).resolve().parents[1]


def test_all_models_load_and_have_one_axis() -> None:
    for config in ("M0", "B0", "B1", "B2", "G1"):
        model = mujoco.MjModel.from_xml_path(str(ROOT / "models" / f"1DOF-{config}.xml"))
        assert (model.nq, model.nv, model.nu) == (1, 1, 1)
        assert int(((model.geom_contype != 0) | (model.geom_conaffinity != 0)).sum()) == 0


def test_measurement_record_is_included() -> None:
    text = (ROOT / "measurements" / "AS_BUILT_DIMENSIONS_MASSES_AND_POSITIONS.txt").read_text()
    assert "B2" in text and "110 g" in text and "+100 mm" in text



def test_xc330_setup_choices_are_validated() -> None:
    import sys
    sys.path.insert(0, str(ROOT / "simulation_and_hardware"))
    from xc330_setup import BAUD_RATE_CODES, require_motor_id, require_supported_baud

    assert BAUD_RATE_CODES[4_000_000] == 6
    assert require_supported_baud(1_000_000) == 1_000_000
    assert require_motor_id(252, "target") == 252
    import pytest
    with pytest.raises(ValueError):
        require_supported_baud(123456)
    with pytest.raises(ValueError):
        require_motor_id(254, "target")
