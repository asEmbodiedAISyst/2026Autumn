# RS06 Hardware Configuration and Measured-Fixture Record

The JSON files under [`fixture-metadata/`](fixture-metadata/) are the
machine-readable source of truth. Values marked **CAD-derived** come from the
supplied Fusion/MJCF export and are not independent measurements of the
as-built fixture. Unknown physical facts are explicitly marked **Not recorded**.

## Evidence status terms

| Term | Meaning |
|---|---|
| CAD-derived | Calculated from the supplied Fusion/MJCF mass, center of mass, inertia tensor, joint position, and joint axis. |
| Collected | Recorded by the RS06 collection software in a captured run. |
| Operator-confirmed | Must be checked against the physical assembly before an accepted run. |
| Not recorded | No qualified value is currently present; it must not be inferred. |

## Hardware configuration family

| ID | Physical configuration | Identification role | External moving mass (kg) | External inertia about `rs06_joint` (kg m^2) | Signed gravity first moment (kg m) | Maximum gravity torque at 9.81 m/s^2 (N m) | Evidence and model |
|---|---|---|---:|---:|---:|---:|---|
| M0 | RS06 output with no external moving load | Motor-only pilot and low-inertia calibration | 0 | 0 | 0 | 0 | [Metadata](fixture-metadata/M0.json); [source MJCF](../source-assets/mjcf/test_station_no_payload/test_station_no_payload.xml) |
| B0 | Balanced link without the two large end payloads | Lower-inertia balanced calibration and model selection | 0.6872134493 | 0.0129095290 | -0.0000365552 | 0.0003586060 | [Metadata](fixture-metadata/B0.json); [source MJCF](../source-assets/mjcf/test_station_balanced_link/test_station_balanced_link.xml) |
| B1 | Balanced link with both large end payloads installed | Higher-inertia calibration, model selection, and held-out P06 | 2.4072134493 | 0.0576790352 | -0.0000365552 | 0.0003586060 | [Metadata](fixture-metadata/B1.json); [source MJCF](../source-assets/mjcf/test_station_balanced_payload/test_station_balanced_payload.xml) |
| G1 | Fixed one-sided payload | Asymmetric held-out transfer and static-gravity reference | 1.5472134493 | 0.0352942821 | -0.1290365552 | 1.2658486060 | [Metadata](fixture-metadata/G1.json); [source MJCF](../source-assets/mjcf/test_station_one_payload/test_station_one_payload.xml) |

The listed inertia is the **external moving-fixture inertia** about the joint
axis. It excludes RS06 rotor/output-side equivalent inertia and excludes the
MuJoCo joint `armature`; those terms must not be added twice. B0 and B1 are
effectively balanced, not mathematically perfect. M0 uses a nonphysical MuJoCo
regularizer of `1e-6 kg` and `1e-12 kg m^2`; it is not a measured payload.

## Fixed controller conditions

| Controller | Motor mode | KP | KD | Position-command and collection rate | Manifest | Intended comparison |
|---|---|---:|---:|---:|---|---|
| H1 | Position | 50.0 | 3.38 | 50 Hz | [`trajectory-suites/H1/manifest.json`](trajectory-suites/H1/manifest.json) | Primary controller condition |
| H2 | Position | 100.0 | 1.95 | 50 Hz | [`trajectory-suites/H2/manifest.json`](trajectory-suites/H2/manifest.json) | Independent higher-KP/lower-KD condition |

KP and KD are RS06 command-interface settings, not independently calibrated SI
stiffness and damping coefficients. H1 and H2 are frozen independent hardware
contexts. Identification must not tune these values to reduce a model output
gap, and results for H1 and H2 must not be silently averaged.

### Shared hardware and collection context

| Field | Current campaign value | Evidence status |
|---|---|---|
| Actuator model | RS06 | Collected |
| Motor CAN ID | 2 | Collected |
| Controller slot / route | Slot 1, FLRL / CAN1 | Collected |
| Transport | MagicLimb control box 16-slot protocol, `observed-2026-08-08` | Collected |
| Serial configuration | `/dev/ttyACM0`, 1,000,000 baud in the captured campaign | Collected; port is host-specific |
| Command and sample rate | 50 Hz | Frozen manifest and collected metadata |
| Position center | 0 rad | Configured; physical zero alignment requires operator confirmation |
| Configured position bounds | -12.57 to +12.57 rad | Software safety configuration, not evidence of physical hard stops |
| Torque channel | RS06/firmware torque estimate | Collected but unqualified; not an independent shaft-torque measurement |


## Measured-fixture record

The course requires the physical embodiment to be traceable, not merely named.
For an accepted as-built RS06 fixture revision, preserve the following fields.

