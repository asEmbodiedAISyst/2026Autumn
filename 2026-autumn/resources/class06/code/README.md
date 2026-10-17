# Class 06 native playback sources

[Course page](../../../module-02-hand-data-for-multi-fingered-manipulation/06-learned-in-hand-cube-reorientation.md) · [Resource inventory](../README.md) · [GPU reference procedure](REFERENCE-EVALUATION.md)

Models, the supplied ONNX actor, pinned task sources, licences and retained evaluations are bundled here. `native_task.py` runs the pinned task arithmetic with native MuJoCo physics; it preserves the task's observation/history ordering. `lettered_cube.py` changes only the cube's display artwork. The supplied upstream player's callback remains a separate reference, with interface differences recorded in `results/policy-contract-audit.json`.

The recorded native runtime uses Python 3.12 and the pinned `requirements-demo.txt`. Reading the lesson and supplied results does not require installation. Environment setup, working directories and execution instructions belong to the separately prepared example package. This review does not change simulation logic, models, weights or prior results.
