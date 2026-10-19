# Class 02 — Additional material

[Lecture](../../../module-01-actuator-data-for-1-dof-systems/02-actuator-basics-for-controlled-action.md)

This folder holds the hardware record and the reference files of Class 02.

| Folder | Content |
| --- | --- |
| `data/hardware/xc330_physical_demo/` | one recorded XC330 episode: command and telemetry events (Parquet), the control table before and after, the episode metadata |
| `manuals/` | the user manuals of the XC330, RS00 and RS06, with their source URLs |
| `models/` | an MJCF reference model of a single XC330, an empty scene and the mesh assets |

Read the Parquet tables with pandas, for example:

```bash
cd 2026-autumn/resources/class02/additional_material
uv run --python 3.12 --with pandas --with pyarrow python -c \
    "import pandas as pd; print(pd.read_parquet('data/hardware/xc330_physical_demo/telemetry_events.parquet').head())"
```
