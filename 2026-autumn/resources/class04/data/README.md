# Saved XC330 evidence for Class 04

These files contain the **98 g XC330 Real-Position v2 campaign**. They support the Class 04 demonstration and saved-output activity. The supplied analysis reads frozen predictions: it does not fit parameters, run MuJoCo, or operate hardware.

From `2026-autumn/resources/class04` in the cloned repository, run:

```bash
python3 code/analyze_episode.py
```

This analyses the G1 activity episode and writes `activity-output/metrics.json` and, when Matplotlib is available, an overlay and residual plot. Metrics require only Python's standard library:

```bash
python3 code/analyze_episode.py --no-plot
```

To analyse the balanced comparison episode:

```bash
python3 code/analyze_episode.py --episode data/xc330-98g-H1-B1-P06-R01.csv --output-dir activity-output-B1
```

The plotting environment used here is recorded in [`requirements-analysis.txt`](../code/requirements-analysis.txt). Correct analysis of the saved figures and metrics receives the same activity credit as running the command.

## Episodes and scoring contract

| File | Exact source episode identity | Context |
|---|---|---|
| `xc330-98g-H1-G1-P06-R01.csv` | `G1__H1__P06_heldout_composite__R01` | Main activity: H1, eccentric G1 fixture, P06 composite profile, first held-out repeat |
| `xc330-98g-H1-B1-P06-R01.csv` | `B1__H1__P06_heldout_composite__R01` | Balanced comparison: H1, B1 fixture, same named P06 profile and repeat |

Each CSV contains 1,100 samples at a nominal 0.01 s interval, from 0 to 10.99 s. Time zero is the first retained point on the processed active-episode grid, not the instant the device was powered on. The source adapter first retains the overlap of active command time and telemetry time. It holds external goals with zero-order hold and linearly interpolates references and telemetry onto the 100 Hz grid. Preparation and return commands are outside this active-episode window.

Score **all supplied samples**. No further filtering, time shifting, alignment optimization, burn-in exclusion, or validity mask is applied here. In particular, independently shifting a simulation to make it look closer would change the comparison contract.

Matching H1/P06/R01 controls the named campaign contexts. The two physical episodes still have their own recorded references, measured initial states and acquisition histories. Their comparison supports investigation of condition dependence; it does not uniquely prove which physical effect caused the difference.

## CSV column guide

All angular positions share the source campaign's joint-coordinate convention and use radians. Velocity uses rad/s. The symbol `qhat` below denotes the model's predicted position, conventionally written as an accented q in the notes.

| CSV column | Symbolic alias | Meaning |
|---|---|---|
| `time_s` | `t` | Seconds from the processed active-episode start |
| `external_goal_rad` | `q_d` | External application Goal Position, preserved as the command context; not the replay's direct input |
| `internal_position_reference_rad` | `q_r` | Recorded internal Position Trajectory; input to the declared feedback approximation |
| `internal_velocity_reference_rad_s` | `v_r` | Recorded internal Velocity Trajectory; this separate firmware field is used directly, rather than differentiating the interpolated `q_r` |
| `physical_position_rad` | `y_q` | Recorded physical position, interpolated onto the analysis grid |
| `physical_velocity_rad_s` | `y_v` | Recorded physical velocity telemetry, interpolated onto the analysis grid; its initial value initializes the replay |
| `simulated_M1_position_rad` | `qhat_M1` | Native MuJoCo position replay using the published frozen M1 integral-regression candidate |
| `simulated_M2_position_rad` | `qhat_M2` | Native MuJoCo position replay using the published frozen M2 simulation output-error candidate |
| `M1_residual_rad` | `r_M1 = qhat_M1 - y_q` | Signed model-to-physical discrepancy for M1 |
| `M2_residual_rad` | `r_M2 = qhat_M2 - y_q` | Signed model-to-physical discrepancy for M2 |

