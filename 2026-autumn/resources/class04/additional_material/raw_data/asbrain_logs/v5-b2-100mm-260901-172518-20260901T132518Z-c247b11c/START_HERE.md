# START HERE — B2 XC330 experiment

This folder distributes retained motor records from the B2 campaign. The original campaign also reported synchronized iPhone capture; that original capture report and this release’s contents have different scopes.

## What was installed

- Motor: XC330-M288-T, ID 5.
- Fixture: balanced equal payloads centered at -100 mm and +100 mm.
- Moving mass declared for this run: 110 g.
- Experiment zero is measured encoder tick 2048 ±5 under torque; the balanced fixture does not use G1's torque-off gravity-rest rule.

## Original run status

- Collection status before independent verification: **complete**.
- Campaign error: none.
- Read-only host timing gate: passed=True; observed latency=1 ms.
- Planned motion-and-media episodes: 60.

## Distribution scope

This release retains 61 episode rows and matching episode directories, including 1 preparation/recentring record. It includes motor commands, telemetry, zero-acquisition records, control-register snapshots and episode manifests.

The campaign-local `media/` tree is **not distributed** here: the full labeled/unlabeled videos, episode videos, camera JPEG/depth/AR records, keyframes, snapshots, visual index and full-video frame/chapter maps are absent. The original `inventory.sha256` is also absent. Camera paths and inventory references inside retained source reports describe the original archive; they are not links to supplied files or a completeness check of this export.

### Available teaching records

- [Current Class 04 lesson](../../../../../../module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md): worked explanation and saved-record activity.
- [Selected B1/H2/P06/R01 clip](../../../../recordings/source/b1-h2-p06-heldout.mp4): one available teaching record, not full visual coverage of this B2 campaign.
- [Paired B1/H2/P06/R01 samples](../../../data/minimal_heldout_episode_B1_H2_P06_R01.csv.gz), [held-out episode scores](../../../results/held_out_results.csv) and [overall held-out result](../../../results/overall_heldout_result.csv): the supplied numerical comparison.

## Retained source records

- [Episode summary](episode-summary.csv): one row per motor episode; its camera fields retain original-capture metadata.
- [Run manifest](run.json): original apparatus/protocol and run identities.
- [Method and results](B2_METHOD_AND_RESULTS.md): original campaign interpretation.
- [Host timing preflight](HOST_PREFLIGHT.json): recorded read-only U2D2 latency-timer evidence.
- [Original verification report](VERIFICATION.json): checks of the original archive, including camera files that are absent from this release. Its saved pass is not a new verification of release completeness.
- [Position-counter canonicalization](position-counter-canonicalization.json): original conversion record.

## Original camera-capture report

- Original camera-capture status: **complete**.
- Original episode media sessions: 60/60.
- Original full-video status: **complete**.

These statuses record what the source capture system reported at collection and verification time. They do not mean that the original camera archive is included in this release. Full and episode camera paths remain as provenance in the run, summary and episode manifests.

## Episode guide for retained motor records

The table uses the original friendly names, order and robot-result declarations. Each row links to its supplied manifest and motor data. Original camera locations remain in the manifest or episode summary. The campaign-local camera files are absent; the separate selected teaching clip is linked above.

