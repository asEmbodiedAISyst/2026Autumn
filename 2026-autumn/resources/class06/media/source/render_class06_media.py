"""Render the selected episode from copied states; never change task physics."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
MEDIA=Path(__file__).resolve().parents[1];sys.path.insert(0,str(MEDIA.parent/'code'))
import mujoco
from lettered_cube import make_env
from test_upstream_onnx import REF,controller_class
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--font',type=Path,required=True);args=p.parse_args();font=ImageFont.truetype(str(args.font),18)
 expected=json.loads((MEDIA/'data/continuous-example.json').read_text())['trace'];out=MEDIA/'data/frames';out.mkdir(parents=True,exist_ok=True)
 env=make_env(True,0.);env.mj_model.vis.global_.offwidth=1920;env.mj_model.vis.global_.offheight=1080;state=env.reset_seed(9204);cls=controller_class();policy=cls(str(REF/'leap_reorient_policy.onnx'),env._hand_qids,env._hand_dqids,state.data.raw.ctrl.copy(),env._lowers,env._uppers,env.n_substeps)
 camera=mujoco.MjvCamera();camera.azimuth=120;camera.elevation=-25;camera.distance=.52;camera.lookat[:]=[.15,.04,.06]
 frames=[];goals=0;events=[];difference=0.
 with mujoco.Renderer(env.mj_model,height=1080,width=1920) as renderer:
  for step in range(1,1001):
   action=policy._policy.run(policy._output_names,{'obs':np.asarray(state.obs['state'],dtype=np.float32).reshape(1,57)})[0][0];state=env.step(state,action)
   event=bool(float(state.metrics['reward/success']));goals+=event
   if event:events.append(step)
   error=float(env._cube_orientation_error(state.data));row=expected[step-1];difference=max(difference,abs(error-row['orientation_error_rad']))
   assert event==row['goal_event'] and goals==row['goals'] and abs(error-row['orientation_error_rad'])<1e-7
   if step in [1,356,761,1000] or step%10==0:
    data=mujoco.MjData(env.mj_model);mujoco.mj_copyData(data,env.mj_model,state.data.raw);mujoco.mj_forward(env.mj_model,data);renderer.update_scene(data,camera=camera);im=Image.fromarray(renderer.render())
    if step in [1,356,761,1000]:im.save(out/f'step-{step:04d}.png')
    if step%10==0:
     frame=Image.new('RGB',(960,572),'white');frame.paste(im.resize((960,540),Image.Resampling.LANCZOS),(0,0));ImageDraw.Draw(frame).text((12,546),f'Selected seed 9204 | t = {step*.05:.2f} s | goal events: {goals}',font=font,fill='black');frames.append(frame)
   if step%200==0:print(f'Media replay: step {step}, events {goals}',flush=True)
 assert events==[356,761] and not bool(state.done)
 frames[0].save(MEDIA/'video/cube-reorientation.gif',save_all=True,append_images=frames[1:],duration=500,loop=0)
 receipt={'seed':9204,'noise_level':0,'steps':1000,'control_dt':.05,'mujoco':mujoco.__version__,'policy_sha256':hashlib.sha256((REF/'leap_reorient_policy.onnx').read_bytes()).hexdigest(),'matched_retained_error_trace':True,'max_error_difference_rad':difference,'event_steps':events,'native_frame_size':[1920,1080],'frame_steps':[1,356,761,1000],'gif_size':[960,572],'gif_sample_steps':10,'gif_frame_duration_ms':500,'font':{'filename':args.font.name,'sha256':hashlib.sha256(args.font.read_bytes()).hexdigest()},'scope':'New rendering of an existing selected episode; no training or new reliability estimate.'}
 (MEDIA/'data/media-replay.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
