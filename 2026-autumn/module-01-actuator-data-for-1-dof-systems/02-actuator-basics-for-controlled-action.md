---
description: 21 October 2026 · CR6
---

# 02 Actuator Basics for Controlled Action

**What turns a motor into an actuator capable of controlled action?** A motor produces torque, but a useful robotic joint must also accept a meaningful command, transfer effort to a mechanism, observe its state and respond within operating limits. We follow that process through the ROBOTIS XC330/XL330 and RobStride RS06/RS00 families.

The class develops three abilities: distinguish a motor from an integrated actuator; distinguish a command, an internal reference and a measured response; and read the exact model's specifications, interfaces and operating limits. The teaching-team demonstration connects application software to physical action and returning telemetry. The final activity is an unpowered XC330 inspection and an XC330/XL330 comparison.

The inspection and comparison activity is in Section 7. [Detailed technical reading](../resources/class02/reading-notes.md) · [Optional telemetry calculations](../resources/class02/telemetry-worked-example.md)

## 1. Controlled action as a physical feedback process

### Begin with the object

Look at the actuator before opening a program. Find the model label, output, mounting features and connectors. Identify which parts move relative to the housing. A mounted actuator is already part of a mechanical system: its mounting provides a reaction to the torque applied at its output.

![Physical XC330 and geometric representation](../.gitbook/assets/class02/01-actuator-and-geometry.png)

