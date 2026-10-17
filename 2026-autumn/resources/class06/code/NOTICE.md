# Attribution and changes

Playground snapshot: Google DeepMind, Apache-2.0; see PLAYGROUND-LICENSE and provenance.json.
Menagerie LEAP assets: exact commit selected by Playground; see models/MENAGERIE-LICENSE.

reference/ and models/xmls/ are unmodified upstream copies. native_task.py is a
course-developed compatibility layer: it hash-verifies and executes selected
upstream method bodies, replacing construction and physics/data APIs. Native
MuJoCo physics uses CPU JAX task math and random numbers. The included audit_policy_contract.py and validate_lettered.py exercise
these adaptations. Upstream Warp training uses the pinned checkout directly.
The course does not claim to have trained the supplied policy or of identical cross-backend dynamics.

The six course cube-face PNG textures use MiSans Fonts. They are generated artwork; no font software is redistributed in this student package. Figure reproduction requires locally licensed MiSans Regular/Semibold. Source and font requirements are documented in the class media folder; official font licence: https://hyperos.mi.com/font/en/download/.
