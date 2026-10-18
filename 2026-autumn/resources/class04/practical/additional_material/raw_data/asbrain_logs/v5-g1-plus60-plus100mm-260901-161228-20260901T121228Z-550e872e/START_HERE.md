# START HERE — G1 XC330 experiment

This folder distributes retained motor records from the G1 campaign. The original campaign also reported synchronized iPhone capture; that original capture report and this release’s contents have different scopes.

## What was installed

- Motor: XC330-M288-T, ID 5.
- Fixture: two payloads on the positive side at +60 mm and +100 mm.
- Moving mass declared for this run: 110 g.
- Torque-off gravity rest is not experiment zero; experiment zero is measured encoder tick 2048 ±5 under torque.

## Original run status

- Collection status before independent verification: **complete**.
- Campaign error: none.
- Read-only host timing gate: passed=True; observed latency=1 ms.

## Distribution scope

This release retains 22 episode rows and matching episode directories. It includes motor commands, telemetry, zero-acquisition records, control-register snapshots and episode manifests.

The campaign-local `media/` tree is **not distributed** here: the full labeled/unlabeled videos, episode videos, camera JPEG/depth/AR records, keyframes, snapshots, visual index and full-video frame/chapter maps are absent. The original `inventory.sha256` is also absent. Camera paths and inventory references inside retained source reports describe the original archive; they are not links to supplied files or a completeness check of this export.

### Available teaching records

- [Current Class 04 lesson](../../../../../../../module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md): worked explanation and saved-record activity.
- [Selected B1/H2/P06/R01 clip](../../../../../recordings/source/b1-h2-p06-heldout.mp4): one available teaching record, not full visual coverage of this G1 campaign.
- [Paired B1/H2/P06/R01 samples](../../../data/minimal_heldout_episode_B1_H2_P06_R01.csv.gz), [held-out episode scores](../../../results/held_out_results.csv) and [overall held-out result](../../../results/overall_heldout_result.csv): the supplied numerical comparison.

## Retained source records

- [Episode summary](episode-summary.csv): one row per motor episode; its camera fields retain original-capture metadata.
- [Run manifest](run.json): original apparatus/protocol and run identities.
- [Method and results](G1_METHOD_AND_RESULTS.md): original campaign interpretation.
- [Host timing preflight](HOST_PREFLIGHT.json): recorded read-only U2D2 latency-timer evidence.
- [Original verification report](VERIFICATION.json): checks of the original archive, including camera files that are absent from this release. Its saved pass is not a new verification of release completeness.
- [Position-counter canonicalization](position-counter-canonicalization.json): original conversion record.

## Original camera-capture report

- Original camera-capture status: **complete**.
- Original episode media sessions: 22.
- Original full-video status: **complete**.

These statuses record what the source capture system reported at collection and verification time. They do not mean that the original camera archive is included in this release. Full and episode camera paths remain as provenance in the run, summary and episode manifests.

## Episode guide for retained motor records

The table uses the original friendly names, order and robot-result declarations. Each row links to its supplied manifest and motor data. Original camera locations remain in the manifest or episode summary. The campaign-local camera files are absent; the separate selected teaching clip is linked above.

