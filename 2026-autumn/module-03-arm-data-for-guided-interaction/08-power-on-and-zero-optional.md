# Optional: power-on and zero

**Optional teaching-team preparation.** The required student task is simulation control. This retained source procedure is not a student instruction to assemble, energise or calibrate a physical arm during class.

This page follows the [assembly guide](08-assembly-optional.md). It takes the assembled arm through its first power-on: the CAN bus, the motor IDs, the zero, the motor parameters and the first bounded motion. The steps follow the three gates of [Class 08](08-lets-build-a-simple-arm-and-turn-it-on.md): do not start a gate before the earlier gate is closed.

***

## Safety rules

{% hint style="danger" %}
**One person keeps control of the power switch at all times and can cut the power without delay.**

**Nobody stays inside the workspace of the arm while the motors are enabled.** The only exception is the drag check: the motors give zero torque or only the gravity torque, one staff member moves the arm by hand, and a second person holds the power switch.

**Read the usage notes at the top of each script before you run it.**

**Stop a script in the way that its notes give, and hold or fold the arm before the torque goes off.** In the motion test, Ctrl-C holds the last target until you press Enter. A tracking abort cuts the torque at once, and the arm can fall.

**The power switch is the emergency stop only. After it, the arm falls to its mechanical stops.**

Only the teaching team operates powered hardware. Do not plug or unplug a motor cable while the supply is on.
{% endhint %}

***

## Before you start

You need an Ubuntu computer, not a virtual machine, with Python 3.12 or 3.13: the arm talks over SocketCAN, a part of the Linux kernel, so macOS cannot run this page.

<details>

<summary>Install uv (once)</summary>

