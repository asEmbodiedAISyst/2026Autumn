# Class 10 resources — audit demonstration data

The [complete lesson](../../module-03-arm-data-for-guided-interaction/10-collect-data-for-reinforcement-learning.md) explains this simulated handheld pusher pilot, the audit and the student activity. Ten episodes contain 638 retained frames at nominal 30 Hz. The original Parquet/video and exact CSV/JSON exports are retained; no interpolation or synthetic rows were added during export. Images are tool-camera simulation views, not physical iPhone captures.

The nine-value features are episode-relative position in metres and two orientation columns. The 628 available within-episode action/next-state pairs match exactly. Last-row actions have no following saved state; do not join them to another episode. Nominal dataset timestamps do not provide measured source-acquisition latency.

The numeric audit keeps geometry, speed, visibility and executability separate. Episode 4's last recorded distance is 32.03 mm; episode 6's implied action-pose speed is about 0.60 m/s. The source fault-reference distance 23.9 mm for episode 4 is a separately defined source record. The canonical IK report is conditional on the retained model/frame/solver and its small-error orientation metric. It does not certify physical reachability, contact, visibility or hardware operation.

The recorded-policy folder preserves a separate seven-channel gripper ACT result: 24/50 simulation success flags, plus two selected clips and the source training recipe. These are not results for the nine-feature pilot. Weights, processors and matching executor configuration are absent; exact policy inference is not supplied.

See [source identity](SOURCE.json), [model notice](model/rebot_b601_rs_mjcf/NOTICE.md), [licence](model/rebot_b601_rs_mjcf/LICENSE.CERN-OHL-W), [numeric result](saved/numeric-audit.json) and [canonical result](saved/canonical-ik.json). Requirements describe the tested optional IK dependencies. Existing paths, code, models, source results and media remain available; this manuscript review does not migrate them to a new package layout.
