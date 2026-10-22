# Class 03 student guide — fixture digitization and MJCF inspection

## What this class is about

This class converts an identified physical fixture into a mechanically meaningful MuJoCo model. The B0 moving assembly has an accepted external moving mass of 110 g: a 22 g link and two complete 44 g pin–payload assemblies at ±60 mm. The activity examines model structure, configuration identity, mass distribution, joint declarations, actuation, and sensing. It does not compare the simulated trajectory with hardware measurements.

## Setup

From this folder, run:

```bash
uv sync
uv run pytest
```

## Inspect the five fixture configurations

```bash
uv run python simulation_only/demo.py
```

The command loads M0, B0, B1, B2, and G1 and writes `outputs/model_inspection.json`. For each configuration, the report records:

- generalized-coordinate, velocity, and actuator dimensions;
- the hinge axis and joint range;
- external moving mass;
- gravity bias at the declared inspection pose; and
- the number of collision-enabled geometries.

Open B0 in the MuJoCo viewer for 30 seconds:

```bash
uv run python simulation_only/demo.py --viewer B0 --viewer-seconds 30
```

Identify the fixed XC330 body, moving link subtree, revolute joint, rigid payload attachments, and positive joint axis.

## Examine mass distribution in simulation

```bash
uv run python simulation_only/activity.py \
  --model B0 --payload-scale 1.25 --torque-nm 0.05 --duration-s 0.10
```

The command applies the same short torque input to two simulated cases. The first uses the accepted 110 g B0 declaration. The second is a controlled hypothetical case in which the mass and inertia of both complete pin–payload assemblies are increased by 25%. Geometry, link properties, and applied torque remain unchanged.

Inspect `outputs/b0_inertia_response_activity.json`. Relate the change in modeled joint inertia to the change in initial angular acceleration. The hypothetical case is a sensitivity study, not another physical configuration or a hardware result.

## Questions to answer

1. Why do five manufactured parts not create five degrees of freedom?
2. Which MJCF body owns the hinge joint, and which bodies move as its descendants?
3. Why do B0 and B2 have equal external moving mass but different joint inertia?
4. Which declaration makes G1 mechanically different from the symmetric B-series configurations?
5. What is the difference between an XML document and an MJCF model?
6. Which properties are established by digitization, and which uncertain dynamic effects are deferred to Class 04?

## Troubleshooting

The structural report and mass-distribution activity do not require a graphical desktop. If a viewer cannot open, run `simulation_only/demo.py` without `--viewer`; the JSON report is still produced.