| # | Friendly name | Original robot result | Episode manifest | Motor data |
|---:|---|---|---|---|
| 1 | H1 low-amplitude safety pilot | complete | [G1__H1__PILOT_LOW_AMPLITUDE](episodes/G1__H1__PILOT_LOW_AMPLITUDE/episode.json) | [commands](episodes/G1__H1__PILOT_LOW_AMPLITUDE/command_events.parquet) · [telemetry](episodes/G1__H1__PILOT_LOW_AMPLITUDE/telemetry_events.parquet) |
| 2 | H2 low-amplitude safety pilot | complete | [G1__H2__PILOT_LOW_AMPLITUDE](episodes/G1__H2__PILOT_LOW_AMPLITUDE/episode.json) | [commands](episodes/G1__H2__PILOT_LOW_AMPLITUDE/command_events.parquet) · [telemetry](episodes/G1__H2__PILOT_LOW_AMPLITUDE/telemetry_events.parquet) |
| 3 | H1 held-out composite motion, repeat 01 | complete | [G1__H1__P06_heldout_composite__R01](episodes/G1__H1__P06_heldout_composite__R01/episode.json) | [commands](episodes/G1__H1__P06_heldout_composite__R01/command_events.parquet) · [telemetry](episodes/G1__H1__P06_heldout_composite__R01/telemetry_events.parquet) |
| 4 | H2 held-out composite motion, repeat 01 | complete | [G1__H2__P06_heldout_composite__R01](episodes/G1__H2__P06_heldout_composite__R01/episode.json) | [commands](episodes/G1__H2__P06_heldout_composite__R01/command_events.parquet) · [telemetry](episodes/G1__H2__P06_heldout_composite__R01/telemetry_events.parquet) |
| 5 | H1 held-out sine-and-hold motion, repeat 01 | complete | [G1__H1__P07_heldout_sine_hold__R01](episodes/G1__H1__P07_heldout_sine_hold__R01/episode.json) | [commands](episodes/G1__H1__P07_heldout_sine_hold__R01/command_events.parquet) · [telemetry](episodes/G1__H1__P07_heldout_sine_hold__R01/telemetry_events.parquet) |
| 6 | H2 held-out sine-and-hold motion, repeat 01 | complete | [G1__H2__P07_heldout_sine_hold__R01](episodes/G1__H2__P07_heldout_sine_hold__R01/episode.json) | [commands](episodes/G1__H2__P07_heldout_sine_hold__R01/command_events.parquet) · [telemetry](episodes/G1__H2__P07_heldout_sine_hold__R01/telemetry_events.parquet) |
| 7 | H2 held-out composite motion, repeat 02 | complete | [G1__H2__P06_heldout_composite__R02](episodes/G1__H2__P06_heldout_composite__R02/episode.json) | [commands](episodes/G1__H2__P06_heldout_composite__R02/command_events.parquet) · [telemetry](episodes/G1__H2__P06_heldout_composite__R02/telemetry_events.parquet) |
| 8 | H1 held-out composite motion, repeat 02 | complete | [G1__H1__P06_heldout_composite__R02](episodes/G1__H1__P06_heldout_composite__R02/episode.json) | [commands](episodes/G1__H1__P06_heldout_composite__R02/command_events.parquet) · [telemetry](episodes/G1__H1__P06_heldout_composite__R02/telemetry_events.parquet) |
| 9 | H2 held-out sine-and-hold motion, repeat 02 | complete | [G1__H2__P07_heldout_sine_hold__R02](episodes/G1__H2__P07_heldout_sine_hold__R02/episode.json) | [commands](episodes/G1__H2__P07_heldout_sine_hold__R02/command_events.parquet) · [telemetry](episodes/G1__H2__P07_heldout_sine_hold__R02/telemetry_events.parquet) |
| 10 | H1 held-out sine-and-hold motion, repeat 02 | complete | [G1__H1__P07_heldout_sine_hold__R02](episodes/G1__H1__P07_heldout_sine_hold__R02/episode.json) | [commands](episodes/G1__H1__P07_heldout_sine_hold__R02/command_events.parquet) · [telemetry](episodes/G1__H1__P07_heldout_sine_hold__R02/telemetry_events.parquet) |
| 11 | H1 held-out composite motion, repeat 03 | complete | [G1__H1__P06_heldout_composite__R03](episodes/G1__H1__P06_heldout_composite__R03/episode.json) | [commands](episodes/G1__H1__P06_heldout_composite__R03/command_events.parquet) · [telemetry](episodes/G1__H1__P06_heldout_composite__R03/telemetry_events.parquet) |
| 12 | H2 held-out composite motion, repeat 03 | complete | [G1__H2__P06_heldout_composite__R03](episodes/G1__H2__P06_heldout_composite__R03/episode.json) | [commands](episodes/G1__H2__P06_heldout_composite__R03/command_events.parquet) · [telemetry](episodes/G1__H2__P06_heldout_composite__R03/telemetry_events.parquet) |
| 13 | H1 held-out sine-and-hold motion, repeat 03 | complete | [G1__H1__P07_heldout_sine_hold__R03](episodes/G1__H1__P07_heldout_sine_hold__R03/episode.json) | [commands](episodes/G1__H1__P07_heldout_sine_hold__R03/command_events.parquet) · [telemetry](episodes/G1__H1__P07_heldout_sine_hold__R03/telemetry_events.parquet) |
| 14 | H2 held-out sine-and-hold motion, repeat 03 | complete | [G1__H2__P07_heldout_sine_hold__R03](episodes/G1__H2__P07_heldout_sine_hold__R03/episode.json) | [commands](episodes/G1__H2__P07_heldout_sine_hold__R03/command_events.parquet) · [telemetry](episodes/G1__H2__P07_heldout_sine_hold__R03/telemetry_events.parquet) |
| 15 | H2 held-out composite motion, repeat 04 | complete | [G1__H2__P06_heldout_composite__R04](episodes/G1__H2__P06_heldout_composite__R04/episode.json) | [commands](episodes/G1__H2__P06_heldout_composite__R04/command_events.parquet) · [telemetry](episodes/G1__H2__P06_heldout_composite__R04/telemetry_events.parquet) |
| 16 | H1 held-out composite motion, repeat 04 | complete | [G1__H1__P06_heldout_composite__R04](episodes/G1__H1__P06_heldout_composite__R04/episode.json) | [commands](episodes/G1__H1__P06_heldout_composite__R04/command_events.parquet) · [telemetry](episodes/G1__H1__P06_heldout_composite__R04/telemetry_events.parquet) |
| 17 | H2 held-out sine-and-hold motion, repeat 04 | complete | [G1__H2__P07_heldout_sine_hold__R04](episodes/G1__H2__P07_heldout_sine_hold__R04/episode.json) | [commands](episodes/G1__H2__P07_heldout_sine_hold__R04/command_events.parquet) · [telemetry](episodes/G1__H2__P07_heldout_sine_hold__R04/telemetry_events.parquet) |
| 18 | H1 held-out sine-and-hold motion, repeat 04 | complete | [G1__H1__P07_heldout_sine_hold__R04](episodes/G1__H1__P07_heldout_sine_hold__R04/episode.json) | [commands](episodes/G1__H1__P07_heldout_sine_hold__R04/command_events.parquet) · [telemetry](episodes/G1__H1__P07_heldout_sine_hold__R04/telemetry_events.parquet) |
| 19 | H1 held-out composite motion, repeat 05 | complete | [G1__H1__P06_heldout_composite__R05](episodes/G1__H1__P06_heldout_composite__R05/episode.json) | [commands](episodes/G1__H1__P06_heldout_composite__R05/command_events.parquet) · [telemetry](episodes/G1__H1__P06_heldout_composite__R05/telemetry_events.parquet) |
| 20 | H2 held-out composite motion, repeat 05 | complete | [G1__H2__P06_heldout_composite__R05](episodes/G1__H2__P06_heldout_composite__R05/episode.json) | [commands](episodes/G1__H2__P06_heldout_composite__R05/command_events.parquet) · [telemetry](episodes/G1__H2__P06_heldout_composite__R05/telemetry_events.parquet) |
| 21 | H1 held-out sine-and-hold motion, repeat 05 | complete | [G1__H1__P07_heldout_sine_hold__R05](episodes/G1__H1__P07_heldout_sine_hold__R05/episode.json) | [commands](episodes/G1__H1__P07_heldout_sine_hold__R05/command_events.parquet) · [telemetry](episodes/G1__H1__P07_heldout_sine_hold__R05/telemetry_events.parquet) |
| 22 | H2 held-out sine-and-hold motion, repeat 05 | complete | [G1__H2__P07_heldout_sine_hold__R05](episodes/G1__H2__P07_heldout_sine_hold__R05/episode.json) | [commands](episodes/G1__H2__P07_heldout_sine_hold__R05/command_events.parquet) · [telemetry](episodes/G1__H2__P07_heldout_sine_hold__R05/telemetry_events.parquet) |
