# Class 03 TA guide — XC330 B0 collection and connection setup

## Purpose and safety boundary

Students use simulation and the embedded V5 record. The TA station demonstrates the physical B0 XC330 collection. Keep the fixture clear, use its mechanical range, and run only one program that owns the serial port at a time.

The Class 03 hardware profile is copied from V5:

- motor: XC330-M288-T, model number `1240`, firmware `53`;
- V5 default: ID `5`, `4,000,000` bps, register baud value `6`;
- operating mode `5`: Current-Based Position Control;
- guarded teaching envelope: raw ticks `1024` through `3072`.

The supplied U2D2 serial path and all runtime files are local to this project in `config/hardware.example.toml` and `hardware_runtime/`.

## Setup once

```bash
uv sync
uv run pytest
```

## 1. Scan, then configure ID, baud rate, and operating mode

Open the desktop visualizer:

```bash
uv run python simulation_and_hardware/xc330_setup.py --visualizer
```

Click **Scan connected XC330** first. It searches every XC330-supported baud rate without writing anything and fills the detected motor ID and baud automatically. Then select the desired ID, baud rate, and operating mode. For Class 03, choose mode `5` (Current-Based Position Control).

The visualizer supports the XC330 values `9,600`, `57,600`, `115,200`, `1,000,000`, `2,000,000`, `3,000,000`, `4,000,000`, and `4,500,000` bps. The V5 teaching station should remain at ID `5` and `4,000,000` bps unless you intentionally have a different station.

For terminal-only use, this is a read-only inspection:

```bash
uv run python simulation_and_hardware/xc330_setup.py --scan

# Automatically find the one connected XC330 and read it
uv run python simulation_and_hardware/xc330_setup.py --auto-detect --inspect
```

To set the full V5 profile from the automatically detected XC330, use the desired values and the explicit confirmation phrase:

```bash
uv run python simulation_and_hardware/xc330_setup.py \
  --auto-detect --id 5 --baud 4000000 --operating-mode 5 \
  --apply --confirm APPLY_XC330_CONFIG
```

Before applying a change, leave exactly one XC330 connected and disconnect any other motor that uses the target ID. The tool broadcast-pings for collisions, disables torque, writes only the selected ID, baud, and operating-mode registers, closes the old connection, reconnects with the requested values, and verifies readback. It never sends a position or velocity command.

If a baud change fails verification, reconnect using the old values first. Do not guess a `/dev/ttyUSB*` path: use the stable U2D2 path in the local config. Stop if supply voltage is outside 4.5–5.5 V, temperature is high, a hardware error is reported, or another application owns the port.

## 2. Demonstrate guarded B0 collection

First show the configuration without opening the port:

```bash
uv run python simulation_and_hardware/live_b0_collection.py
```

For the supervised physical demonstration, verify that the fixture is clear and then explicitly permit torque and motion:

```bash
uv run python simulation_and_hardware/live_b0_collection.py --enable-motion --seconds 8
```

This opens a focused live MuJoCo B0 twin while it collects the bounded 0.18 Hz physical trace. The CSV includes physical telemetry and `simulation_position_rad`; torque-off cleanup runs even if it stops early. Use `--no-viewer` only for headless troubleshooting.

## V5 campaign boundary

The original V5 B0 campaign is a multi-condition experiment (H1–H5, P01–P06, and repeats), rather than one longer safe teaching motion. The default 8-second command remains the supervised classroom demo. Select the exact controller/profile/repeat subset before scheduling a full physical campaign.

## 3. Connect it to the student result

Run the visual simulation comparison beside the hardware station. It opens the focused MuJoCo B0 XC330 view and a live cyan-hardware/orange-MuJoCo/red-residual dashboard:

```bash
uv run python simulation_only/b0_data_collection.py
```

Emphasize that the resulting pre-identification gap is expected. Class 04 uses the included record to fit parameters; Class 03 does not claim that the prepared model has been identified.

