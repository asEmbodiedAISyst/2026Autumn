"""Visual-only letter cube layered onto the pinned native task model."""
import io
import xml.etree.ElementTree as ET
from pathlib import Path
import mujoco
import numpy as np

from native_task import ROOT, NativeReorient, NativeModel

FACE_LETTERS = {'up':'M', 'front':'B', 'left':'Z', 'back':'U', 'right':'A', 'down':'I'}
COLORS = {'M':'#dbeafe','B':'#fde68a','Z':'#d1fae5','U':'#fbcfe8','A':'#fed7aa','I':'#ddd6fe'}

def texture(letter):
    # Distributed artwork is rendered in MiSans; font software is not bundled.
    return (ROOT / 'assets' / 'letters' / (letter + '.png')).read_bytes()

def make_env(labels=True, noise_level=1.0):
    env=NativeReorient(noise_level=noise_level)
    if not labels:return env
    assets={p.name:p.read_bytes() for p in (ROOT/'models').rglob('*') if p.is_file()}
    cube=ET.fromstring(assets['reorientation_cube.xml'])
    asset=cube.find('asset')
    attrs={'name':'course_letters','type':'cube'}
    for face,letter in FACE_LETTERS.items():
        name='course_letter_'+face+'.png';assets[name]=texture(letter);attrs['file'+face]=name
    ET.SubElement(asset,'texture',attrs)
    ET.SubElement(asset,'material',{'name':'course_letters','texture':'course_letters'})
    # Change the zero-density, noncontact display mesh only. The box collision
    # geom and its 108 g mass remain untouched. Apply the same artwork to goal.
    visual=cube.find("worldbody/body/geom[@type='mesh']")
    visual.attrib.pop('mesh');visual.set('type','box');visual.set('size','.035 .035 .035');visual.set('material','course_letters')
    assets['reorientation_cube.xml']=ET.tostring(cube)
    scene=ET.fromstring(assets['scene_mjx_cube.xml'])
    goal=scene.find("worldbody/body[@name='goal']/geom[@type='mesh']")
    goal.attrib.pop('mesh');goal.set('type','box');goal.set('size','.035 .035 .035');goal.set('material','course_letters')
    model=mujoco.MjModel.from_xml_string(ET.tostring(scene,encoding='unicode'),assets=assets)
    model.opt.timestep=env.sim_dt;model.opt.ccd_iterations=10
    model.vis.global_.offwidth=1280;model.vis.global_.offheight=720
    env._mj_model=model;env._mjx_model=NativeModel(model);env._post_init()
    return env

def physics_contract(original, labelled):
    """Compare dynamics, contact geometry, solver, joints, sensors and actuators."""
    fields=('body_mass','body_inertia','body_ipos','body_iquat','body_pos','body_quat',
            'dof_armature','dof_damping','dof_frictionloss','jnt_type','jnt_pos','jnt_axis','jnt_range',
            'actuator_gainprm','actuator_biasprm','actuator_ctrlrange','actuator_forcerange',
            'actuator_forcelimited','jnt_actfrcrange','jnt_actfrclimited','qpos0',
            'sensor_type','sensor_objid','sensor_objtype','sensor_adr','sensor_dim',
            'geom_contype','geom_conaffinity','geom_friction','geom_solref','geom_solimp')
    for name in fields:np.testing.assert_array_equal(getattr(original,name),getattr(labelled,name),err_msg=name)
    contact=(original.geom_contype!=0)|(original.geom_conaffinity!=0)
    for name in ('geom_type','geom_size','geom_pos','geom_quat','geom_bodyid'):
        np.testing.assert_array_equal(getattr(original,name)[contact],getattr(labelled,name)[contact],err_msg=name)
    for name in ('timestep','integrator','solver','iterations','ls_iterations','ccd_iterations','gravity'):
        np.testing.assert_array_equal(getattr(original.opt,name),getattr(labelled.opt,name),err_msg=name)
    return {'passed':True,'array_fields':list(fields),'contact_geoms':int(contact.sum()),
            'visual_changes':'two noncontact zero-density display geoms and new materials/textures only'}