`uv` installs Python and the packages of each class folder. Install it once, following the [uv installation page](https://docs.astral.sh/uv/getting-started/installation/) or with this command, the same on Linux and macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If `curl` is not found, as on a fresh Ubuntu, install it with `sudo apt install curl`, or use `wget` instead:

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```

Open a new terminal afterwards, so that the `uv` command is found. Check it with `uv --version`.

</details>

Get the code and make the environment:

```bash
git clone https://github.com/asEmbodiedAISyst/2026Autumn.git rob7103
cd rob7103
cd 2026-autumn/resources/class08/practical/additional_material
uv sync --group real                  # the drivers of the physical arm
```

{% hint style="info" %}
If you cloned the repository in an earlier class, run `git pull` in the `rob7103` folder instead of `git clone`.
{% endhint %}

***

## Gate A: the assembled arm (power off)

{% stepper %}
{% step %}
### Check the assembly

Go through the final checklist of the [assembly guide](08-assembly-optional.md#final-checklist). Every joint turns by hand through its full range, every cable has slack at the end stops, and the base is clamped to the table.
{% endstep %}

{% step %}
### Check the wiring

The section [How the computer reaches the motors](08-lets-build-a-simple-arm-and-turn-it-on.md#how-the-computer-reaches-the-motors) of the class page shows the chain. The USB-to-CAN adapter connects the computer to the splitter board. The XT30 2+2 cable carries the 48 V supply and the two CAN wires from the splitter board to motor 1. The motors are chained to motor 7. A switch within reach of the operator is in the 48 V line. Set the mains selector of the supply to 230 V for 220 V mains, or to 115 V for 110 V mains.
{% endstep %}

{% step %}
### Check the CAN termination

The DIP switch of the adapter in position 120R gives the termination at the computer end. With the supply off, measure between CAN-H and CAN-L: two 120 Ω resistors in parallel give approximately 60 Ω.
{% endstep %}

{% step %}
### Fold the arm to the zero pose

Fold the arm by hand to the zero pose, gripper closed. The arm starts every power-on from this pose.
{% endstep %}
{% endstepper %}

***

## Gate B: communication, zero and parameters (motors disabled)

{% stepper %}
{% step %}
### Power on and start the CAN bus

Switch the supply on. The motors stay disabled. Start the bus at 1 Mbit/s and scan for the seven motors. These commands are for Ubuntu only: `can0` is a SocketCAN interface of the Linux kernel, and the USB-to-CAN adapter of the kit has no driver for this on macOS.

```bash
sudo modprobe peak_usb
sudo ip link set can0 type can bitrate 1000000 restart-ms 100
sudo ip link set can0 up
ip -details link show can0          # UP, ERROR-ACTIVE
uv run motorbridge-cli scan --vendor robstride --channel can0 --start-id 1 --end-id 7
```

**Expected:** `can0` is `UP` and `ERROR-ACTIVE` at bitrate 1000000, and the [motorbridge](https://github.com/motorbridge/motorbridge) scan reports `scan done: 7 motor(s) found`.
{% endstep %}

{% step %}
### Check the motor IDs

Each motor has an ID on the bus, 1 to 7 in the order of the joint table. The motors of the kit come with their IDs written; the ID is on the label of each housing. A new spare RobStride motor answers on ID 127. Connect one new motor at a time and write its ID with `motorbridge-cli id-set`. Switch the power off before each change of cable. Then scan again to make sure of the new ID.
{% endstep %}

{% step %}
### Connect Motorbridge Studio

[Motorbridge Studio](https://motorbridge.github.io/motorbridge-studio/) is a web page that reads and writes the motor settings. It talks to the bus through a gateway, a local program that connects the web page to `can0`:

```bash
uv run motorbridge-gateway -- --bind 127.0.0.1:9002 --transport socketcan --channel can0
```

Open [https://motorbridge.github.io/motorbridge-studio/](https://motorbridge.github.io/motorbridge-studio/), open the **reBot Arm** tab and click **Connect** (`ws://127.0.0.1:9002`). Select the arm model `rebot-arm-robstride` and click **Scan All Joints**. All seven joints must be online.
{% endstep %}

{% step %}
### Write the zero

<figure><img src="https://raw.githubusercontent.com/asEmbodiedAISyst/2026Autumn/main/2026-autumn/resources/class08/figures/source/motorbridge-studio.png" alt="Motorbridge Studio: the reBot Arm tab, Connect, the arm model, First-time Guide, Scan All Joints and Zero All"><figcaption><p>Figure 1. Motorbridge Studio: the reBot Arm tab, Connect, the arm model, First-time Guide, Scan All Joints and Zero All.</p></figcaption></figure>

Studio has a **First-time Guide** for the first power-on. It makes the zero and the limits a reliable baseline:

1. Under **Arm Model**, select the model of your arm.
2. Place all seven joints by hand in a safe mechanical start pose, with no risk of collision.
3. Click **Scan All Joints** to confirm that all joints are online.
4. When the pose is correct, click **Zero All** and go through its safety confirmations.
5. Click **Read Params** to keep a record, then **Write Default Params**. If something is wrong later, put the arm back in the mechanical zero pose before you calibrate again.

For the reBot arm, the safe start pose is the zero pose: folded, gripper closed. The current pose becomes the zero of all seven motors, and the motors keep it. Studio allows Zero All only when the joints are already near zero. Use the force option only when the arm is really in the mechanical zero pose.
{% endstep %}

{% step %}
### Write the parameter template

Click **Read Params** and keep the old values as a record. Hold the arm, make sure that nobody is near it, and click **Write Default Params**: Studio writes the reBot RobStride values and reads them back. The step passes when the read-back agrees. Then stop the gateway with Ctrl-C.

{% hint style="warning" %}
The gateway holds the CAN bus: no other program can use the bus while it runs.
{% endhint %}
{% endstep %}
{% endstepper %}

### Evidence of Gate B

| Check      | Pass                                                              |
| ---------- | ----------------------------------------------------------------- |
| IDs        | IDs 1–7 answer in the order of the joint table                    |
| Zero       | after a power cycle, the folded pose reads 0° ± 2° on every joint |
| Parameters | the read-back agrees with the template                            |
| Errors     | no error flags                                                    |

Some firmware does not keep the zero through a power cycle. Then write it again.

***

## Gate C: the first motion (supervised)

{% stepper %}
{% step %}
### Drag check with the digital twin

```bash
uv run python code/real_gripper_drag.py --can-port can0 --viewer
```

The script enables the motors with zero output, so the arm is free. A table shows the angle, speed, torque, temperature and state of each motor every 20 ms, and the MuJoCo model follows the measured angles. One staff member moves each joint by hand; a second person holds the power switch.

**Expected:** the twin turns the same joint in the same direction as the arm, the folded pose reads 0° ± 2°, and every motor state is `OK`. A joint that turns the wrong way stops the bring-up. If the folded pose does not read zero, `--rezero` writes the current pose as the motor zero after the operator types `yes`. To stop, hold and fold the arm, then press Ctrl-C: the motors give no support in this mode.
{% endstep %}

{% step %}
### Gravity hold

```bash
uv run python code/real_gripper_drag.py --can-port can0 --mode gravity --viewer
```

The motors give only the gravity torque of the model: no stiffness and a small damping. Hold the arm when it starts. **Expected:** the arm stays where you leave it. If it sinks or drifts, stop and correct the gravity model of that joint before any motion. The first Ctrl-C keeps the compensation: fold the arm, then press Enter.
{% endstep %}

{% step %}
### Joint motion test

```bash
uv run python code/real_gripper_motion_test.py --can-port can0 --joints 2 --viewer
```

The staff member leaves the workspace first. The script holds the zero pose with a soft impedance and the gravity feed-forward. Then it moves each selected joint +10°, back, −10° and back, at 5°/s. A side beyond a soft limit is skipped. Without `--joints` it tests joints 1–6 one at a time. At the end the arm goes back to zero in two stages (joints 1, 4, 5, 6, then 2 and 3), and the torque goes off.

| Event                    | What the script does                               | What the arm does                       |
| ------------------------ | -------------------------------------------------- | --------------------------------------- |
| End of the test          | goes back to zero, then torque off                 | rests in the folded pose                |
| Ctrl-C                   | holds the last target until Enter, then torque off | falls after Enter if you do not hold it |
| Tracking error above 15° | torque off at once                                 | can fall                                |
| Power switch             | no torque                                          | falls to its mechanical stops           |

**Expected** for joint 2: approximately 2° tracking error (2–5° is normal, the abort is at 15°), a peak torque of approximately 2 N m and no temperature rise. The script writes a JSON log to `outputs/real_gripper/`.
{% endstep %}
{% endstepper %}

### After Gate C

Before any task, load the soft limits of the joint table and set a low tool speed limit of 0.05 m/s. The arm must also hold its last target when a teleoperation stream stops. Class 09 checks this with the phone.