| Required field | Current RS06 record | Required action or interpretation |
|---|---|---|
| Fixture ID and description | M0, B0, B1, and G1 are defined above | Confirm that the installed assembly matches the selected ID before every run. |
| Assembly revision | Not recorded | Assign a stable revision for each physical link/payload assembly. |
| Mounting revision | Not recorded | Record hub, adapter, fastener, and mounting-orientation changes separately. |
| Installed components and payload-center distances | Geometry is present in the hash-bound MJCF and meshes | Measure the as-built payload centers from the joint axis and record sign/orientation. |
| Installed moving mass | CAD-derived values are listed above | Weigh the actual installed moving assembly or its individual parts and report the method and resolution. |
| Center of mass and joint-axis inertia | CAD-derived in each metadata JSON | Recalculate from measured masses/geometry or measure independently; include uncertainty. |
| Signed gravity first moment | CAD-derived in each metadata JSON | Confirm the physical zero, gravity direction, and sign on the bench. |
| Maximum gravity torque | `9.81 * abs(signed first moment)` | Treat G1 as a static reference, not as a dynamic torque transducer. |
| Joint axis | MJCF axis `[-1, 0, 0]` at body-frame position `[0.0015, 0, 0]` m | Confirm that the physical installation uses the same axis and sign convention. |
| Zero definition and positive direction | MJCF `q=0`; collection center is 0 rad | Photograph/mark the physical zero and verify increasing position direction. |
| Mechanical range and collision clearance | Physical hard stops are not recorded; MJCF range is -1.1 to +1.1 rad | Measure the safe as-built range; do not substitute the configured +/-12.57 rad software bounds. |
| Mass-property uncertainty | Not recorded | Record scale resolution, distance uncertainty, calculation method, and resulting inertia/first-moment uncertainty. |
| Fastener and balance check | Not recorded | Record torque/retention method and confirm B0/B1 balance before accepted collection. |
| Motor serial or asset ID | Not recorded | Photograph and enter the identifier for the RS06 used in the campaign. |
| Fixture photos or drawings | One inspected CAD render per fixture is present and hash-bound | Keep the renders as design-intent evidence; add physical as-built photographs separately. |

### Visual evidence locations and status

| Evidence | Current file or directory | Current status and additional useful views |
|---|---|---|
| Shared station and actuator | `fixture-metadata/evidence/photos/common/` | No shared physical photos yet; add test-station overview, RS06 nameplate/serial, control box, and joint interface |
| M0 | `fixture-metadata/evidence/photos/M0.jpg` | CAD render recorded; add physical motor-only assembly, joint mount, and marked zero pose |
| B0 | `fixture-metadata/evidence/photos/B0.jpg` | CAD render recorded; add physical overall assembly, both sides of the balanced link, joint mount, and zero pose |
| B1 | `fixture-metadata/evidence/photos/B1.jpg` | CAD render recorded; add physical overall assembly, left and right payload mounting, joint mount, and zero pose |
| G1 | `fixture-metadata/evidence/photos/G1.jpg` | CAD render recorded; add physical overall assembly, one-sided payload and its orientation, joint mount, and zero pose |

The four current JPEG files are CAD-rendered assembly views, so the metadata
classifies them as `cad_render` with `as_built_photograph: false`. Use stable
names without spaces for future physical evidence, for example
`G1/g1_as_built_overview.jpg` and `common/rs06_nameplate.jpg`. Do not place
fixture photos inside a captured run directory; the sidecar metadata binds them
to the relevant fixture revision.

## Five-development-layer evidence review

| Development layer | RS06 requirement | Evidence currently preserved | Remaining boundary |
|---|---|---|---|
| 1. Physical Embodiment | Build and qualify M0/B0/B1/G1; preserve measured mass, payload centers, center of mass, joint-axis inertia, signed G1 coordinate, zero, range, and revision | Hash-bound Fusion MJCF, meshes, CAD-derived mass properties, and fixture sidecars | Independent as-built measurements, revisions, physical range, sign audit, and photos remain pending |
| 2. Sensing and Actuation | Preserve command, transmitted/acknowledged target, measured position/velocity, timing, validity, controller condition, status, and available effort context | Raw position commands and echoes, measured position/velocity, firmware torque estimate, timestamps, safety flags, H1/H2 identity | Current, PWM, voltage, temperature, firmware revision, and independent torque are unavailable or not recorded |
| 3. Computation and Representation | Keep raw streams immutable and make every conversion, trajectory manifest, schema, and controller/fixture mapping versioned | Raw CSV, episode CSV/NPZ, trajectory manifests, experiment contracts, verification files, and SHA-256 bindings | Any future conversion or exclusion rule must receive a new version and must not overwrite raw evidence |
| 4. Robo-Physical Learning and Task Validation | Fit and evaluate H1 and H2 independently using frozen calibration, model-selection, and held-out roles | [`frozen-episode-matrix.json`](frozen-episode-matrix.json) defines the adapted 32-combination matrix; G1 static-gravity runs are separate supporting evidence | B2 is unavailable; G1 transfer and torque conclusions must remain within the declared evidence boundary |
| 5. Lifecycle Evidence | Bind design, data, models, methods, decisions, limitations, and source revisions into one traceable release | Fixture metadata, run-binding manifest, source hashes, contracts, per-run verification, and documentation | Add as-built measurements/photos and record any hardware or firmware change as a new revision |

## Traceability files

| Purpose | File |
|---|---|
| Hardware-matched MJCF and mesh snapshots | [`model-sources/`](model-sources/) |
| Fixture sidecars and captured-run bindings | [`fixture-metadata/manifest.json`](fixture-metadata/manifest.json) |
| Adapted hardware episode matrix | [`frozen-episode-matrix.json`](frozen-episode-matrix.json) |
| Hardware trajectory manifests | [`trajectory-suites/H1/manifest.json`](trajectory-suites/H1/manifest.json), [`trajectory-suites/H2/manifest.json`](trajectory-suites/H2/manifest.json) |
| Dynamic collected runs | [`collected/`](collected/) |
| Static-gravity collected runs | [`gravity-collected/`](gravity-collected/) |
