# Model source

- `ReBot_Arm_RS.urdf` and `meshes/shared`, `meshes/visual` are copied from
  [Seeed-Projects/reBot-DevArm](https://github.com/Seeed-Projects/reBot-DevArm), folder `Rebot_Arm_description/RS`
  (commit `c247ea9cb0da29cd52c31953659cc8c47e6d1a6e`, 2026-10-04), licence CERN-OHL-W-2.0, see
  `LICENSE.CERN-OHL-W`. Only the meshes that the arm model uses are kept.
- `rebot_b601_rs_pusher.xml` is generated from the URDF by the course simulation repository
  (`tools/build_rebot_mjcf.py`): the gripper and its motor are replaced by the pusher tool under `link6`.
- `tool_pusher.xml` and `tool_handheld.xml` describe the printed tool (flange, 10 x 10 mm rod, phone plate,
  phone body, phone camera `phone`, rod-tip site `tcp`); `meshes/tool/robot_tool.stl` and `hand_tool.stl` are the
  printed parts designed for the course. `handheld_tool.xml` carries the handheld print on a mocap body.
- `table_env.xml` (table, lights, fixed cameras), `objects_push_cube.xml`, `objects_push_t.xml` and the
  `scene_*.xml` files are written for the course: `scene_pusher_*` = arm with the tool, `scene_handheld_*` = the
  tool alone.
