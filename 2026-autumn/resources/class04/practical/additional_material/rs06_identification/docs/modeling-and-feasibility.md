# M0 model and fixture feasibility

## What M0 is in the model

M0 does not remove the joint, and it does not weld the motor output to the world. The model keeps two levels:

```text
world
└── fixed motor and bench body
    └── output moving body
        └── hinge joint
```

A MuJoCo hinge must belong to a child body that can move. Thus the "no load" configuration still has an output
body. The model gives this body a mass of `1e-6 kg` and a diagonal inertia of `1e-12 kg m^2`, so that the model is
valid numerically. The mesh of the body is display only (`density=0`, `contype=0`, `conaffinity=0`): it adds no
mass and no collision.

The RS06 models use the same rule:

- `base_link` is the fixed body;
- `playload-1` is the child body of `rs06_joint`;
- the `playload-1` mesh is display only;
- the equivalent inertia of the motor and the gear is the joint `armature`, not a value computed from the mesh.

In Fusion 360 it is sufficient to model one motor with its output flange or adapter, as two components and one
revolute joint: the fixed component is `base_link`, the moving component is the flange or adapter. Do not add a
fictitious counterweight to the moving component for M0. When Fusion cannot export a moving body with zero mass,
export it as it is, then make the body display only in the MJCF and add the numerical regulariser, as above.

## Inertia about the joint axis

The inertia about the joint axis is not the first number of `fullinertia`. It is computed along the joint axis with
the parallel-axis theorem:

```text
J_axis = aᵀ I_com a + m (||r||² − (a·r)²)
```

where `a` is the unit joint axis, `I_com` the inertia tensor at the centre of mass, `m` the moving mass and `r` the
vector from the joint to the centre of mass. The values of the four fixtures are in
`hardware/README.md` (table "Hardware configuration family") and in
`data/chapter-02/releases/rs06-sim-data-v1/fixture-contract.json`.

B0 and B1 have a residual gravity torque of about `0.000359 N m` at the export zero pose: they are balanced for
engineering purposes. G1 has about `1.266 N m`, which is not a small offset. The signed first moment in the tables
has the geometric sign of the export frame; the MuJoCo `qfrc_bias` at the zero pose has the opposite sign. The
travel, the release direction and the emergency-stop limits of the physical G1 need a separate review.

## Are four fixtures sufficient

M0, B0, B1 and G1 are sufficient for the adapted task:

- M0 gives a path close to the bare motor and a low external-inertia condition;
- B0 and B1 give two balanced axial inertias that differ by a factor of about 4.47. This makes the armature, the
  damping and the dry friction more identifiable;
- G1 gives an asymmetric gravity transfer check that is used only in the held-out split;
- the three-parameter Method 2 pipeline of the Sim-Position and the Sim-Torque data ran on the data of this
  package.

The missing B2 sets clear limits:

- the package reproduces the adapted 32 episodes, not the 38 episodes of the original matrix;
- there is no third, higher balanced inertia for model selection and for extrapolation to high loads. B1 is used
  in the calibration, in the model selection and in one held-out profile, so the mechanical conditions are less
  independent than in the original design;
- the effect of the payload radius cannot be tested on its own, because the assemblies change only between no
  load and two-sided load, not the distance at a constant mass;
- results must not be extrapolated to inertias above B1, to other lever arms, or to flexibility, backlash and
  mounting resonance;
- G1 free-fall data is supporting data; it does not replace the closed-loop G1/P06 and G1/P07 episodes.

If a B2 is built later, the most useful B2 is a balanced inertia higher than B1 with a measured mechanical
stiffness, which restores the calibration and model-selection role of B2 in the original matrix.

## Controller names

The simulation uses C1 and C2; the hardware uses H1 and H2. The pairs C1-H1 and C2-H2 have the same numbers, but
the pairing is a frozen hypothesis of the simulation. The KP and KD of the RS06 protocol do not have the physical
meaning of `N m/rad` and `N m s/rad` by default. A hardware result must keep the complete controller and
firmware context. Do not copy the hardware values into MuJoCo as SI gains and then report the identification as
complete.