The uppercase `M1`/`M2` identifiers in these column names map to `method1`/`method2` in the source publication's tables. They are fitted candidates, not an arbitrary nominal-model baseline. Tracking errors such as `q_d - y_q` and `q_r - y_q` answer different questions from the prediction residual `qhat - y_q`.

## Fixed physical model and controller

The campaign fixture contains one 0.006 kg link, two 0.004 kg pins and two 0.042 kg payloads: **0.098 kg total added moving mass**. B1 uses payload centres at −80 and +80 mm; G1 uses +60 and +100 mm in the fixture's naming convention. The source MuJoCo geometry has its own declared signed first-moment convention, recorded in the configuration file.

This differs from the reviewed Class 03 example: that example uses a 22 g link and two complete 44 g pin/payload assemblies, totalling 110 g. Reused fixture labels do not make the mass properties identical. Class 04's numerical evidence uses this 98 g record throughout.

H1 uses firmware registers P=600, I=0, D=150 in Current-Based Position Control (Mode 5). The fixed engineering conversion gives `Kp=1.57983562710739 N m/rad`, `Kv=0.20211461523105595 N m s/rad` and an effort limit of ±0.1551 N m. These values are assumptions of the replay model; gain registers are not copied directly as SI gains. Current-to-effort conversion is not an independent measurement of shaft torque.

MuJoCo uses `implicitfast`, a 0.002 s step and gravity of 9.81 m/s². Every episode starts at its first processed physical position and velocity. The recorded internal references are held at the preceding analysis sample over each set of five simulation substeps. H1's frozen candidates are:

| Parameter | Unit | M1 integral regression | M2 output-error fitting |
|---|---|---:|---:|
| Armature | kg m² | 0.010706886765349692 | 0.00632962729586566 |
| Damping | N m s/rad | 0.03647832779506367 | 0.04256643460373195 |
| Friction loss | N m | 0.010226937934345186 | 0.007363036739462707 |

These effective parameters belong to the declared model and controller context. They are not measurements of three isolated motor constants. No fitting occurred during this export or student analysis.

## Saved outputs and source records

| File | Purpose |
|---|---|
| `xc330-98g-selected-episode-metrics.json` | Native replay results for both selected episodes, with exact agreement checks against published scores |
| `xc330-98g-activity-saved-metrics.json` | Saved result from the standalone analysis command for the G1 activity |
| `xc330-98g-model-config.json` | Fixtures, controller assumptions, frozen candidates and replay/scoring choices |
| `xc330-98g-heldout-condition-metrics.csv` | Equal-episode means derived from published per-episode results, explicitly separated into B1/P06, G1/P06, G1/P07 and G1/P06+P07 groups under H1 and H2 |
| `xc330-98g-published-episode-metrics.csv` | Unchanged per-episode published frozen prediction metrics, enabling independent regrouping |
| `xc330-98g-published-aggregate-metrics.csv` | Unchanged published split-level equal-episode means; held-out means mix B1/P06 and G1/P06/P07 |
| `xc330-98g-published-fixture-split-metrics.csv` | Unchanged source fixture/split means; B1 held-out is P06 only, whereas G1 held-out combines P06 and P07 |
| Other `xc330-98g-published-*.csv` files | Unchanged source mass properties, controller conditions, parameters and repeatability context |
| `xc330-98g-source-manifest.json` | Source repository/commit, immutable archive/adapter hashes, exported file hashes and runtime versions |

The underlying source is the [PhyIntel repository](https://github.com/asMagicBrain/PhyIntel) at commit `9821dae9cb14ecfcd9fde3f97f14308a21f5bc00`. This export uses the recovered, lossless NPZ representation of the source adapter's output, not raw telemetry and not the separate 110 g consolidation package. Actual MuJoCo predictions were regenerated through the unchanged native replay engine with the frozen source parameters. All four selected position RMSEs exactly match the supplied published values in the recorded NumPy/MuJoCo runtime.
