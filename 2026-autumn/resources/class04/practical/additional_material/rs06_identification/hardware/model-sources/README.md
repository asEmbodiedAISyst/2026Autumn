# RS06 hardware-matched MJCF snapshots

This directory is the hardware-campaign copy of the frozen digital models in
`data/chapter-02/releases/rs06-sim-data-v1/model-sources/`.

The four MJCF files and every referenced STL mesh are byte-identical to that
release directory. Keeping the meshes here is necessary because each XML uses
a relative `meshes/...` path and should load as a self-contained model tree.

| Fixture | MJCF | Purpose |
|---|---|---|
| M0 | `M0.xml` | Motor-only configuration with no physical external load |
| B0 | `B0.xml` | Balanced link without the large end payloads |
| B1 | `B1.xml` | Balanced link with both large end payloads |
| G1 | `G1.xml` | One-sided payload for asymmetric/gravity evaluation |

`SHA256SUMS` records the frozen file hashes. Do not tune these hardware copies
independently. A model change requires a new declared model revision and a
corresponding update to both the release and hardware snapshot, followed by a
new hash audit.

Each XML carries the H1 actuator defaults (`kp=50`, `kv=3.38`). H2 is not a
different fixture model: the simulation pipeline applies the frozen H2
controller values (`kp=100`, `kv=1.95`) at runtime. Geometry and mass properties
therefore remain identical between H1 and H2.
