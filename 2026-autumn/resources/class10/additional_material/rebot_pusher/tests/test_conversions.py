import numpy as np

from rebot_sim.robot import (
    DIRECTIONS,
    action_to_motor_deg,
    gripper_m_to_motor_deg,
    motor_deg_to_action,
    motor_deg_to_sim,
    sim_to_motor_deg,
)


def test_roundtrip():
    q = np.array([0.1, 1.2, 1.0, -0.5, 0.3, -0.2])
    motor = sim_to_motor_deg(q, 0.02)
    q2, g2 = motor_deg_to_sim(motor)
    np.testing.assert_allclose(q2, q)
    assert abs(g2 - 0.02) < 1e-12
    np.testing.assert_allclose(action_to_motor_deg(motor_deg_to_action(motor)), motor)


def test_real_follower_convention():
    """Real datasets: state ~ action * [1, 1, -1, -1, -1, 1, 6]; gripper action 0..45 <-> motor 0..270 <-> 0..0.05 m."""
    np.testing.assert_allclose(DIRECTIONS, [1, 1, -1, -1, -1, 1, 6])
    assert gripper_m_to_motor_deg(0.05) == 270
    action = np.array([0, 90, -60, 30, 0, 0, 45.0])
    np.testing.assert_allclose(action_to_motor_deg(action), [0, 90, 60, -30, 0, 0, 270])


def test_action_clipped_to_soft_limits():
    motor = action_to_motor_deg(np.array([500, 500, -500, 500, 500, 500, 500.0]))
    assert motor[0] == 145 and motor[1] == 170 and motor[2] == 200 and motor[6] == 270