| # | Friendly name | Original robot result | Episode manifest | Motor data |
|---:|---|---|---|---|
| 1 | H1 low-amplitude safety pilot | complete | [B2__H1__PILOT_LOW_AMPLITUDE](episodes/B2__H1__PILOT_LOW_AMPLITUDE/episode.json) | [commands](episodes/B2__H1__PILOT_LOW_AMPLITUDE/command_events.parquet) · [telemetry](episodes/B2__H1__PILOT_LOW_AMPLITUDE/telemetry_events.parquet) |
| 2 | H4 low-amplitude safety pilot | complete | [B2__H4__PILOT_LOW_AMPLITUDE](episodes/B2__H4__PILOT_LOW_AMPLITUDE/episode.json) | [commands](episodes/B2__H4__PILOT_LOW_AMPLITUDE/command_events.parquet) · [telemetry](episodes/B2__H4__PILOT_LOW_AMPLITUDE/telemetry_events.parquet) |
| 3 | H5 low-amplitude safety pilot | complete | [B2__H5__PILOT_LOW_AMPLITUDE](episodes/B2__H5__PILOT_LOW_AMPLITUDE/episode.json) | [commands](episodes/B2__H5__PILOT_LOW_AMPLITUDE/command_events.parquet) · [telemetry](episodes/B2__H5__PILOT_LOW_AMPLITUDE/telemetry_events.parquet) |
| 4 | H1 slow triangle motion, calibration repeat 01 | complete | [B2__H1__P01_slow_triangle__R01](episodes/B2__H1__P01_slow_triangle__R01/episode.json) | [commands](episodes/B2__H1__P01_slow_triangle__R01/command_events.parquet) · [telemetry](episodes/B2__H1__P01_slow_triangle__R01/telemetry_events.parquet) |
| 5 | H2 slow triangle motion, calibration repeat 01 | complete | [B2__H2__P01_slow_triangle__R01](episodes/B2__H2__P01_slow_triangle__R01/episode.json) | [commands](episodes/B2__H2__P01_slow_triangle__R01/command_events.parquet) · [telemetry](episodes/B2__H2__P01_slow_triangle__R01/telemetry_events.parquet) |
| 6 | H3 slow triangle motion, calibration repeat 01 | complete | [B2__H3__P01_slow_triangle__R01](episodes/B2__H3__P01_slow_triangle__R01/episode.json) | [commands](episodes/B2__H3__P01_slow_triangle__R01/command_events.parquet) · [telemetry](episodes/B2__H3__P01_slow_triangle__R01/telemetry_events.parquet) |
| 7 | H4 slow triangle motion, calibration repeat 01 | complete | [B2__H4__P01_slow_triangle__R01](episodes/B2__H4__P01_slow_triangle__R01/episode.json) | [commands](episodes/B2__H4__P01_slow_triangle__R01/command_events.parquet) · [telemetry](episodes/B2__H4__P01_slow_triangle__R01/telemetry_events.parquet) |
| 8 | H5 slow triangle motion, calibration repeat 01 | complete | [B2__H5__P01_slow_triangle__R01](episodes/B2__H5__P01_slow_triangle__R01/episode.json) | [commands](episodes/B2__H5__P01_slow_triangle__R01/command_events.parquet) · [telemetry](episodes/B2__H5__P01_slow_triangle__R01/telemetry_events.parquet) |
| 9 | H1 multisine motion, calibration repeat 01 | complete | [B2__H1__P02_multisine__R01](episodes/B2__H1__P02_multisine__R01/episode.json) | [commands](episodes/B2__H1__P02_multisine__R01/command_events.parquet) · [telemetry](episodes/B2__H1__P02_multisine__R01/telemetry_events.parquet) |
| 10 | H2 multisine motion, calibration repeat 01 | complete | [B2__H2__P02_multisine__R01](episodes/B2__H2__P02_multisine__R01/episode.json) | [commands](episodes/B2__H2__P02_multisine__R01/command_events.parquet) · [telemetry](episodes/B2__H2__P02_multisine__R01/telemetry_events.parquet) |
| 11 | H3 multisine motion, calibration repeat 01 | complete | [B2__H3__P02_multisine__R01](episodes/B2__H3__P02_multisine__R01/episode.json) | [commands](episodes/B2__H3__P02_multisine__R01/command_events.parquet) · [telemetry](episodes/B2__H3__P02_multisine__R01/telemetry_events.parquet) |
| 12 | H4 multisine motion, calibration repeat 01 | complete | [B2__H4__P02_multisine__R01](episodes/B2__H4__P02_multisine__R01/episode.json) | [commands](episodes/B2__H4__P02_multisine__R01/command_events.parquet) · [telemetry](episodes/B2__H4__P02_multisine__R01/telemetry_events.parquet) |
| 13 | H5 multisine motion, calibration repeat 01 | complete | [B2__H5__P02_multisine__R01](episodes/B2__H5__P02_multisine__R01/episode.json) | [commands](episodes/B2__H5__P02_multisine__R01/command_events.parquet) · [telemetry](episodes/B2__H5__P02_multisine__R01/telemetry_events.parquet) |
| 14 | H1 smooth-level motion, calibration repeat 01 | complete | [B2__H1__P03_smooth_levels__R01](episodes/B2__H1__P03_smooth_levels__R01/episode.json) | [commands](episodes/B2__H1__P03_smooth_levels__R01/command_events.parquet) · [telemetry](episodes/B2__H1__P03_smooth_levels__R01/telemetry_events.parquet) |
| 15 | H2 smooth-level motion, calibration repeat 01 | complete | [B2__H2__P03_smooth_levels__R01](episodes/B2__H2__P03_smooth_levels__R01/episode.json) | [commands](episodes/B2__H2__P03_smooth_levels__R01/command_events.parquet) · [telemetry](episodes/B2__H2__P03_smooth_levels__R01/telemetry_events.parquet) |
| 16 | H3 smooth-level motion, calibration repeat 01 | complete | [B2__H3__P03_smooth_levels__R01](episodes/B2__H3__P03_smooth_levels__R01/episode.json) | [commands](episodes/B2__H3__P03_smooth_levels__R01/command_events.parquet) · [telemetry](episodes/B2__H3__P03_smooth_levels__R01/telemetry_events.parquet) |
| 17 | H4 smooth-level motion, calibration repeat 01 | complete | [B2__H4__P03_smooth_levels__R01](episodes/B2__H4__P03_smooth_levels__R01/episode.json) | [commands](episodes/B2__H4__P03_smooth_levels__R01/command_events.parquet) · [telemetry](episodes/B2__H4__P03_smooth_levels__R01/telemetry_events.parquet) |
| 18 | H5 smooth-level motion, calibration repeat 01 | complete | [B2__H5__P03_smooth_levels__R01](episodes/B2__H5__P03_smooth_levels__R01/episode.json) | [commands](episodes/B2__H5__P03_smooth_levels__R01/command_events.parquet) · [telemetry](episodes/B2__H5__P03_smooth_levels__R01/telemetry_events.parquet) |
| 19 | H5 slow triangle motion, calibration repeat 02 | complete | [B2__H5__P01_slow_triangle__R02](episodes/B2__H5__P01_slow_triangle__R02/episode.json) | [commands](episodes/B2__H5__P01_slow_triangle__R02/command_events.parquet) · [telemetry](episodes/B2__H5__P01_slow_triangle__R02/telemetry_events.parquet) |
| 20 | H4 slow triangle motion, calibration repeat 02 | complete | [B2__H4__P01_slow_triangle__R02](episodes/B2__H4__P01_slow_triangle__R02/episode.json) | [commands](episodes/B2__H4__P01_slow_triangle__R02/command_events.parquet) · [telemetry](episodes/B2__H4__P01_slow_triangle__R02/telemetry_events.parquet) |
| 21 | H3 slow triangle motion, calibration repeat 02 | complete | [B2__H3__P01_slow_triangle__R02](episodes/B2__H3__P01_slow_triangle__R02/episode.json) | [commands](episodes/B2__H3__P01_slow_triangle__R02/command_events.parquet) · [telemetry](episodes/B2__H3__P01_slow_triangle__R02/telemetry_events.parquet) |
| 22 | H2 slow triangle motion, calibration repeat 02 | complete | [B2__H2__P01_slow_triangle__R02](episodes/B2__H2__P01_slow_triangle__R02/episode.json) | [commands](episodes/B2__H2__P01_slow_triangle__R02/command_events.parquet) · [telemetry](episodes/B2__H2__P01_slow_triangle__R02/telemetry_events.parquet) |
| 23 | H1 slow triangle motion, calibration repeat 02 | complete | [B2__H1__P01_slow_triangle__R02](episodes/B2__H1__P01_slow_triangle__R02/episode.json) | [commands](episodes/B2__H1__P01_slow_triangle__R02/command_events.parquet) · [telemetry](episodes/B2__H1__P01_slow_triangle__R02/telemetry_events.parquet) |
| 24 | H5 multisine motion, calibration repeat 02 | complete | [B2__H5__P02_multisine__R02](episodes/B2__H5__P02_multisine__R02/episode.json) | [commands](episodes/B2__H5__P02_multisine__R02/command_events.parquet) · [telemetry](episodes/B2__H5__P02_multisine__R02/telemetry_events.parquet) |
| 25 | H4 multisine motion, calibration repeat 02 | complete | [B2__H4__P02_multisine__R02](episodes/B2__H4__P02_multisine__R02/episode.json) | [commands](episodes/B2__H4__P02_multisine__R02/command_events.parquet) · [telemetry](episodes/B2__H4__P02_multisine__R02/telemetry_events.parquet) |
| 26 | H3 multisine motion, calibration repeat 02 | complete | [B2__H3__P02_multisine__R02](episodes/B2__H3__P02_multisine__R02/episode.json) | [commands](episodes/B2__H3__P02_multisine__R02/command_events.parquet) · [telemetry](episodes/B2__H3__P02_multisine__R02/telemetry_events.parquet) |
| 27 | H2 multisine motion, calibration repeat 02 | complete | [B2__H2__P02_multisine__R02](episodes/B2__H2__P02_multisine__R02/episode.json) | [commands](episodes/B2__H2__P02_multisine__R02/command_events.parquet) · [telemetry](episodes/B2__H2__P02_multisine__R02/telemetry_events.parquet) |
| 28 | H1 multisine motion, calibration repeat 02 | complete | [B2__H1__P02_multisine__R02](episodes/B2__H1__P02_multisine__R02/episode.json) | [commands](episodes/B2__H1__P02_multisine__R02/command_events.parquet) · [telemetry](episodes/B2__H1__P02_multisine__R02/telemetry_events.parquet) |
| 29 | H5 smooth-level motion, calibration repeat 02 | complete | [B2__H5__P03_smooth_levels__R02](episodes/B2__H5__P03_smooth_levels__R02/episode.json) | [commands](episodes/B2__H5__P03_smooth_levels__R02/command_events.parquet) · [telemetry](episodes/B2__H5__P03_smooth_levels__R02/telemetry_events.parquet) |
| 30 | H4 smooth-level motion, calibration repeat 02 | complete | [B2__H4__P03_smooth_levels__R02](episodes/B2__H4__P03_smooth_levels__R02/episode.json) | [commands](episodes/B2__H4__P03_smooth_levels__R02/command_events.parquet) · [telemetry](episodes/B2__H4__P03_smooth_levels__R02/telemetry_events.parquet) |
| 31 | H3 smooth-level motion, calibration repeat 02 | complete | [B2__H3__P03_smooth_levels__R02](episodes/B2__H3__P03_smooth_levels__R02/episode.json) | [commands](episodes/B2__H3__P03_smooth_levels__R02/command_events.parquet) · [telemetry](episodes/B2__H3__P03_smooth_levels__R02/telemetry_events.parquet) |
| 32 | H2 smooth-level motion, calibration repeat 02 | complete | [B2__H2__P03_smooth_levels__R02](episodes/B2__H2__P03_smooth_levels__R02/episode.json) | [commands](episodes/B2__H2__P03_smooth_levels__R02/command_events.parquet) · [telemetry](episodes/B2__H2__P03_smooth_levels__R02/telemetry_events.parquet) |
| 33 | H1 smooth-level motion, calibration repeat 02 | complete | [B2__H1__P03_smooth_levels__R02](episodes/B2__H1__P03_smooth_levels__R02/episode.json) | [commands](episodes/B2__H1__P03_smooth_levels__R02/command_events.parquet) · [telemetry](episodes/B2__H1__P03_smooth_levels__R02/telemetry_events.parquet) |
| 34 | H3 slow triangle motion, calibration repeat 03 | complete | [B2__H3__P01_slow_triangle__R03](episodes/B2__H3__P01_slow_triangle__R03/episode.json) | [commands](episodes/B2__H3__P01_slow_triangle__R03/command_events.parquet) · [telemetry](episodes/B2__H3__P01_slow_triangle__R03/telemetry_events.parquet) |
| 35 | H1 slow triangle motion, calibration repeat 03 | complete | [B2__H1__P01_slow_triangle__R03](episodes/B2__H1__P01_slow_triangle__R03/episode.json) | [commands](episodes/B2__H1__P01_slow_triangle__R03/command_events.parquet) · [telemetry](episodes/B2__H1__P01_slow_triangle__R03/telemetry_events.parquet) |
| 36 | H5 slow triangle motion, calibration repeat 03 | complete | [B2__H5__P01_slow_triangle__R03](episodes/B2__H5__P01_slow_triangle__R03/episode.json) | [commands](episodes/B2__H5__P01_slow_triangle__R03/command_events.parquet) · [telemetry](episodes/B2__H5__P01_slow_triangle__R03/telemetry_events.parquet) |
| 37 | H2 slow triangle motion, calibration repeat 03 | complete | [B2__H2__P01_slow_triangle__R03](episodes/B2__H2__P01_slow_triangle__R03/episode.json) | [commands](episodes/B2__H2__P01_slow_triangle__R03/command_events.parquet) · [telemetry](episodes/B2__H2__P01_slow_triangle__R03/telemetry_events.parquet) |
| 38 | H4 slow triangle motion, calibration repeat 03 | complete | [B2__H4__P01_slow_triangle__R03](episodes/B2__H4__P01_slow_triangle__R03/episode.json) | [commands](episodes/B2__H4__P01_slow_triangle__R03/command_events.parquet) · [telemetry](episodes/B2__H4__P01_slow_triangle__R03/telemetry_events.parquet) |
| 39 | H3 multisine motion, calibration repeat 03 | complete | [B2__H3__P02_multisine__R03](episodes/B2__H3__P02_multisine__R03/episode.json) | [commands](episodes/B2__H3__P02_multisine__R03/command_events.parquet) · [telemetry](episodes/B2__H3__P02_multisine__R03/telemetry_events.parquet) |
| 40 | H1 multisine motion, calibration repeat 03 | complete | [B2__H1__P02_multisine__R03](episodes/B2__H1__P02_multisine__R03/episode.json) | [commands](episodes/B2__H1__P02_multisine__R03/command_events.parquet) · [telemetry](episodes/B2__H1__P02_multisine__R03/telemetry_events.parquet) |
| 41 | H5 multisine motion, calibration repeat 03 | complete | [B2__H5__P02_multisine__R03](episodes/B2__H5__P02_multisine__R03/episode.json) | [commands](episodes/B2__H5__P02_multisine__R03/command_events.parquet) · [telemetry](episodes/B2__H5__P02_multisine__R03/telemetry_events.parquet) |
| 42 | H2 multisine motion, calibration repeat 03 | complete | [B2__H2__P02_multisine__R03](episodes/B2__H2__P02_multisine__R03/episode.json) | [commands](episodes/B2__H2__P02_multisine__R03/command_events.parquet) · [telemetry](episodes/B2__H2__P02_multisine__R03/telemetry_events.parquet) |
| 43 | H4 multisine motion, calibration repeat 03 | complete | [B2__H4__P02_multisine__R03](episodes/B2__H4__P02_multisine__R03/episode.json) | [commands](episodes/B2__H4__P02_multisine__R03/command_events.parquet) · [telemetry](episodes/B2__H4__P02_multisine__R03/telemetry_events.parquet) |
| 44 | H3 smooth-level motion, calibration repeat 03 | complete | [B2__H3__P03_smooth_levels__R03](episodes/B2__H3__P03_smooth_levels__R03/episode.json) | [commands](episodes/B2__H3__P03_smooth_levels__R03/command_events.parquet) · [telemetry](episodes/B2__H3__P03_smooth_levels__R03/telemetry_events.parquet) |
| 45 | H1 smooth-level motion, calibration repeat 03 | complete | [B2__H1__P03_smooth_levels__R03](episodes/B2__H1__P03_smooth_levels__R03/episode.json) | [commands](episodes/B2__H1__P03_smooth_levels__R03/command_events.parquet) · [telemetry](episodes/B2__H1__P03_smooth_levels__R03/telemetry_events.parquet) |
| 46 | H5 smooth-level motion, calibration repeat 03 | complete | [B2__H5__P03_smooth_levels__R03](episodes/B2__H5__P03_smooth_levels__R03/episode.json) | [commands](episodes/B2__H5__P03_smooth_levels__R03/command_events.parquet) · [telemetry](episodes/B2__H5__P03_smooth_levels__R03/telemetry_events.parquet) |
| 47 | H2 smooth-level motion, calibration repeat 03 | complete | [B2__H2__P03_smooth_levels__R03](episodes/B2__H2__P03_smooth_levels__R03/episode.json) | [commands](episodes/B2__H2__P03_smooth_levels__R03/command_events.parquet) · [telemetry](episodes/B2__H2__P03_smooth_levels__R03/telemetry_events.parquet) |
| 48 | H4 smooth-level motion, calibration repeat 03 | complete | [B2__H4__P03_smooth_levels__R03](episodes/B2__H4__P03_smooth_levels__R03/episode.json) | [commands](episodes/B2__H4__P03_smooth_levels__R03/command_events.parquet) · [telemetry](episodes/B2__H4__P03_smooth_levels__R03/telemetry_events.parquet) |
| 49 | H1 chirp motion, model selection repeat 01 | complete | [B2__H1__P04_chirp__R01](episodes/B2__H1__P04_chirp__R01/episode.json) | [commands](episodes/B2__H1__P04_chirp__R01/command_events.parquet) · [telemetry](episodes/B2__H1__P04_chirp__R01/telemetry_events.parquet) |
| 50 | H2 chirp motion, model selection repeat 01 | complete | [B2__H2__P04_chirp__R01](episodes/B2__H2__P04_chirp__R01/episode.json) | [commands](episodes/B2__H2__P04_chirp__R01/command_events.parquet) · [telemetry](episodes/B2__H2__P04_chirp__R01/telemetry_events.parquet) |
| 51 | H1 wide-sine motion, model selection repeat 01 | complete | [B2__H1__P05_wide_sine__R01](episodes/B2__H1__P05_wide_sine__R01/episode.json) | [commands](episodes/B2__H1__P05_wide_sine__R01/command_events.parquet) · [telemetry](episodes/B2__H1__P05_wide_sine__R01/telemetry_events.parquet) |
| 52 | H2 wide-sine motion, model selection repeat 01 | complete | [B2__H2__P05_wide_sine__R01](episodes/B2__H2__P05_wide_sine__R01/episode.json) | [commands](episodes/B2__H2__P05_wide_sine__R01/command_events.parquet) · [telemetry](episodes/B2__H2__P05_wide_sine__R01/telemetry_events.parquet) |
| 53 | H2 chirp motion, model selection repeat 02 | complete | [B2__H2__P04_chirp__R02](episodes/B2__H2__P04_chirp__R02/episode.json) | [commands](episodes/B2__H2__P04_chirp__R02/command_events.parquet) · [telemetry](episodes/B2__H2__P04_chirp__R02/telemetry_events.parquet) |
| 54 | H1 chirp motion, model selection repeat 02 | complete | [B2__H1__P04_chirp__R02](episodes/B2__H1__P04_chirp__R02/episode.json) | [commands](episodes/B2__H1__P04_chirp__R02/command_events.parquet) · [telemetry](episodes/B2__H1__P04_chirp__R02/telemetry_events.parquet) |
| 55 | H2 wide-sine motion, model selection repeat 02 | complete | [B2__H2__P05_wide_sine__R02](episodes/B2__H2__P05_wide_sine__R02/episode.json) | [commands](episodes/B2__H2__P05_wide_sine__R02/command_events.parquet) · [telemetry](episodes/B2__H2__P05_wide_sine__R02/telemetry_events.parquet) |
| 56 | H1 wide-sine motion, model selection repeat 02 | complete | [B2__H1__P05_wide_sine__R02](episodes/B2__H1__P05_wide_sine__R02/episode.json) | [commands](episodes/B2__H1__P05_wide_sine__R02/command_events.parquet) · [telemetry](episodes/B2__H1__P05_wide_sine__R02/telemetry_events.parquet) |
| 57 | H1 chirp motion, model selection repeat 03 | complete | [B2__H1__P04_chirp__R03](episodes/B2__H1__P04_chirp__R03/episode.json) | [commands](episodes/B2__H1__P04_chirp__R03/command_events.parquet) · [telemetry](episodes/B2__H1__P04_chirp__R03/telemetry_events.parquet) |
| 58 | H2 chirp motion, model selection repeat 03 | complete | [B2__H2__P04_chirp__R03](episodes/B2__H2__P04_chirp__R03/episode.json) | [commands](episodes/B2__H2__P04_chirp__R03/command_events.parquet) · [telemetry](episodes/B2__H2__P04_chirp__R03/telemetry_events.parquet) |
| 59 | H1 wide-sine motion, model selection repeat 03 | complete | [B2__H1__P05_wide_sine__R03](episodes/B2__H1__P05_wide_sine__R03/episode.json) | [commands](episodes/B2__H1__P05_wide_sine__R03/command_events.parquet) · [telemetry](episodes/B2__H1__P05_wide_sine__R03/telemetry_events.parquet) |
| 60 | H2 wide-sine motion, model selection repeat 03 | complete | [B2__H2__P05_wide_sine__R03](episodes/B2__H2__P05_wide_sine__R03/episode.json) | [commands](episodes/B2__H2__P05_wide_sine__R03/command_events.parquet) · [telemetry](episodes/B2__H2__P05_wide_sine__R03/telemetry_events.parquet) |

### Preparation records

- [B2__H1__RECENTER_001 manifest](episodes/B2__H1__RECENTER_001/episode.json), [commands](episodes/B2__H1__RECENTER_001/command_events.parquet) and [telemetry](episodes/B2__H1__RECENTER_001/telemetry_events.parquet): preparation/recentring, separate from the motion-and-media episode count above.
