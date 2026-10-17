"""Canonical-frame IK audit; no renderer, hardware, policy, or training."""
from pathlib import Path
import argparse
import json
import numpy as np
import mujoco
from lesson_lab import ROOT, load_rows
from rebot_sim.ik import DiffIK
from rebot_sim.pose import EpisodeFrame, tilt_angle, yaw_of
from rebot_sim.sim import RebotSim


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=ROOT/"results/canonical-ik.json")
    args=parser.parse_args()
    config=json.loads((ROOT/"config.json").read_text())
    cfg=config["canonical_ik"]
    rows=load_rows(ROOT/config["dataset"])
    info=json.loads((ROOT/config["dataset"]/"meta/info.json").read_text())
    start_q=np.array(cfg["start_joint_rad"])
    sim=RebotSim(cfg["scene"],cameras=())
    solver=DiffIK(sim.model,posture=start_q,damping=cfg["damping"],posture_gain=cfg["posture_gain"],rot_weight=cfg["rotation_weight"])
    frame=EpisodeFrame(np.array(cfg["start_position_m"]),np.array(cfg["start_rotation"]))
    results=[]
    for ep in sorted({r["episode_index"] for r in rows}):
        group=sorted((r for r in rows if r["episode_index"]==ep),key=lambda r:r["frame_index"])
        poses=[frame.decode(np.array(r["observation.state"])) for r in group]
        q=start_q.copy(); reachable=0; positions=[]; rotations=[]
        for pos,rot in poses:
            result=solver.solve(pos,rot,q,max_iters=cfg["max_iters"])
            if not result.success: result=solver.solve(pos,rot,start_q,max_iters=cfg["retry_max_iters"])
            q=result.q; reachable+=int(result.success); positions.append(pos); rotations.append(rot)
        speed=np.linalg.norm(np.diff(positions,axis=0),axis=1)*info["fps"]
        tilts=np.degrees([tilt_angle(r) for r in rotations]);yaws=np.degrees([yaw_of(r) for r in rotations])
        item=dict(episode_index=ep,frames=len(group),reachable_frames=reachable,reachable_fraction=reachable/len(group),peak_observation_pose_speed_m_s=float(speed.max()),p95_observation_pose_speed_m_s=float(np.percentile(speed,95)),max_tilt_deg=float(tilts.max()),min_yaw_deg=float(yaws.min()),max_yaw_deg=float(yaws.max()))
        item["limit_warning"]=bool(item["reachable_fraction"]<cfg["minimum_reachable_fraction"] or item["peak_observation_pose_speed_m_s"]>config["numeric"]["max_command_speed_m_s"]*config["numeric"]["speed_warning_multiplier"] or item["max_tilt_deg"]>cfg["max_tilt_deg"] or max(abs(item["min_yaw_deg"]),abs(item["max_yaw_deg"]))>cfg["max_yaw_deg"])
        results.append(item)
        print(f"ep{ep:02}: {reachable}/{len(group)} reachable ({item['reachable_fraction']:.0%}); peak {item['peak_observation_pose_speed_m_s']:.3f} m/s; yaw {item['min_yaw_deg']:.1f}..{item['max_yaw_deg']:.1f} deg; warning={item['limit_warning']}",flush=True)
    # A small headless physics check confirms the scene also steps; this is independent of IK acceptance.
    sim.reset(start_q)
    for _ in range(info["fps"]): sim.step()
    physics=dict(control_steps=info["fps"],elapsed_simulation_s=sim.time,all_qpos_finite=bool(np.isfinite(sim.data.qpos).all()))
    report=dict(dataset="pilot_push_cube_handheld",config=cfg,software=dict(mujoco=mujoco.__version__,numpy=np.__version__),episodes=results,physics_smoke=physics,scope="Pose-state IK in this canonical frame/model/solver only; no collision, contact, effort, visibility, global impossibility or physical-operation certificate.")
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+"\n")
    print(f"Headless physics: {physics['control_steps']} steps, {physics['elapsed_simulation_s']:.6f} simulated seconds, finite={physics['all_qpos_finite']}")

if __name__ == "__main__": main()
