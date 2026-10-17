# Class 09 resources

The complete lecture, demonstration and student activity are on the [Class 09 page](../../module-03-arm-data-for-guided-interaction/09-teleoperation-by-streaming-from-asmagic.md). This folder preserves the supplied simulation bridge/model, two complete retained episodes and the arithmetic/audit helper. The Python interface is asmagic0.1.4; this is separate from the installed iOS app version. No hardware driver is included.

The retained circle and dropout are local fake-phone simulation captures, not physical robot or phone-camera data. Circle has170 rows; dropout has169. Each row has front/side RGB images of640×480 pixels. CSV actions and states use different sign/scale conventions. The bridge's receiver freshness diagnostic is not a packet-specific capture-to-actuation latency measurement. See the lesson for frame, timing and record-order interpretation.

The original runtime verification in evidence/verification.json combines checks from different runs. Its added retained_episode_audit identifies the distributed CSVs by hash and verifies their actual row/image counts and timing. Historical rerun counts do not replace those identities. Requirements and preserved code describe the tested software; source presence does not qualify an actual iPhone or hardware installation.

Model provenance and the CERN-OHL-W licence are retained in [the source notice](consolidation/package/additional_material/model/rebot_b601_rs_mjcf/NOTICE.md) and [licence](consolidation/package/additional_material/model/rebot_b601_rs_mjcf/LICENSE.CERN-OHL-W).