*Figure 1. A physical XC330 beside its geometric representation. Identify the output and fixed mounting. Similar geometry helps locate interfaces, but does not establish similar behavior. [Figure source and code](../resources/class02/media/FIGURE-CODE.md#hardware-identity).*

**Predict:** a host requests a change of thirty degrees. Does the output jump, move gradually, oscillate or remain still? Name a physical condition and a controller setting that could change your prediction.

---

### Motor, transmission and integrated actuator

A motor converts electrical energy into mechanical work. An integrated actuator adds a transmission, output support, sensing, drive electronics, embedded control and a communication interface. Together, these parts turn a request into controlled action. A host application can be simple because substantial control already takes place inside the device.

The host supplies information; the electrical supply provides energy. A correct communication packet cannot move an unpowered mechanism. Conversely, connecting power does not specify the movement. The controller must interpret a command in the selected mode, and the drive must produce suitable motor effort.

The transmission connects the motor to the output. With reduction ratio $$N=\omega_m/\dot q$$, the motor rotates faster than the output. A simple steady transmission relationship is

$$
\tau_{\mathrm{out}}\approx\eta N\tau_m.
$$

Here $$q$$ is output angle, $$\omega_m$$ is motor angular velocity and $$\eta$$ represents efficiency. A 100:1 reduction gives an ideal output speed of 10 r/min from a motor speed of 1,000 r/min. Reduction trades speed for effort; it does not remove losses, backlash, compliance or thermal limits. Detailed motor and reflected-inertia derivations remain in the technical reading.

---

### Sensing makes correction possible

Let $$q(t)$$ describe physical output position and $$y(t)$$ its reported position measurement. A controller uses the measurement to compare what the mechanism is doing with what it should do. The encoder, controller and drive therefore belong to the actuator system even when they are hidden inside one housing.

Mechanical power at the output is

$$
P_{\mathrm{out}}=\tau_{\mathrm{out}}\dot q.
$$

An illustrative 0.10 N m at 2 rad/s gives 0.20 W. A stationary output has zero instantaneous mechanical power even while applying torque. Electrical losses can still produce heat. Holding a load and moving a load are consequently different operating conditions.

The mounting matters as much as the moving output. An unsecured housing can turn instead of providing the intended joint action. A useful experiment identifies what is fixed, what moves, what is measured and which reference direction is positive. These choices carry directly into the digital model in Class 03.

**Check:** identify the component that supplies energy, the component that estimates position and the component that decides how the drive responds. Which of those roles can be inferred merely from a CAD image?

## 2. Position, velocity and current-related control

### A request has meaning only through its interface

A position request specifies a target angle. A velocity request specifies how fast the output should move. A current request specifies a current-related quantity in the device's control interface. These commands answer different questions, even if they share the same communication cable.

| Mode or interface | Requested quantity | What the controller must still manage |
|---|---|---|
| Position | Desired angle | Trajectory, effort, feedback and position limits |
| Velocity | Desired angular speed | Acceleration, effort and accumulated travel |
| Current | Current-related target | Current regulation, electrical limits and mechanical response |
| Current-based position | Position with current-related control/limiting | Position/profile behavior and current-related limits |
| PWM | Drive modulation | Actual voltage, current, speed and load |

For a velocity request, position continues to change. Requesting zero velocity and requesting a particular position are therefore different instructions. For a current request, speed depends on the mechanism and load; the request does not prescribe one angle or one speed.

---

### Command, internal reference and measured response

Distinguish four quantities:

- $$u(t)$$: the host request, or an explicitly named goal-register readback;
- $$r(t)$$: the internal desired trajectory;
- $$q(t)$$: physical output position;
- $$y(t)$$: the reported position measurement.

Firmware can turn a sudden target into a gradual reference. Finite effort, inertia, resistance and load then affect the response. The signals have different identities even when their numerical values coincide. They can agree at a settled target; they need not be unequal at all times.

On XC330, Goal Position at address 116 holds the goal, Position Trajectory at 140 exposes an internal desired position, and Present Position at 132 reports encoder position. A later goal-register readback is also distinct from the host's original write and its timestamp.

![Measured goal, internal reference and position](../.gitbook/assets/class02/02-command-reference-response.png)

*Figure 2. Three reported position signals from one physical XC330 episode. Left: the complete 13-second record. Right: a fixed first-reversal window, with original row 400 marked. Positions use count 2,048 as their declared zero; the horizontal axis is host receive-end time. [Data and interpretation](../resources/class02/data/xc330-hardware-demo/README.md) · [Figure code](../resources/class02/media/FIGURE-CODE.md#telemetry-motion).*

Read the reversal before doing arithmetic. The goal, internal reference and output separate while the movement changes direction. At the marked sample their relative angles are approximately 24.785°, 25.400° and 26.279°. Those observations help distinguish a requested target from the device's internal trajectory and the moving mechanism.

---

### Position holding, speed regulation and effort

Imagine three instructions applied to the same suitably configured joint. “Hold this angle” asks for position regulation. “Turn at a small constant speed” asks for velocity regulation. “Apply this current-related target” asks the drive to regulate an electrical quantity whose mechanical effect depends on the motor, transmission and load.

A slow response can have several explanations. The profile may deliberately move slowly; an effort limit may restrict acceleration; or the load may resist motion. Comparing $$u$$, $$r$$ and $$y$$ helps distinguish these cases. If $$r$$ is slow, the output may be correctly following a shaped reference. If $$r$$ changes while $$y$$ barely moves, inspect limits, configuration, faults and the mechanical system.

Current is useful telemetry, but its meaning is model-specific. XC330 reports input-supply current. That channel is not an independent measurement of output torque or motor winding phase current. A requested torque, an estimated torque and a calibrated torque measurement must be named separately. A simulator's torque command does not become a verified physical torque merely because its units are N m.

**Check:** can an actuator use electrical power while maintaining almost constant position? Can a velocity command run out of mechanical travel? Explain both using the requested quantity and the physical system.

## 3. XC330 and XL330: what smart actuation means

### Read the exact model name

The XC330-M288-T integrates a coreless DC motor, metal reduction gears, output bearings, a contactless absolute encoder, electronics and firmware. Its TTL interface carries digital instructions and status information. This integration is what makes the device convenient to use as a smart actuator; it does not guarantee a particular application accuracy or calibrated force sensing.

XC330 and XL330 are not interchangeable names for the same internal mechanism. The following exact-model values come from the ROBOTIS documents (ROBOTIS n.d.a; ROBOTIS n.d.b).

| Attribute | XC330-M288-T | XL330-M288-T |
|---|---|---|
| Motor and gears | Coreless DC; metal gears | Cored motor; engineering-plastic gears |
| Mass | 23 g | 18 g |
| Dimensions | 20 × 34 × 26 mm | 20 × 34 × 26 mm |
| Stall torque at 5.0 V | 0.93 N m | 0.52 N m |
| No-load speed at 5.0 V | 81 r/min | 103 r/min |
| Encoder resolution | 4,096 counts/revolution | 4,096 counts/revolution |

Both documents specify a 3.7–6.0 V input range with 5.0 V recommended, and a TTL multidrop interface. Similar external dimensions make this a useful comparison: matching shape does not imply identical materials, mass, effort or speed.

---

### Interpret the ratings

**Worked comparison:** at 5 V, XC330 has the greater specified stall torque, while XL330 has the greater no-load speed. Which is preferable depends on the intended task. Holding or accelerating a mechanism, achieving speed, reducing moving mass and choosing cost or durability can lead to different decisions.

Stall torque and no-load speed describe different test conditions. Stall means zero speed; no-load speed concerns very small external mechanical load. Multiplying the two extremes does not give an achievable continuous power. Sustained behavior additionally depends on heat transfer and operating limits.

A 12-bit encoder represents one revolution using 4,096 counts:

$$
\Delta q=\frac{360}{4096}\approx0.08789\text{ degrees per count}.
$$

This is resolution. Accuracy concerns agreement with the actual physical angle under stated conditions. Backlash, compliance, zero choice, assembly and calibration can affect accuracy even when the count increment is small. More digits in a log do not remove those effects.

### Firmware is part of the system

The configured mode, gains, profiles and limits affect action. Changing Operating Mode can reset related fields; read configuration back after a change. A gain register value such as 800 is not automatically a physical stiffness of 800 N m/rad. An ID identifies a device, while a control-table address identifies a field within it.

In the recorded example, ID 5 uses baud selection 6, corresponding to 4 Mbit/s. That is communication speed. A logger receiving approximately 200 readings each second has an approximately 5 ms polling interval; neither number establishes the internal servo-loop frequency.

**Check:** find one property that XC330 and XL330 share and one that differs. Include the exact model, unit and condition. Explain why “both are 12-bit” is insufficient evidence that they will have identical positioning accuracy.

## 4. RS06 and RS00: proprioceptive and quasi-direct-drive actuation

### A different balance of motor and transmission

A quasi-direct-drive actuator combines a motor with a comparatively low reduction ratio. RS06 and RS00 use ratios of 9:1 and 10:1, respectively, rather than XC330-M288-T's approximately 288:1. Low reduction changes the trade between motor effort, speed, reflected inertia, friction and backdrivability. It is a design choice, not a universal performance ranking.

For an ideal transmission, $$\omega_m=N\dot q$$. A 1 rad/s output therefore corresponds to approximately 9 rad/s at the RS06 motor and approximately 288 rad/s at the XC330 motor. This comparison concerns the transmission relationship; it does not establish that both devices can deliver the same output effort under those conditions.

Motor inertia reflected to the output scales with $$N^2J_m$$ in the simple rigid-transmission model. Holding the same motor inertia fixed, increasing reduction increases that reflected term. Real devices have different motors, gear losses, elasticity and controls, so comparing gear ratios alone is insufficient to compare measured joint behavior. Class 03 will connect these physical properties to a mechanical model.

---

### What proprioception provides

In this context, proprioception means sensing variables associated with the actuator's own state: position, velocity, electrical current, temperature and status. These signals help regulate and interpret action. Their usefulness depends on where and how each quantity is measured or estimated.

The RS06/RS00 manuals describe three-phase motors, field-oriented control, position sensing and CAN communication. Current-related control and reported joint state can support compliant or effort-sensitive behavior. A current-based torque estimate still depends on the device model, calibration and transmission. It is not automatically an independent external force/torque measurement.

An actuator does not acquire whole-body intelligence merely by reporting its own state. That state becomes useful when the application connects it to a task, mechanism, environment and action policy. This is the same distinction we made between receiving a valid position packet and accomplishing a physical movement.

### Compare the two exact models

The following values refer to the supplied revision 260713 manuals, not to every device sold under a similar name (RobStride Dynamics Co., Ltd. 2026a, 2026b).

| Attribute | RS06 | RS00 |
|---|---|---|
| Rated voltage | 48 V DC | 48 V DC |
| Operating voltage range | 15–60 V DC | 24–60 V DC |
| Reduction | 9:1 | 10:1 |
| Mass | 621 ± 3 g | 310 ± 3 g |
| Rated load in the manual | 11 N m at 100 r/min, with specified cooling | 5 N m at 100 r/min, with specified cooling |
| Peak load in the manual | 36 N m | 14 N m |
| Communication | CAN, specified 1 Mbit/s | CAN, specified 1 Mbit/s |

Read the associated thermal test and mounting conditions before using the load figures. These are not directly equivalent to the XC330 stall rating. A larger numerical value does not by itself answer whether the actuator is appropriate for a particular mechanism or task.

---

### Connect the interface to a control law

The RS06 manual's operation-control interface expresses a torque reference using desired position, desired velocity, proportional and damping terms, and a feedforward contribution. A corresponding joint-level expression is

$$
\tau_{\mathrm{ref}}
=K_p(q_d-y)+K_d(\dot q_d-\hat v)+\tau_{\mathrm{ff}}.
$$

Here $$q_d$$ and $$\dot q_d$$ are desired position and velocity, $$y$$ is position feedback, and $$\hat v$$ is the device's velocity estimate. Keeping feedback distinct from physical $$q$$ preserves the signal definitions of Section 2. The equation describes requested controller effort; it does not establish that physical output torque equals that reference at every instant. Limits, transmission effects and estimation remain relevant.

**Worked example:** assume a hypothetical $$K_p=2$$ N m/rad, a position error of 0.10 rad, zero velocity error and zero feedforward. The proportional contribution is 0.20 N m. If velocity error is −0.20 rad/s and hypothetical $$K_d=0.10$$ N m s/rad, damping contributes −0.02 N m, giving a 0.18 N m reference. These numbers explain the equation; they are not station settings or a measured output-torque result.

An XC330 gain register cannot be substituted for this $$K_p$$ without a defined mapping. Likewise, DYNAMIXEL packets, IDs and register addresses cannot be sent unchanged to a RobStride CAN interface. The host software must respect each device's protocol, units, supported modes and status feedback.

Brushless motors, strain-wave transmissions and other actuator constructions extend these design choices. A motor, a reduction mechanism and an integrated joint remain different objects. Our two families are enough to examine that distinction without surveying every commercial product.

**Check:** which parts of the RS06 control equation describe a target, feedback, a gain and an effort reference? Which extra evidence would you need to call the reported quantity a calibrated physical output torque?

## 5. Read documents, interfaces and operating limits

### Find what each document can tell you

Use the **user manual** for installation, wiring, modes, registers, protocol behavior and operating restrictions. Use a **technical data sheet** for ratings, dimensions, interfaces and test conditions. Read the manufacturer's safety instructions with both. Document names vary, so inspect what the source actually contains rather than relying on an invented universal abbreviation.

A Safety Data Sheet normally concerns hazards of a substance or mixture. An actuator manual's safety section is not automatically an SDS. A lubricant, adhesive or battery used with the station can have its own relevant documentation.

For an actuator, a useful specification states the quantity, unit, condition and interpretation. “Torque: 0.93” is incomplete. “0.93 N m stall torque at 5 V” describes a particular rating, while a sustained joint task needs further thermal and operating information.

---

### Follow the command path through real components

The demonstration follows **application → asBrain/interface → actuator → telemetry**. At each boundary identify what is sent, what carries it, which device interprets it and what returns. If the station uses another supported interface, name it explicitly and follow the same boundaries.

![Physical actuator, cable, interface and hub](../.gitbook/assets/class02/03-interface-components.png)

*Figure 3. Actuator ports, three-conductor cable, U2D2 and power hub. The USB-to-bus interface carries host data; the hub provides a connection for external actuator power. [Figure source and code](../resources/class02/media/FIGURE-CODE.md#communication-parts).*

The two XC330 bus ports are equivalent connections to shared data, supply and ground. Daisy chaining extends the bus; cable order does not assign a device ID. An ID identifies the actuator, an address identifies one field inside it, and baud defines communication speed. A USB interface is not a substitute for the actuator's required external supply.

---

![Unpowered component arrangement](../.gitbook/assets/class02/04-connection-inspection.png)

*Figure 4. The supplied component arrangement does not show the USB lead or external power source attached. Use it to identify components and missing connections. Consult the exact wiring source before energizing a station. [Figure source and code](../resources/class02/media/FIGURE-CODE.md#connection-inspection).*

For RS06/RS00, identify the CAN adapter, bus wiring, supply and model-specific protocol instead. Verify the selected interface/protocol and reported device identity. Similar host software does not make TTL and CAN connectors, supply voltages or message formats interchangeable.

### Read limits before interpreting a response

Connect limits to the intended action: position travel, speed, acceleration/profile settings, current or drive limits, temperature, mounting and cooling. A command may be syntactically valid yet inconsistent with the mechanism's travel or the station's operating conditions. A fault or protection response can also explain why the output stops following a request.

Keep a concise record: exact model and firmware, interface and units, operating mode, gains/profile/limits, mechanical mounting/load, and the reported signals. Distinguish a documented rating from a station readback and from a measured response. Those are three different sources of knowledge.

**Before the break:** choose one entry from the XC330 document and one from an RS06/RS00 manual. State what the entry tells you and what it leaves unresolved for a particular task. Next, the teaching team will show how those definitions meet an actual or recorded station.

## Break

Prepare the demonstration view and the unpowered XC330 units for the final inspection. The next part follows the command and returning telemetry; students operate no powered station.

## 6. Teaching-team demonstration

### Identify the station and trace the path

Start at the application. Identify the connected device, the asBrain or other configured interface, the actuator's model/firmware and its mode. Trace the physical communication and power connections. Point to the output, mounting and available feedback. Ask the class to distinguish the target shown in the application from the returning state.

Read the station's actual configuration rather than assuming defaults. Show the selected travel, profile and effort bounds and the available stop action. The teaching team performs powered operation using its prepared station procedure. The supplied photographs and frozen configuration provide the corresponding recorded fallback.

### Show a bounded position request and its response

Use a small request already qualified for the mounted station. Ask for a prediction, then show the requested target, internal reference where exposed, measured position and status. Explain a shaped reference, a lagging physical response and a settled target using the signal identities from Section 2. Return to the prepared state through the station procedure.

For the recorded route, Figure 2 provides the same observation questions. The supplied Mode 5 episode contains 2,601 readings from a motor-only XC330. Read the three position values at the marked reversal; a full conversion exercise is optional rather than a required part of this demonstration.

### Compare supported modes and device interfaces

Show the meaning of a second supported mode through a qualified station operation or a clearly identified existing recording. Position mode and current-based position mode are useful examples: both accept a position request, while their configured effort/control behavior differs. Velocity or current operation can be shown only when that station's prepared procedure covers it. A mode-selection menu alone does not demonstrate physical behavior.

For the recorded alternative, the retained Mode 3 step and Mode 5 records show two actual configurations. They come from different devices/assemblies and are **not a controlled comparison of mode performance**. Use them to identify requests and feedback. Use the RS06/RS00 manual and the actual station readback to compare CAN interface and operation-control quantities with the XC330 control table.

### Interpret the response and close the station

Choose a position, current-related, temperature or fault field and explain what it reports. Name one quantity the field does not independently measure. Ask the class to identify the complete application-to-telemetry path again, then close or disable the station using the teaching team's procedure.

A recorded demonstration preserves the same questions when powered equipment is unavailable. The [supporting resource guide](../resources/class02/README.md) identifies the offline files. The teaching team prepares and qualifies the powered station. No package installation, full campaign audit or parameter fitting belongs during the demonstration.

## 7. Student activity: unpowered inspection and comparison

Each student inspects an **unpowered XC330** and returns it. Teams then compare XC330-M288-T and XL330-M288-T using official documentation and the lesson's specification extract. Keep power disconnected; do not disassemble the device or force the output.

### Inspect and identify

Find the exact model label, output, mounting features and connectors. Identify what moves relative to the fixed housing. Record the available feedback quantities from the documentation, distinguishing them from visible physical features.

Each student returns the unit after inspection. If units are limited, rotate them within the team; the supplied photographs support identification while waiting.

### Compare the exact models

Use the [XC330 source](https://docs.robotis.com/docs/dxl/model_reference/x_series/xc_series/xc330-m288/) and [XL330 source](https://docs.robotis.com/docs/dxl/model_reference/x_series/xl_series/xl330-m288/) or the lesson's attributed extract.

| Comparison | Your response |
|---|---|
| One shared property | Name it; include units where relevant |
| Construction or mass difference | State the exact models and values/materials |
| Torque or speed difference | Include the unit, supply voltage and rating condition |
| Implication for an intended use | Explain which property matters and why |

Can the quoted stall torque and no-load speed be obtained simultaneously? Does 4,096 counts/revolution establish positioning accuracy? Use the definitions in the lesson.

### Record and return

Check that all units have been returned. Submit one short team comparison with labelled inspection notes, model-specific evidence and the interpretation. Use the [printable record](../.gitbook/assets/class02/Class02-Activity.pdf) or equivalent notes.

No software installation, powered operation, raw-data conversion or parameter fitting is required. Optional follow-up: locate three research examples using XC330/XL330; record the exact model and role, or state that the exact model could not be verified.

## 8. Optional follow-up and the next class

Find three research examples using XC330/XL330. Record the exact model, the role it plays, the source and what the source actually establishes. If an exact model cannot be verified, record that uncertainty rather than inferring it from a photograph.

For further study, [telemetry calculations](../resources/class02/telemetry-worked-example.md) develop raw-to-engineering conversions and the distinction between tracking error and a Sim2Real comparison. The [technical reading](../resources/class02/reading-notes.md) develops motor equations, step/frequency responses and the retained XC330/RS06 studies. These are supporting resources, not replacements for the planned Class 02 activity.

Class 03 asks what a digital representation of this physical system must preserve. Geometry, frames, joints, moving mass, inertia and the actuator interface follow from the boundaries identified here. A visually similar model is a starting point; behavior must be investigated as well.

## References and documents

ROBOTIS. n.d.a. “XC330-M288-T.” *ROBOTIS Documentation*. Accessed October 17, 2026. [Exact-model documentation](https://docs.robotis.com/docs/dxl/model_reference/x_series/xc_series/xc330-m288/).

ROBOTIS. n.d.b. “XL330-M288-T.” *ROBOTIS Documentation*. Accessed October 17, 2026. [Exact-model documentation](https://docs.robotis.com/docs/dxl/model_reference/x_series/xl_series/xl330-m288/).

RobStride Dynamics Co., Ltd. 2026a. *RS06 User Manual*. Revision 260713. [Supplied source](../.gitbook/assets/class02/RobStride_RS06_User_Manual_260713.pdf), Sections 1, 2 and 4.3.

RobStride Dynamics Co., Ltd. 2026b. *RS00 User Manual*. Revision 260713. [Supplied source](../.gitbook/assets/class02/RobStride_RS00_User_Manual_260713.pdf), Sections 1 and 2.

Photographs and the matched CAD view were supplied by Mohamad Halwani. [Figure inputs and generation code](../resources/class02/media/FIGURE-CODE.md) · [Record identity](../resources/class02/data/xc330-hardware-demo/README.md).
