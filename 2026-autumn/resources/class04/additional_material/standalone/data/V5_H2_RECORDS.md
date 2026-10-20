# Embedded V5 B0/H2 physical records

Class 04 includes local copies of the full available V5 B0/H2 set. No runtime path points back to V5 and no new physical data is collected by the identification script.

| coverage | profiles | repeats | total episodes |
| --- | --- | --- | ---: |
| full H2 experiment set | P01 slow triangle, P02 multisine, P03 smooth levels, P04 chirp, P05 wide sine | R01, R02, R03 | 15 |

Every directory in `data/v5_h2_full/` contains the original V5 `command_events.parquet` and `telemetry_events.parquet`. The `episode.json` fixture metadata uses the accepted 110 g correction: a 22 g link and two complete 44 g pin–payload assemblies.

The Class 04 simulation uses all records:

- calibration: R01 and R02 for P01–P05 (10 episodes);
- independent validation: R03 for P01–P05 (5 episodes);
- focused replay in the MuJoCo viewer: held-out P04 chirp R03.

The smaller `data/v5_h2_calibration/` set is retained for the Class 03 selected physical protocol (P01 + P02 + P03, R01). The Class 04 full experiment uses `v5_h2_full/`.
