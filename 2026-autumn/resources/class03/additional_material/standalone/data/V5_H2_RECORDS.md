# Embedded V5 B0 H2 records

These local copies make the course projects standalone. The command and telemetry files were copied from the V5 hardware campaign and do not require any path outside this folder. Their episode metadata uses the accepted fixture correction: a 22 g link plus two complete 44 g pin–payload assemblies, giving 110 g external moving mass.

| profile | repeat | command duration | Class 03 use |
| --- | ---: | ---: | --- |
| P01 slow triangle | R01 | 13.00 s | selected physical protocol |
| P02 multisine | R01 | 14.75 s | student simulation replay |
| P03 smooth levels | R01 | 8.54 s | selected physical protocol |

Each profile directory contains `command_events.parquet`, `telemetry_events.parquet`, and corrected `episode.json` metadata. Class 03 replays P02/R01 in the student activity and can replay P01–P03/R01 as the selected physical protocol. Class 04 uses the complete 15-episode set: P01–P05 with R01 and R02 for calibration and R03 for independent validation.
