# RS06 fixture metadata sidecars

`M0.json`, `B0.json`, `B1.json`, and `G1.json` bind each declared hardware
fixture ID to the supplied Fusion/MJCF revision, source meshes, hashes, and the
CAD-derived mass properties used by the RS06 Chapter 2 model.

The values are reproducible from:

```bash
.venv/bin/python \
  course_resources/chapter02-rs06-data/scripts/build_chapter02_rs06_fixture_metadata.py
```

`manifest.json` binds every captured dynamic and static-gravity run to one of
the four sidecars using the run's declared fixture ID and records hashes of the
raw session, package contract, verification, and sidecar. Captured evidence is
not modified.

The inertia field is the **external moving fixture inertia about
`rs06_joint`**. It excludes motor rotor/output inertia and excludes the MuJoCo
joint `armature`, so those terms must not be added twice during identification.

These files deliberately distinguish known CAD evidence from missing physical
provenance. `assembly_revision`, `mounting_revision`, motor serial, as-built
uncertainty, physical hard stops, physical photographs, and fastener checks
remain null until the operator supplies them. Configured software limits and
CAD values are not presented as independent as-built measurements.

`evidence/photos/M0.jpg`, `B0.jpg`, `B1.jpg`, and `G1.jpg` are inspected CAD
assembly renders. The builder records their relative paths and SHA-256 hashes as
design-intent evidence with `as_built_photograph: false`. Physical fixture,
mounting, zero-mark, and nameplate photographs are still required for an
as-built evidence claim.
