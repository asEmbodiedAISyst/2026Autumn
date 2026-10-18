"""Minimal subset of the course package ``rebot_sim`` for the Class 08 bring-up of the physical arm.

* :mod:`.robot`: joint names, directions, soft limits and unit conversions of the reBot Arm B601-RS;
* :mod:`.sim`: the MuJoCo arm in the gripper table scene (``model/rebot_b601_rs_mjcf/scene_table.xml``);
* :mod:`.viewer_utils`: clean close of the MuJoCo passive viewer;
* :mod:`.real.gripper_arm`: the physical arm with the gripper (7 RobStride motors) and its digital twin.

The scripts in ``code/`` add the parent folder (``additional_material/``) to ``sys.path`` to import it.
"""
