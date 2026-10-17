"""Recreate raw image inputs for one class. Run with the figure environment:
python code/collect_image_inputs.py --class-root .
No overlays or enhancement; camera/model settings and selected frame numbers are recorded.
"""
from pathlib import Path
import argparse,json,hashlib,sys
import numpy as np
from PIL import Image

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--class-root',type=Path,default=Path(__file__).resolve().parents[1]);args=ap.parse_args();r=args.class_root.resolve();n=int(r.name[-2:]);a=r/'consolidation/package/additional_material';records=[]
 if n==8:
  import mujoco
  sys.path.insert(0,str(a/'code'));from controlled_motion import ArmSim,HOME_QPOS
  s=ArmSim();s.model.vis.global_.offwidth=1200;s.model.vis.global_.offheight=800;render=mujoco.Renderer(s.model,800,1200);cam=mujoco.MjvCamera();cam.lookat[:]=(.24,0,.15);cam.distance=1.05;cam.azimuth=140;cam.elevation=-27
  for name,q in [('zero',np.zeros(6)),('home',HOME_QPOS)]:
   s.reset(q);render.update_scene(s.data,cam);p=r/f'data/arm-{name}.png';Image.fromarray(render.render()).save(p);records.append({'model':'consolidation/package/additional_material/model/rebot_b601_rs_mjcf/scene_table.xml','q_rad':q.tolist(),'camera':{'lookat':cam.lookat.tolist(),'distance':cam.distance,'azimuth':cam.azimuth,'elevation':cam.elevation},'output':str(p.relative_to(r))})
  render.close()
 elif n in [10,11]:
  import cv2
  if n==10:video=a/'data/pilot_push_cube_handheld/videos/observation.images.phone/chunk-000/file-000.mp4';specs=[('pilot-nominal',0),('pilot-turned',116)]
  else:video=a/'data/videos/class11_rollout_pusher_ep000.mp4';specs=[('video-frame-start',0),('video-frame-middle',225),('video-frame-end',449)]
  for name,index in specs:
   c=cv2.VideoCapture(str(video));c.set(cv2.CAP_PROP_POS_FRAMES,index);ok,bgr=c.read();fps=c.get(cv2.CAP_PROP_FPS);c.release()
   if not ok:raise RuntimeError('Cannot decode selected supplied frame')
   p=r/f'data/{name}.png';Image.fromarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)).save(p);records.append({'video':str(video.relative_to(r)),'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'frame':index,'fps':fps,'time_s':index/fps,'output':str(p.relative_to(r))})
 else:raise SystemExit('Class09 figures consume recorded CSV, not extracted video.')
 (r/'evidence/image-inputs.json').write_text(json.dumps(records,indent=2)+'\n');print('Prepared',len(records),'raw inputs')
if __name__=='__main__':main()
