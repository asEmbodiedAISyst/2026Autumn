# START HERE — M0 XC330 experiment

This folder is the record of the M0 motor campaign. When camera capture succeeds, synchronized iPhone evidence is kept alongside the motor measurements.

## What was installed

- Motor: XC330-M288-T, ID 5.
- Fixture: motor-only; no external horn, link, pin, or payload is installed, so payload centers are not applicable.
- Moving mass declared for this run: 0 g.
- Experiment zero is measured encoder tick 2048 ±5 under torque; M0 uses the standard zero/recenter path and never G1's torque-off gravity-rest rule.

## Run status

- Collection status before independent verification: **complete**.
- Campaign error: none.
- Read-only host timing gate: passed=True; observed latency=1 ms.
- Planned motion-and-media episodes: 20.
- M0 captured design: H1/H2 only; 2 pilots and 18 calibration episodes (P01-P03 x H1/H2 x R01-R03).
- M0 has no P04/P05 model-selection or P06 held-out sessions; the design contract excludes model selection from M0.

## Where to look

- episode-summary.csv: one-row-per-episode motor and media summary.
- episodes/: full command, telemetry, zero-acquisition, register, and episode manifest data.
- HOST_PREFLIGHT.json: read-only U2D2 latency-timer evidence.
- VERIFICATION.json: per-run independent verification report.
- inventory.sha256: hashes every retained artifact, including VERIFICATION.json.

## Camera capture result

- Status: **complete**.
- Episode media sessions: 20/20.

### Full experiment viewing copies

