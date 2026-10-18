# START HERE — G1 XC330 experiment

This folder is the record of the G1 motor campaign. When camera capture succeeds, synchronized iPhone evidence is kept alongside the motor measurements.

## What was installed

- Motor: XC330-M288-T, ID 5.
- Fixture: two payloads on the positive side at +60 mm and +100 mm.
- Moving mass declared for this run: 110 g.
- Torque-off gravity rest is not experiment zero; experiment zero is measured encoder tick 2048 ±5 under torque.

## Run status

- Collection status before independent verification: **complete**.
- Campaign error: none.
- Read-only host timing gate: passed=True; observed latency=1 ms.

## Where to look

- episode-summary.csv: one-row-per-episode motor and media summary.
- episodes/: full command, telemetry, zero-acquisition, register, and episode manifest data.
- HOST_PREFLIGHT.json: read-only U2D2 latency-timer evidence.
- VERIFICATION.json: per-run independent verification report.
- inventory.sha256: hashes every retained artifact, including VERIFICATION.json.

## Camera capture result

- Status: **complete**.
- Episode media sessions: 22.

### Full experiment viewing copy

- Full-video status: **complete**.
- Full labeled video: [open labeled video](media/video/260901-161228_G1_full-experiment-labeled.mp4).
- Full unlabeled video: [open unlabeled video](media/video/260901-161228_G1_full-experiment-unlabeled.mp4).
- Full-video frame map: media/video/260901-161228_G1_full-experiment-frame-map.csv.
- Full-video chapter map: media/video/260901-161228_G1_chapters.csv.
- Presentation: episode and phase labels are burned into the frames; there is no audio track; inter-episode gaps are omitted.
- Visual index: media/index.html.
- media/episodes/: one plainly named folder per motion episode.
- Each episode has a timestamp-prefixed labeled video and a matching timestamp-prefixed unlabeled video (derived, no audio).
- media/episodes/*/keyframes/: labeled setup, zero, finish, and gravity-rest photographs.
- media/episodes/*/raw/color_frames/: exact JPEG frames received from the iPhone; these are primary evidence.
- media/episodes/*/raw/depth_frames/: received uint16 depth arrays.
- media/episodes/*/raw/<number>_<scene>_ar.csv: authoritative iPhone time, host wall time, host monotonic time, pose, and camera intrinsics. raw/ar.csv is only a compatibility symlink.

Retain the JPEGs, depth arrays, CSV tables, and inventory with every derived MP4.

## Episode guide

