"""Portable pilot contract and numeric audit. Python standard library only."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
VECTOR_KEYS = ("action", "observation.state", "observation.environment_state")


def load_rows(root):
    with (root / "frames.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in VECTOR_KEYS:
            row[key] = json.loads(row[key])
        for key in ("episode_index", "frame_index", "index", "task_index"):
            row[key] = int(row[key])
        row["timestamp"] = float(row["timestamp"])
    return rows


def audit(root, cfg):
    info = json.loads((root / "meta/info.json").read_text())
    rows = load_rows(root)
    fps = info["fps"]
    episodes = []
    for episode in sorted({row["episode_index"] for row in rows}):
        group = sorted((r for r in rows if r["episode_index"] == episode), key=lambda r: r["frame_index"])
        timestamps = [r["timestamp"] for r in group]
        shape_ok = all(len(r[k]) == info["features"][k]["shape"][0] for r in group for k in VECTOR_KEYS)
        finite = all(math.isfinite(v) for r in group for v in [r["timestamp"], *(v for k in VECTOR_KEYS for v in r[k])])
        dt_ok = len(group) > 1 and all(abs(b-a-1/fps) <= cfg["timestamp_tolerance_s"] for a,b in zip(timestamps,timestamps[1:]))
        indices_ok = [r["frame_index"] for r in group] == list(range(len(group)))
        speed = max((math.dist(a["action"][:3],b["action"][:3])*fps for a,b in zip(group,group[1:])),default=0.0)
        environment = group[-1]["observation.environment_state"]
        distance = math.dist(environment[:2],environment[3:5])
        inside = distance < cfg["geometric_threshold_m"]
        notes = []
        if not shape_ok: notes.append("feature dimension mismatch")
        if not finite: notes.append("nonfinite numeric feature")
        if not dt_ok: notes.append("timestamp step irregular or insufficient frames")
        if not indices_ok: notes.append("noncontiguous per-episode frame indices")
        if speed > cfg["max_command_speed_m_s"]*cfg["speed_warning_multiplier"]: notes.append("action-pose speed exceeds audit threshold")
        if not inside: notes.append("last recorded frame outside 15mm goal radius")
        if len(group) < cfg["minimum_episode_frames"]: notes.append("very short episode")
        episodes.append(dict(episode_index=episode,frames=len(group),duration_s=timestamps[-1]-timestamps[0],dt_ok=dt_ok,shape_ok=shape_ok,finite=finite,frame_indices_ok=indices_ok,peak_action_pose_speed_m_s=speed,speed_unit="m/s",final_recorded_distance_m=distance,inside_15mm_at_last_recorded_frame=inside,notes=notes,visibility="not assessed",reachability="not assessed",acceptance="requires image and reachability review"))
    return dict(dataset=root.name,fps=fps,actual_frames=len(rows),declared_frames=info["total_frames"],frame_count_matches=len(rows)==info["total_frames"],episode_count_matches=len(episodes)==info["total_episodes"],geometric_threshold_m=cfg["geometric_threshold_m"],episodes=episodes,scope="CSV metadata, timing, dimensions, finite values, indices, action-pose finite-difference speed and final recorded distance; not full demonstration acceptance")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["contract","audit","verify"])
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    cfg=json.loads((ROOT/"config.json").read_text())
    data=ROOT/cfg["dataset"]
    if args.mode == "verify":
        manifest=json.loads((ROOT/"MANIFEST.json").read_text())
        mismatches=[p for p,digest in manifest["sha256"].items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=digest]
        if mismatches: raise SystemExit("Manifest mismatch: "+", ".join(mismatches))
        print(f"Verified {len(manifest['sha256'])} distributed files against MANIFEST.json")
        return
    if args.mode == "contract":
        report=json.loads((data/"meta/info.json").read_text())
        report["task_records"]=json.loads((data/"tasks.json").read_text())
        report["representation_note"]="episode-relative position in metres + first two rotation-matrix columns (dimensionless); nine values are not nine joint angles"
        report["split_note"]="Source metadata declares train 0:10; no held-out split has been executed. Design a split before training."
        report["audit_config"]=cfg
        print(json.dumps(report,indent=2))
    else:
        report=audit(data,cfg["numeric"])
        print(f"dataset {report['dataset']}: {len(report['episodes'])} episodes, {report['actual_frames']} frames, nominal {report['fps']} Hz")
        for r in report["episodes"]:
            print(f"ep{r['episode_index']:02}: {r['frames']} frames; dt_ok={r['dt_ok']}; {r['peak_action_pose_speed_m_s']:.3f} m/s; inside15mm={r['inside_15mm_at_last_recorded_frame']}; {'; '.join(r['notes'])}")
        print("Visibility and reachability NOT assessed; geometric success does not accept a demonstration.")
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2)+"\n")

if __name__ == "__main__":
    main()
