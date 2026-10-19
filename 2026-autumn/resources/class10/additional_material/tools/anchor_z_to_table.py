"""Re-anchor the z axis of a pusher-tool dataset ("episode" format) from the episode start to the table.

In the recorded format the tool pose is relative to the first frame of the episode, so ``z = 0`` is wherever
the demonstration happened to start. The robot starts every episode at a fixed height and replays the relative
motion, so demonstrations that started at different heights push at different heights on the robot. With the
table as the z reference (``z`` = height of the pusher tip above the table) the policy knows how high it is on both
sides; x, y and the orientation stay relative to the episode start.

For datasets recorded without a table calibration the table is estimated per episode from the lowest point of
the tip: table = min(z) - push_height (the tip pushes ``push_height`` above the table; 0.006 m for the scripted
simulation expert, about 0.008 m for a person).

The converted dataset is written next to the original with the suffix ``_tablez`` (videos are shared through
symlinks; the parquet files are rewritten and the stats recomputed).

Usage::

    uv run python tools/anchor_z_to_table.py datasets/real_push_cube_all --push-height 0.008
    uv run python tools/anchor_z_to_table.py datasets/ip17v3_cube300_handheld --push-height 0.006
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def convert(root: Path, out: Path, push_height: float) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(root / "meta", out / "meta")
    os.symlink((root / "videos").resolve(), out / "videos")
    (out / "data").mkdir()
    offsets = {}
    for src in sorted((root / "data").glob("chunk-*/file-*.parquet")):
        df = pd.read_parquet(src)
        state = np.stack(df["observation.state"].to_numpy()).astype(np.float32)
        action = np.stack(df["action"].to_numpy()).astype(np.float32)
        for ep in np.unique(df["episode_index"]):
            m = (df["episode_index"] == ep).to_numpy()
            table = float(state[m, 2].min()) - push_height  # table height in the episode frame
            offsets[int(ep)] = table
            state[m, 2] -= table
            action[m, 2] -= table
        df["observation.state"] = list(state)
        df["action"] = list(action)
        dst = out / "data" / src.relative_to(root / "data")
        dst.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(dst, index=False)
    (out / "meta" / "table_offsets.json").write_text(json.dumps(offsets, indent=1))
    info_path = out / "meta" / "info.json"
    info = json.loads(info_path.read_text())
    info["z_frame"] = "table"  # documents the convention for scripts and people
    info_path.write_text(json.dumps(info, indent=4))
    heights = -np.array(list(offsets.values()))
    print(f"{len(offsets)} episodes: start height above the table {heights.min() * 100:.1f}-{heights.max() * 100:.1f} cm "
          f"(mean {heights.mean() * 100:.1f} cm)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="dataset directory (episode format)")
    ap.add_argument("--push-height", type=float, default=0.008, help="height of the pusher tip above the table while pushing, m (simulation expert 0.006, a person about 0.008)")
    ap.add_argument("--out", default=None, help="output directory (default <root>_tablez)")
    args = ap.parse_args()
    root = Path(args.root)
    out = Path(args.out) if args.out else root.parent / (root.name + "_tablez")
    convert(root, out, args.push_height)
    # recompute dataset statistics (normalisation of state / action uses them)
    subprocess.run([sys.executable, "-m", "lerobot.scripts.lerobot_edit_dataset", "--operation.type=recompute_stats", "--operation.overwrite=true",
                    f"--repo_id=local/{out.name}", f"--root={out}", f"--new_repo_id=local/{out.name}", f"--new_root={out}"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"wrote {out} (z relative to the table, stats recomputed)")


if __name__ == "__main__":
    main()
