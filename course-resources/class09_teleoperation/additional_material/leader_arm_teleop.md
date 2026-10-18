# Optional: teleoperation with a leader arm (reBot Arm 102)

This guide is extra material. The class uses the phone (asMagic) for teleoperation. A second way is a **leader
arm**: a small passive arm that you move by hand, and the reBot Arm B601-RS (the follower) copies its joint angles.
This is the method of the vendor LeRobot pipeline. Use this guide if your team has a reBot Arm 102 and wants
joint-space teleoperation.

Status: this is the vendor procedure (Seeed wiki and driver repositories, read on 15 October 2026). The course
team has not run it on the course arm. Report problems to the teaching team.

## Phone or leader arm

| | Phone (Class 09 scripts) | Leader arm (this guide) |
| --- | --- | --- |
| What the operator moves | the phone, in Cartesian space | a copy of the arm, joint by joint |
| Mapping | clutch, frame transform, inverse kinematics | direct: leader joint angle = follower joint target |
| Extra hardware | an iPhone with asMagic | the reBot Arm 102 (7 servos, USB-to-UART cable) |
| Software | `code/teleop_rebot_rs_real.py` | vendor LeRobot fork + `lerobot-teleoperator-rebot-arm-102` + `lerobot-robot-seeed-b601` |
| Dataset | the Class 09 recording format | a LeRobot dataset of joint positions (`seeed_b601_rs_follower`) |

The leader arm has no inverse kinematics and no workspace limit in Cartesian space: the follower goes where the
leader joints go, inside the joint limits of the driver. Datasets of the two methods have different state and
action spaces. Do not mix them without a conversion.

## Safety rules

**One person keeps control of the power switch of the follower at all times and can cut the power without
delay. Nobody stays inside the workspace of the follower while its motors are enabled; the operator of the leader
stands outside the reach of the follower. Read the usage notes of each command before you run it. To stop
normally, stop the program (Ctrl+C) and wait until the follower is at rest with its motors disabled. The power
switch is the emergency stop only; after it the arm falls.**

Vendor rule: if the power of either arm drops, a contact is poor or a signal cable comes off during
teleoperation, first stop the program and move the follower back to its folded zero pose. Then connect the power
again and start the program again.

## 1. Before you start

1. Complete the Class 08 bring-up of the follower: wiring, `can0` at 1 Mbit/s, motor IDs 1 to 7, the zero in the
   folded pose and the default parameter template written in Motorbridge Studio, the drag check and the joint
   motion test.
2. Stop `motorbridge-gateway` if it runs. It holds the CAN bus, and the LeRobot driver cannot connect.
3. Connect the reBot Arm 102 to the computer with its USB-to-UART cable. It usually appears as `/dev/ttyUSB0`:

   ```bash
   ls /dev/ttyUSB*
   sudo dmesg | grep ttyUSB          # if the last line says "disconnected", brltty took the port
   sudo apt remove brltty            # only if brltty takes the port
   sudo chmod 666 /dev/ttyUSB0
   ```

## 2. Install the vendor software

The vendor uses a Conda environment with Python 3.12 and its own LeRobot fork. Keep it separate from the course
`uv` environments.

```bash
mkdir ~/rebot_lerobot && cd ~/rebot_lerobot
git clone https://github.com/Seeed-Projects/lerobot.git
conda create -y -n lerobot python=3.12
conda activate lerobot
pip install -e ./lerobot
pip install lerobot-teleoperator-rebot-arm-102 lerobot-robot-seeed-b601 motorbridge
conda install ffmpeg -c conda-forge
python -c "import torch; print(torch.cuda.is_available())"   # False = CPU build (enough for teleoperation)
```

## 3. Calibrate both arms

The calibration files are in `~/.cache/huggingface/lerobot/calibration/robots/` (follower) and
`.../teleoperators/` (leader). To calibrate again, delete the old file first.

**Follower.** Fold the arm to the zero pose of Class 08 (all joints at zero, gripper fully closed). The vendor
command writes the motor zero at the current pose, so the pose must be exact:

```bash
sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
lerobot-calibrate --robot.type=seeed_b601_rs_follower --robot.port=can0 \
    --robot.id=follower1 --robot.can_adapter=socketcan
```

**Leader.** Move the leader to its zero pose (the same folded shape as the follower, gripper closed). Hold it
still and press Enter at each prompt. The calibration sets the current position of each servo to zero:

```bash
lerobot-calibrate --teleop.type=rebot_arm_102_leader --teleop.port=/dev/ttyUSB0 \
    --teleop.id=rebot_arm_102_leader
```

Check the leader. In the zero pose every value must read 0.00; move one joint at a time and check that the
correct column changes:

```bash
git clone https://github.com/Seeed-Projects/lerobot-teleoperator-rebot-arm-102.git
python lerobot-teleoperator-rebot-arm-102/examples/read_raw_angles.py --port /dev/ttyUSB0
```

Leader servo IDs: shoulder_pan 0, shoulder_lift 1, elbow_flex 2, wrist_flex 3, wrist_yaw 4, wrist_roll 5,
gripper 6. The leader joint ranges come from `config_rebot_arm_102_leader.py`, not from the calibration. The joint
directions of the follower come from the follower configuration (the direction vector of Class 08). If one joint
moves the wrong way, change the configuration; do not calibrate again.

Optional direction check without motion of the follower: `examples/read_leader_follower_compare.py` disables the
follower torque and prints the leader, the follower and the difference per joint (see its `--help` for the
follower type and port options).

## 4. Teleoperate

```bash
lerobot-teleoperate \
    --robot.type=seeed_b601_rs_follower --robot.port=can0 --robot.id=follower1 --robot.can_adapter=socketcan \
    --teleop.type=rebot_arm_102_leader --teleop.port=/dev/ttyUSB0 --teleop.id=rebot_arm_102_leader
```

Start with the leader near the pose of the follower. Move slowly at first. To see cameras during teleoperation,
add `--robot.cameras="{ front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30, fourcc: "MJPG"}}"`
and `--display_data=true`; `lerobot-find-cameras opencv` lists the camera indices.

## 5. Record a dataset (optional)

```bash
lerobot-record \
    --robot.type=seeed_b601_rs_follower --robot.port=can0 --robot.id=follower1 --robot.can_adapter=socketcan \
    --robot.cameras="{ front: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30, fourcc: "MJPG"}}" \
    --teleop.type=rebot_arm_102_leader --teleop.port=/dev/ttyUSB0 --teleop.id=rebot_arm_102_leader \
    --display_data=true --dataset.repo_id=local/leader_test --dataset.num_episodes=5 \
    --dataset.single_task="Push the black cube into the green target area." \
    --dataset.push_to_hub=false --dataset.episode_time_s=30 --dataset.reset_time_s=30
```

Keys: Right arrow ends the episode early, Left arrow records it again, Esc stops the session. The dataset goes to
`~/.cache/huggingface/lerobot/local/leader_test`. Apply the Class 10 audit to it before you train on it.

## Sources

- Seeed wiki, reBot Arm B601-RS in LeRobot: <https://wiki.seeedstudio.com/rebot_arm_b601_rs_lerobot/>
- Seeed wiki, getting started (wiring, Motorbridge Studio): <https://wiki.seeedstudio.com/rebot_b601_rs_getting_started/>
- Leader driver: <https://github.com/Seeed-Projects/lerobot-teleoperator-rebot-arm-102>
- Follower driver: <https://github.com/Seeed-Projects/lerobot-robot-seeed-b601>
- No-code alternative from the vendor (SenseCraft Robotics) supports the reBot Arm 102 with the B601-RS.
