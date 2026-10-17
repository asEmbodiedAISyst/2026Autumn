"""Rebuild portable CSVs from the immutable supplied Parquet files.

Authoring only: requires pyarrow. Student audit/inspection uses standard Python.
No serial/CAN access or hardware commands are implemented.
"""
from pathlib import Path
import csv
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "xc330-hardware-demo"


def main():
    for name in ("telemetry_events", "command_events"):
        table = pq.read_table(DATA / "raw" / f"{name}.parquet")
        rows = table.to_pylist()
        with (DATA / f"{name}.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=table.column_names)
            writer.writeheader()
            writer.writerows(rows)
        print(f"{name}: {len(rows)} source rows; all columns retained")


if __name__ == "__main__":
    main()