| # | Friendly name | Robot result | Media folder | Labeled video | Unlabeled video |
|---:|---|---|---|---|---|
| 1 | H1 low-amplitude safety pilot | complete | media/episodes/260901-161228_H1-G1-PILOT_01-h1-safety-pilot | [open](media/episodes/260901-161228_H1-G1-PILOT_01-h1-safety-pilot/video/260901-161228_H1-G1-PILOT_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-PILOT_01-h1-safety-pilot/video/260901-161228_H1-G1-PILOT_experiment-unlabeled.mp4) |
| 2 | H2 low-amplitude safety pilot | complete | media/episodes/260901-161228_H2-G1-PILOT_02-h2-safety-pilot | [open](media/episodes/260901-161228_H2-G1-PILOT_02-h2-safety-pilot/video/260901-161228_H2-G1-PILOT_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-PILOT_02-h2-safety-pilot/video/260901-161228_H2-G1-PILOT_experiment-unlabeled.mp4) |
| 3 | H1 held-out composite motion, repeat 01 | complete | media/episodes/260901-161228_H1-G1-P06-R01_03-h1-composite-repeat-01 | [open](media/episodes/260901-161228_H1-G1-P06-R01_03-h1-composite-repeat-01/video/260901-161228_H1-G1-P06-R01_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P06-R01_03-h1-composite-repeat-01/video/260901-161228_H1-G1-P06-R01_experiment-unlabeled.mp4) |
| 4 | H2 held-out composite motion, repeat 01 | complete | media/episodes/260901-161228_H2-G1-P06-R01_04-h2-composite-repeat-01 | [open](media/episodes/260901-161228_H2-G1-P06-R01_04-h2-composite-repeat-01/video/260901-161228_H2-G1-P06-R01_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P06-R01_04-h2-composite-repeat-01/video/260901-161228_H2-G1-P06-R01_experiment-unlabeled.mp4) |
| 5 | H1 held-out sine-and-hold motion, repeat 01 | complete | media/episodes/260901-161228_H1-G1-P07-R01_05-h1-sine-and-hold-repeat-01 | [open](media/episodes/260901-161228_H1-G1-P07-R01_05-h1-sine-and-hold-repeat-01/video/260901-161228_H1-G1-P07-R01_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P07-R01_05-h1-sine-and-hold-repeat-01/video/260901-161228_H1-G1-P07-R01_experiment-unlabeled.mp4) |
| 6 | H2 held-out sine-and-hold motion, repeat 01 | complete | media/episodes/260901-161228_H2-G1-P07-R01_06-h2-sine-and-hold-repeat-01 | [open](media/episodes/260901-161228_H2-G1-P07-R01_06-h2-sine-and-hold-repeat-01/video/260901-161228_H2-G1-P07-R01_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P07-R01_06-h2-sine-and-hold-repeat-01/video/260901-161228_H2-G1-P07-R01_experiment-unlabeled.mp4) |
| 7 | H2 held-out composite motion, repeat 02 | complete | media/episodes/260901-161228_H2-G1-P06-R02_07-h2-composite-repeat-02 | [open](media/episodes/260901-161228_H2-G1-P06-R02_07-h2-composite-repeat-02/video/260901-161228_H2-G1-P06-R02_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P06-R02_07-h2-composite-repeat-02/video/260901-161228_H2-G1-P06-R02_experiment-unlabeled.mp4) |
| 8 | H1 held-out composite motion, repeat 02 | complete | media/episodes/260901-161228_H1-G1-P06-R02_08-h1-composite-repeat-02 | [open](media/episodes/260901-161228_H1-G1-P06-R02_08-h1-composite-repeat-02/video/260901-161228_H1-G1-P06-R02_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P06-R02_08-h1-composite-repeat-02/video/260901-161228_H1-G1-P06-R02_experiment-unlabeled.mp4) |
| 9 | H2 held-out sine-and-hold motion, repeat 02 | complete | media/episodes/260901-161228_H2-G1-P07-R02_09-h2-sine-and-hold-repeat-02 | [open](media/episodes/260901-161228_H2-G1-P07-R02_09-h2-sine-and-hold-repeat-02/video/260901-161228_H2-G1-P07-R02_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P07-R02_09-h2-sine-and-hold-repeat-02/video/260901-161228_H2-G1-P07-R02_experiment-unlabeled.mp4) |
| 10 | H1 held-out sine-and-hold motion, repeat 02 | complete | media/episodes/260901-161228_H1-G1-P07-R02_10-h1-sine-and-hold-repeat-02 | [open](media/episodes/260901-161228_H1-G1-P07-R02_10-h1-sine-and-hold-repeat-02/video/260901-161228_H1-G1-P07-R02_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P07-R02_10-h1-sine-and-hold-repeat-02/video/260901-161228_H1-G1-P07-R02_experiment-unlabeled.mp4) |
| 11 | H1 held-out composite motion, repeat 03 | complete | media/episodes/260901-161228_H1-G1-P06-R03_11-h1-composite-repeat-03 | [open](media/episodes/260901-161228_H1-G1-P06-R03_11-h1-composite-repeat-03/video/260901-161228_H1-G1-P06-R03_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P06-R03_11-h1-composite-repeat-03/video/260901-161228_H1-G1-P06-R03_experiment-unlabeled.mp4) |
| 12 | H2 held-out composite motion, repeat 03 | complete | media/episodes/260901-161228_H2-G1-P06-R03_12-h2-composite-repeat-03 | [open](media/episodes/260901-161228_H2-G1-P06-R03_12-h2-composite-repeat-03/video/260901-161228_H2-G1-P06-R03_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P06-R03_12-h2-composite-repeat-03/video/260901-161228_H2-G1-P06-R03_experiment-unlabeled.mp4) |
| 13 | H1 held-out sine-and-hold motion, repeat 03 | complete | media/episodes/260901-161228_H1-G1-P07-R03_13-h1-sine-and-hold-repeat-03 | [open](media/episodes/260901-161228_H1-G1-P07-R03_13-h1-sine-and-hold-repeat-03/video/260901-161228_H1-G1-P07-R03_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P07-R03_13-h1-sine-and-hold-repeat-03/video/260901-161228_H1-G1-P07-R03_experiment-unlabeled.mp4) |
| 14 | H2 held-out sine-and-hold motion, repeat 03 | complete | media/episodes/260901-161228_H2-G1-P07-R03_14-h2-sine-and-hold-repeat-03 | [open](media/episodes/260901-161228_H2-G1-P07-R03_14-h2-sine-and-hold-repeat-03/video/260901-161228_H2-G1-P07-R03_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P07-R03_14-h2-sine-and-hold-repeat-03/video/260901-161228_H2-G1-P07-R03_experiment-unlabeled.mp4) |
| 15 | H2 held-out composite motion, repeat 04 | complete | media/episodes/260901-161228_H2-G1-P06-R04_15-h2-composite-repeat-04 | [open](media/episodes/260901-161228_H2-G1-P06-R04_15-h2-composite-repeat-04/video/260901-161228_H2-G1-P06-R04_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P06-R04_15-h2-composite-repeat-04/video/260901-161228_H2-G1-P06-R04_experiment-unlabeled.mp4) |
| 16 | H1 held-out composite motion, repeat 04 | complete | media/episodes/260901-161228_H1-G1-P06-R04_16-h1-composite-repeat-04 | [open](media/episodes/260901-161228_H1-G1-P06-R04_16-h1-composite-repeat-04/video/260901-161228_H1-G1-P06-R04_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P06-R04_16-h1-composite-repeat-04/video/260901-161228_H1-G1-P06-R04_experiment-unlabeled.mp4) |
| 17 | H2 held-out sine-and-hold motion, repeat 04 | complete | media/episodes/260901-161228_H2-G1-P07-R04_17-h2-sine-and-hold-repeat-04 | [open](media/episodes/260901-161228_H2-G1-P07-R04_17-h2-sine-and-hold-repeat-04/video/260901-161228_H2-G1-P07-R04_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P07-R04_17-h2-sine-and-hold-repeat-04/video/260901-161228_H2-G1-P07-R04_experiment-unlabeled.mp4) |
| 18 | H1 held-out sine-and-hold motion, repeat 04 | complete | media/episodes/260901-161228_H1-G1-P07-R04_18-h1-sine-and-hold-repeat-04 | [open](media/episodes/260901-161228_H1-G1-P07-R04_18-h1-sine-and-hold-repeat-04/video/260901-161228_H1-G1-P07-R04_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P07-R04_18-h1-sine-and-hold-repeat-04/video/260901-161228_H1-G1-P07-R04_experiment-unlabeled.mp4) |
| 19 | H1 held-out composite motion, repeat 05 | complete | media/episodes/260901-161228_H1-G1-P06-R05_19-h1-composite-repeat-05 | [open](media/episodes/260901-161228_H1-G1-P06-R05_19-h1-composite-repeat-05/video/260901-161228_H1-G1-P06-R05_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P06-R05_19-h1-composite-repeat-05/video/260901-161228_H1-G1-P06-R05_experiment-unlabeled.mp4) |
| 20 | H2 held-out composite motion, repeat 05 | complete | media/episodes/260901-161228_H2-G1-P06-R05_20-h2-composite-repeat-05 | [open](media/episodes/260901-161228_H2-G1-P06-R05_20-h2-composite-repeat-05/video/260901-161228_H2-G1-P06-R05_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P06-R05_20-h2-composite-repeat-05/video/260901-161228_H2-G1-P06-R05_experiment-unlabeled.mp4) |
| 21 | H1 held-out sine-and-hold motion, repeat 05 | complete | media/episodes/260901-161228_H1-G1-P07-R05_21-h1-sine-and-hold-repeat-05 | [open](media/episodes/260901-161228_H1-G1-P07-R05_21-h1-sine-and-hold-repeat-05/video/260901-161228_H1-G1-P07-R05_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H1-G1-P07-R05_21-h1-sine-and-hold-repeat-05/video/260901-161228_H1-G1-P07-R05_experiment-unlabeled.mp4) |
| 22 | H2 held-out sine-and-hold motion, repeat 05 | complete | media/episodes/260901-161228_H2-G1-P07-R05_22-h2-sine-and-hold-repeat-05 | [open](media/episodes/260901-161228_H2-G1-P07-R05_22-h2-sine-and-hold-repeat-05/video/260901-161228_H2-G1-P07-R05_experiment-labeled.mp4) | [open](media/episodes/260901-161228_H2-G1-P07-R05_22-h2-sine-and-hold-repeat-05/video/260901-161228_H2-G1-P07-R05_experiment-unlabeled.mp4) |
