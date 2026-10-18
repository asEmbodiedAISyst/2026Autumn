# XC330 motor-only demonstration record

One physical episode supplied in Mohamad Halwani's Class 02 material at Assistants commit `f7c118edaadc9f33498669736fa9d99160ff629a`:

- Episode: `M0__H2__P01_slow_triangle__R01`, recorded 1 September 2026.
- Device: XC330-M288-T, model 1240, ID 5, firmware 53.
- Configuration: current-based position mode 5, H2 P/I/D register values 800/0/150; baud selection 6 (4 Mbit/s).
- Fixture: M0, no external horn, link, pin or payload. This does not eliminate internal rotor/transmission inertia or friction.
- Contents: 2,601 telemetry rows and 1,301 command rows, approximately 13 seconds. Original Parquet and JSON files are retained under `raw/`.

The CSV files preserve every source row and column. Use [telemetry_events.csv](telemetry_events.csv) to inspect the measured record and the [worked example](../../telemetry-worked-example.md) for conversions and interpretation. The original hardware tables are supplied by the [selected Class 02 package](https://github.com/asEmbodiedAISyst/2026Autumn/tree/main/2026-autumn/resources/class02/practical/additional_material/data/hardware/xc330_physical_demo). Reading the CSV does not require a simulation or authoring script.

`t_state_s` is the host receive-end time relative to the episode origin. Host request time, receive-end time and device Realtime Tick are different clocks/observations. Polling at approximately 200 Hz does not establish the internal servo-loop frequency. The source `episode.json` has its own timing-quality calculation; our audit explicitly uses receive-end intervals.

Position is reported relative to raw count 2048. Velocity/current/PWM fields in the supplied Parquet and CSV are already signed; no additional sign decoding is applied. Present Current is XC330 input-supply telemetry. Neither that value nor a nominal motor constant supplies an independent output-torque measurement.

The classroom photo/CAD pair illustrates the platform; it is not asserted to be a synchronized camera view of this episode. Camera/video paths named by the original manifest are not bundled or used as pose measurements. There is no video-based angle validation here.
