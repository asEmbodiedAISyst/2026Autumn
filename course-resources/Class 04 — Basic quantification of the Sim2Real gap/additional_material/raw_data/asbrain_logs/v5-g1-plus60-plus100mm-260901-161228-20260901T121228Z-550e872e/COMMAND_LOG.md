# Command log

- `2026-09-01T12:24:24.637535+00:00`: `collect_g1.py --run`
- Camera readiness was required before the Dynamixel device could open: `True`.
- The computer-side asMagic receiver retained 22 camera session(s); per-session indexes report the exact JPEG, depth, and AR CSV availability. It did not control the iPhone app's local Record button.
- Corrected fixture: two complete 44 g payloads at +60 mm and +100 mm, plus one 22 g link, 110 g total external moving mass.
- Operator-declared U2D2 USB latency timer: `1 ms`.
- Read-only sysfs latency preflight: `passed=True`, `observed=1 ms`, path `/sys/class/tty/ttyUSB1/device/latency_timer`. It completed before camera startup or motor-device open.
- Every successful episode actively acquired measured raw tick 2048 under torque before experimental recording.
- Collection status before independent verification: `complete`; error: `None`.
- Held out: `20/20`; pilots: `2/2`.
- Camera sessions finalized: `22/22`.
- Logged torque-off gravity-rest intervals: `22`.
- P06/P07 remained excluded from identification and model-selection decisions.
- Terminal torque disabled: `True`.
- Video finalization, when applicable, ran only after the motor bus was closed.
