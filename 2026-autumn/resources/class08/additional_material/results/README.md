# Results: motion test of the physical arm

`motion_test_20261010_000129.json` is the log of `code/real_gripper_motion_test.py --can-port can0 --joints 2`
on the course arm (reBot Arm B601-RS with gripper), 10 October 2026. Joint 2 (shoulder_lift) is an RS-06 motor.

| Field | Content | Unit |
| --- | --- | --- |
| `hold.pose_deg` | the 7 motor angles while the arm holds the zero pose | deg |
| `hold.feedforward_nm` | the model gravity torque g(q) of joints 1-6 | N m |
| `hold.measured_torque_nm` | the torque that the 7 motors report | N m |
| `hold.model_error_nm` | kp * (target - measured): the torque that the model g(q) did not give | N m |
| `gravity_sweep` | joint 2 held at 0, 10, 20, 30 deg: target, measured angle, g(q), model error | deg, N m |
| `gravity_fit.shoulder_lift` | `[a, b]` of the fit a*cos(q2) + b*sin(q2) of the model error | N m |
| `gravity_fit.max_residual_nm` | the largest residual of the fit | N m |
| `joints` | per tested joint: amplitude, speed, worst tracking error, peak torque, MOSFET temperature | deg, deg/s, deg, N m, deg C |
| `args` | the command-line options of the run | - |
| `kp` | the MIT stiffness of each motor (soft gains, about 1/3 of the vendor values) | N m/rad |

Result: worst tracking error 1.9 deg at +-10 deg and 5 deg/s, peak torque 1.9 N m, 27 deg C. The sweep spans only
30 deg, so the sine term b of the gravity fit is not reliable (the script asks for 45 deg or more).
