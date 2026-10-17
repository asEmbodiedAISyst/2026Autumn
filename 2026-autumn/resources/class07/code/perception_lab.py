"""Known-corner synthetic PnP sensitivity, frame composition and timed packets.
No image detector, live phone, robot, training or recorded hardware data.
"""
from pathlib import Path
import argparse,json,csv
import numpy as np
import cv2
R=Path(__file__).resolve().parents[1]
def estimate_pose(corners,image,K,dist):
 if len(image)<4:return {'valid':False,'reason':'fewer than4correspondences; this lab gate'}
 ok,rr,tt=cv2.solvePnP(corners,image,K,dist,flags=cv2.SOLVEPNP_ITERATIVE)
 return dict(valid=bool(ok and tt[2,0]>0),rvec=rr,tvec=tt)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 out=args.output
 if out.exists():parser.error('Use a fresh output directory; existing evidence is preserved.')
 out.mkdir(parents=True)
 corners=np.array([[-.035,-.035,0],[.035,-.035,0],[.035,.035,0],[-.035,.035,0]],np.float64)
 K=np.array([[700,0,320],[0,700,240],[0,0,1]],np.float64);rv=np.array([.2,-.15,.1]);tv=np.array([.02,-.01,.45]);dist=np.zeros(5)
 pixels=cv2.projectPoints(corners,rv,tv,K,dist)[0].reshape(-1,2);rot=cv2.Rodrigues(rv)[0]
 rows=[];rng=np.random.default_rng(7)
 for sigma in [0,.25,.5,1.,2.]:
  for trial in range(100):
   image=pixels+rng.normal(0,sigma,pixels.shape)
   estimate=estimate_pose(corners,image,K,dist)
   assert estimate['valid'];rr,tt=estimate['rvec'],estimate['tvec']
   er=cv2.Rodrigues(rr)[0];angle=np.arccos(np.clip((np.trace(er@rot.T)-1)/2,-1,1))
   reproj=cv2.projectPoints(corners,rr,tt,K,dist)[0].reshape(-1,2)
   rows.append(dict(pixel_sigma=sigma,trial=trial,translation_error_mm=float(np.linalg.norm(tt.ravel()-tv)*1000),rotation_error_deg=float(np.rad2deg(angle)),reprojection_rmse_px=float(np.sqrt(np.mean(np.sum((reproj-image)**2,axis=1))))))
 assert max(x['translation_error_mm'] for x in rows if x['pixel_sigma']==0)<1e-4
 assert max(x['rotation_error_deg'] for x in rows if x['pixel_sigma']==0)<1e-3
 with (out/'pnp-trials.csv').open('w') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 occluded=estimate_pose(corners[:3],pixels[:3],K,dist);assert not occluded['valid']
 summary=[]
 for sigma in [0,.25,.5,1.,2.]:
  rr=[x for x in rows if x['pixel_sigma']==sigma];summary.append(dict(pixel_sigma=sigma,trials=100,median_translation_mm=float(np.median([x['translation_error_mm'] for x in rr])),median_rotation_deg=float(np.median([x['rotation_error_deg'] for x in rr])),p90_rotation_deg=float(np.percentile([x['rotation_error_deg'] for x in rr],90))))
 # Explicit planar rigid transform arithmetic, embedded in3D.
 R_HC=np.array([[0,-1,0],[1,0,0],[0,0,1]],float);p_HC=np.array([.1,0,0]);p_CO=np.array([.2,.03,.4]);p_HO=R_HC@p_CO+p_HC;np.testing.assert_allclose(p_HO,[.07,.2,.4])
 #100control samples, one deterministic visibility gap; delay3samples, holdlast.
 packets=[];last=None;last_time=0.
 for i in range(100):
  t=i*.05;source=max(0,i-3);capt=source*.05;valid=not 35<=i<45
  if last is None or valid:last=float(.4*np.sin(2*np.pi*.5*capt));last_time=capt
  packets.append(dict(time_s=t,true_yaw_rad=float(.4*np.sin(2*np.pi*.5*t)),delivered_yaw_rad=last,capture_time_s=last_time,age_s=t-last_time,valid_detection=valid,stale=t-last_time>.2))
 result=dict(scope='Synthetic known-corner projection/PnP and timing exercises; no camera recordings or learned vision',seed=7,opencv=cv2.__version__,K=K.tolist(),distortion=dist.tolist(),object_corners_m=corners.tolist(),rvec_object_to_camera=rv.tolist(),tvec_object_to_camera_m=tv.tolist(),projected_pixels=pixels.tolist(),trials=summary,frame_example=dict(p_HC_m=p_HC.tolist(),R_HC=R_HC.tolist(),p_CO_m=p_CO.tolist(),p_HO_m=p_HO.tolist()),occlusion_example=occluded,occlusion_rule='Require all4correspondences in this lab; three available => missing, not a new pose',packets=packets)
 (out/'perception-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['packets']},indent=2))
if __name__=='__main__':main()