- Full-video status: **complete**.
- Full labeled video: [open labeled video](media/video/260901-200740_M0_full-experiment-labeled.mp4).
- Full unlabeled video: [open unlabeled video](media/video/260901-200740_M0_full-experiment-unlabeled.mp4).
- Full-video frame map: media/video/260901-200740_M0_full-experiment-frame-map.csv.
- Full-video chapter map: media/video/260901-200740_M0_chapters.csv.
- Presentation: on the labeled copy, episode and phase labels are burned into the frames; the paired unlabeled copy has no overlays. There is no audio track; inter-episode gaps are omitted.
- Visual index: media/index.html.
- media/episodes/: one plainly named folder per motion episode.
- Each episode has a timestamp-prefixed labeled video and a matching timestamp-prefixed unlabeled video (derived, no audio).
- media/episodes/*/keyframes/: four event-aligned images: before motion, experiment zero/profile start, motion finished, and torque disabled.
- media/episodes/*/snapshots/: a separate timestamp-prefixed pre-motion photograph; it is not counted as a phase keyframe.
- media/episodes/*/raw/color_frames/: exact JPEG frames received from the iPhone; these are primary evidence.
- media/episodes/*/raw/depth_frames/: received uint16 depth arrays.
- media/episodes/*/raw/<number>_<scene>_ar.csv: authoritative iPhone time, host wall time, host monotonic time, pose, and camera intrinsics. raw/ar.csv is only a compatibility symlink.

Retain the JPEGs, depth arrays, CSV tables, and inventory with every derived MP4.

## Episode guide

| # | Friendly name | Robot result | Media folder | Labeled video | Unlabeled video |
|---:|---|---|---|---|---|
| 1 | H1 low-amplitude safety pilot | complete | media/episodes/260901-200740_H1-M0-PILOT_01-h1-safety-pilot | [open](media/episodes/260901-200740_H1-M0-PILOT_01-h1-safety-pilot/video/260901-200740_H1-M0-PILOT_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-PILOT_01-h1-safety-pilot/video/260901-200740_H1-M0-PILOT_experiment-unlabeled.mp4) |
| 2 | H2 low-amplitude safety pilot | complete | media/episodes/260901-200740_H2-M0-PILOT_02-h2-safety-pilot | [open](media/episodes/260901-200740_H2-M0-PILOT_02-h2-safety-pilot/video/260901-200740_H2-M0-PILOT_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-PILOT_02-h2-safety-pilot/video/260901-200740_H2-M0-PILOT_experiment-unlabeled.mp4) |
| 3 | H1 slow triangle motion, calibration repeat 01 | complete | media/episodes/260901-200740_H1-M0-P01-R01_03-h1-slow-triangle-repeat-01 | [open](media/episodes/260901-200740_H1-M0-P01-R01_03-h1-slow-triangle-repeat-01/video/260901-200740_H1-M0-P01-R01_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-P01-R01_03-h1-slow-triangle-repeat-01/video/260901-200740_H1-M0-P01-R01_experiment-unlabeled.mp4) |
| 4 | H2 slow triangle motion, calibration repeat 01 | complete | media/episodes/260901-200740_H2-M0-P01-R01_04-h2-slow-triangle-repeat-01 | [open](media/episodes/260901-200740_H2-M0-P01-R01_04-h2-slow-triangle-repeat-01/video/260901-200740_H2-M0-P01-R01_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-P01-R01_04-h2-slow-triangle-repeat-01/video/260901-200740_H2-M0-P01-R01_experiment-unlabeled.mp4) |
| 5 | H1 multisine motion, calibration repeat 01 | complete | media/episodes/260901-200740_H1-M0-P02-R01_05-h1-multisine-repeat-01 | [open](media/episodes/260901-200740_H1-M0-P02-R01_05-h1-multisine-repeat-01/video/260901-200740_H1-M0-P02-R01_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-P02-R01_05-h1-multisine-repeat-01/video/260901-200740_H1-M0-P02-R01_experiment-unlabeled.mp4) |
| 6 | H2 multisine motion, calibration repeat 01 | complete | media/episodes/260901-200740_H2-M0-P02-R01_06-h2-multisine-repeat-01 | [open](media/episodes/260901-200740_H2-M0-P02-R01_06-h2-multisine-repeat-01/video/260901-200740_H2-M0-P02-R01_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-P02-R01_06-h2-multisine-repeat-01/video/260901-200740_H2-M0-P02-R01_experiment-unlabeled.mp4) |
| 7 | H1 smooth-level motion, calibration repeat 01 | complete | media/episodes/260901-200740_H1-M0-P03-R01_07-h1-smooth-levels-repeat-01 | [open](media/episodes/260901-200740_H1-M0-P03-R01_07-h1-smooth-levels-repeat-01/video/260901-200740_H1-M0-P03-R01_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-P03-R01_07-h1-smooth-levels-repeat-01/video/260901-200740_H1-M0-P03-R01_experiment-unlabeled.mp4) |
| 8 | H2 smooth-level motion, calibration repeat 01 | complete | media/episodes/260901-200740_H2-M0-P03-R01_08-h2-smooth-levels-repeat-01 | [open](media/episodes/260901-200740_H2-M0-P03-R01_08-h2-smooth-levels-repeat-01/video/260901-200740_H2-M0-P03-R01_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-P03-R01_08-h2-smooth-levels-repeat-01/video/260901-200740_H2-M0-P03-R01_experiment-unlabeled.mp4) |
| 9 | H2 slow triangle motion, calibration repeat 02 | complete | media/episodes/260901-200740_H2-M0-P01-R02_09-h2-slow-triangle-repeat-02 | [open](media/episodes/260901-200740_H2-M0-P01-R02_09-h2-slow-triangle-repeat-02/video/260901-200740_H2-M0-P01-R02_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-P01-R02_09-h2-slow-triangle-repeat-02/video/260901-200740_H2-M0-P01-R02_experiment-unlabeled.mp4) |
| 10 | H1 slow triangle motion, calibration repeat 02 | complete | media/episodes/260901-200740_H1-M0-P01-R02_10-h1-slow-triangle-repeat-02 | [open](media/episodes/260901-200740_H1-M0-P01-R02_10-h1-slow-triangle-repeat-02/video/260901-200740_H1-M0-P01-R02_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-P01-R02_10-h1-slow-triangle-repeat-02/video/260901-200740_H1-M0-P01-R02_experiment-unlabeled.mp4) |
| 11 | H2 multisine motion, calibration repeat 02 | complete | media/episodes/260901-200740_H2-M0-P02-R02_11-h2-multisine-repeat-02 | [open](media/episodes/260901-200740_H2-M0-P02-R02_11-h2-multisine-repeat-02/video/260901-200740_H2-M0-P02-R02_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-P02-R02_11-h2-multisine-repeat-02/video/260901-200740_H2-M0-P02-R02_experiment-unlabeled.mp4) |
| 12 | H1 multisine motion, calibration repeat 02 | complete | media/episodes/260901-200740_H1-M0-P02-R02_12-h1-multisine-repeat-02 | [open](media/episodes/260901-200740_H1-M0-P02-R02_12-h1-multisine-repeat-02/video/260901-200740_H1-M0-P02-R02_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-P02-R02_12-h1-multisine-repeat-02/video/260901-200740_H1-M0-P02-R02_experiment-unlabeled.mp4) |
| 13 | H2 smooth-level motion, calibration repeat 02 | complete | media/episodes/260901-200740_H2-M0-P03-R02_13-h2-smooth-levels-repeat-02 | [open](media/episodes/260901-200740_H2-M0-P03-R02_13-h2-smooth-levels-repeat-02/video/260901-200740_H2-M0-P03-R02_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-P03-R02_13-h2-smooth-levels-repeat-02/video/260901-200740_H2-M0-P03-R02_experiment-unlabeled.mp4) |
| 14 | H1 smooth-level motion, calibration repeat 02 | complete | media/episodes/260901-200740_H1-M0-P03-R02_14-h1-smooth-levels-repeat-02 | [open](media/episodes/260901-200740_H1-M0-P03-R02_14-h1-smooth-levels-repeat-02/video/260901-200740_H1-M0-P03-R02_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-P03-R02_14-h1-smooth-levels-repeat-02/video/260901-200740_H1-M0-P03-R02_experiment-unlabeled.mp4) |
| 15 | H1 slow triangle motion, calibration repeat 03 | complete | media/episodes/260901-200740_H1-M0-P01-R03_15-h1-slow-triangle-repeat-03 | [open](media/episodes/260901-200740_H1-M0-P01-R03_15-h1-slow-triangle-repeat-03/video/260901-200740_H1-M0-P01-R03_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-P01-R03_15-h1-slow-triangle-repeat-03/video/260901-200740_H1-M0-P01-R03_experiment-unlabeled.mp4) |
| 16 | H2 slow triangle motion, calibration repeat 03 | complete | media/episodes/260901-200740_H2-M0-P01-R03_16-h2-slow-triangle-repeat-03 | [open](media/episodes/260901-200740_H2-M0-P01-R03_16-h2-slow-triangle-repeat-03/video/260901-200740_H2-M0-P01-R03_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-P01-R03_16-h2-slow-triangle-repeat-03/video/260901-200740_H2-M0-P01-R03_experiment-unlabeled.mp4) |
| 17 | H1 multisine motion, calibration repeat 03 | complete | media/episodes/260901-200740_H1-M0-P02-R03_17-h1-multisine-repeat-03 | [open](media/episodes/260901-200740_H1-M0-P02-R03_17-h1-multisine-repeat-03/video/260901-200740_H1-M0-P02-R03_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-P02-R03_17-h1-multisine-repeat-03/video/260901-200740_H1-M0-P02-R03_experiment-unlabeled.mp4) |
| 18 | H2 multisine motion, calibration repeat 03 | complete | media/episodes/260901-200740_H2-M0-P02-R03_18-h2-multisine-repeat-03 | [open](media/episodes/260901-200740_H2-M0-P02-R03_18-h2-multisine-repeat-03/video/260901-200740_H2-M0-P02-R03_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-P02-R03_18-h2-multisine-repeat-03/video/260901-200740_H2-M0-P02-R03_experiment-unlabeled.mp4) |
| 19 | H1 smooth-level motion, calibration repeat 03 | complete | media/episodes/260901-200740_H1-M0-P03-R03_19-h1-smooth-levels-repeat-03 | [open](media/episodes/260901-200740_H1-M0-P03-R03_19-h1-smooth-levels-repeat-03/video/260901-200740_H1-M0-P03-R03_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H1-M0-P03-R03_19-h1-smooth-levels-repeat-03/video/260901-200740_H1-M0-P03-R03_experiment-unlabeled.mp4) |
| 20 | H2 smooth-level motion, calibration repeat 03 | complete | media/episodes/260901-200740_H2-M0-P03-R03_20-h2-smooth-levels-repeat-03 | [open](media/episodes/260901-200740_H2-M0-P03-R03_20-h2-smooth-levels-repeat-03/video/260901-200740_H2-M0-P03-R03_experiment-labeled.mp4) | [open](media/episodes/260901-200740_H2-M0-P03-R03_20-h2-smooth-levels-repeat-03/video/260901-200740_H2-M0-P03-R03_experiment-unlabeled.mp4) |
