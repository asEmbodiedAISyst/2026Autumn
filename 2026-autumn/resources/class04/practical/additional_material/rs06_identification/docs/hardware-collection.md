# RS06 hardware collection: plan and procedure

The controller conditions H1 and H2, the trajectory suites and the evidence status of every hardware value are in
`hardware/README.md`. This note gives the run plan, the collection procedure and the order of the campaign.

## Trajectory suites

The two 50 Hz suites P01--P07 in `hardware/trajectory-suites/H1` and `H2` are bound to a hash. The default is
`amplitude_scale=1` and `speed_scale=1`: the shape of each profile is the reference definition. When the hardware
needs a different amplitude or speed, generate a new suite in a new directory with a new revision and write both
scales into the manifest. All accepted repeats of one episode must use the same trajectory hash.

```bash
python scripts/generate_chapter02_rs06_hardware_trajectories.py \
  --controller-id H1 --kp 50 --kd 3.38 --output-dir hardware/trajectory-suites/H1 --overwrite
python scripts/generate_chapter02_rs06_hardware_trajectories.py \
  --controller-id H2 --kp 100 --kd 1.95 --output-dir hardware/trajectory-suites/H2 --overwrite
```

## How many runs

`hardware/frozen-episode-matrix.json` freezes 32 unique combinations. With the minimum number of accepted repeats:

| Split | Unique combinations | Accepted repeats per combination | Minimum successful runs |
| --- | ---: | ---: | ---: |
| calibration | 18 | 3 | 54 |
| model_selection | 8 | 3 | 24 |
| held_out | 6 | 5 | 30 |
| total | 32 | | 108 |

`hardware/minimum-run-plan.csv` lists all 108 run IDs with a dry-run command template. Keep a failed or stopped
run with its reason, but do not count it as an accepted repeat. The real number of runs is usually above 108.

The campaign of 25 August 2026 in `hardware/collected/` follows this plan: one session per fixture, controller
and repeat, each session with the profiles of its split (M0 and B0: three repeats of P01--P03, or P01--P05;
B1: three repeats of P01--P06 plus two more of P06; G1: five repeats of P06--P07). The two static-gravity sessions
of G1 are in `hardware/gravity-collected/`.

## Dry run of one episode

Run the command in the package directory. Replace every placeholder with a value measured on the bench and
reviewed:

```bash
python scripts/run_chapter02_rs06_hardware_collection.py \
  --manifest hardware/trajectory-suites/H1/manifest.json \
  --trajectory-ids P01 \
  --run-id m0_h1_p01_repeat01 \
  --fixture-id M0 \
  --fixture-description "RS06 motor-only, fixture revision ..." \
  --fixture-metadata-json hardware/fixture-m0.json \
  --port /dev/ttyACM0 --motor-id 2 \
  --center-position '<CALIBRATED_CENTER_RAD>' \
  --position-min '<MECHANICAL_MIN_RAD>' \
  --position-max '<MECHANICAL_MAX_RAD>' \
  --max-initial-center-distance '<STARTUP_LIMIT_RAD>' \
  --max-position-deviation '<REVIEWED_PROFILE_LIMIT_RAD>' \
  --max-abs-velocity '<ABORT_VELOCITY_RAD_S>' \
  --max-abs-torque '<ABORT_TORQUE_NM>' \
  --max-tracking-error '<ABORT_TRACKING_ERROR_RAD>' \
  --output-dir hardware/collected/m0_h1_p01_repeat01
```

Without `--execute` the script does not open the serial port and does not write data. Check the manifest hash,
the gains, the centre, the mechanical limits, the feedback thresholds and the output directory in its output.
Then add `--execute` at the end of the same command.

The definition of P06 has steps of the centre offset at 3.5 s and 7.3 s. At `amplitude_scale=1` the peak of the
discrete target acceleration at 50 Hz is about `354.4 rad/s^2`. A real run of P06 also needs
`--acknowledge-p06-position-steps`. This flag only records that the operator has reviewed the steps; it does not
reduce the risk and does not smooth the trajectory. The maximum static gravity torque of G1 is about `1.266 N m`
and needs its own review.

## What each run must record

The minimum fixture record is the table "Measured-fixture record" of `hardware/README.md`. In addition, each run
needs: the run ID, the repeat ID, the operator, the faults, the lost frames, and each manual exclusion with its
reason. The collector saves the requested, encoded, acknowledged and measured position, the feedback velocity, the
firmware torque estimate, the three clock relations, the raw uint16 fields, the complete raw record, and the
saturation and validity flags. `torque_feedback_Nm` is not an independent measurement of the output torque.

## G1 free-fall

The package has no free-fall collection script. A protocol of the user must write the CSV and metadata fields of
`hardware/g1-free-fall-schema.json`. In particular:

- "drive enabled with KP = KD = 0" and a real torque-disable are different conditions;
- keep the release boundary, the release angle and direction, and the raw protocol fields;
- free-fall data is supporting calibration data; it does not replace the closed-loop G1/P06 and G1/P07 episodes
  of the frozen matrix.

## Recommended order

1. Dry runs and safety acceptance with M0/P01 under H1 and H2.
2. Calibration of M0, B0 and B1: three accepted repeats of each combination.
3. Freeze the preprocessing, the fixture revisions and the controller context.
4. Model selection with B0 and B1; freeze the model again after the selection.
5. Held-out runs with B1 and G1 last: five accepted repeats of each combination, with no parameter change
   during this stage.
6. Keep the G1 free-fall data separate; do not mix it into the hardware-position archive.
