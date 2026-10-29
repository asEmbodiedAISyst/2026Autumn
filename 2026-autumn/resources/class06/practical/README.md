# Class 06: Continuous positive-Z cube rotation

[Lecture](../../../module-02-hand-data-for-multi-fingered-manipulation/06-learned-in-hand-cube-reorientation.md)

## Available material

The [Class 06 practice](../../../module-02-hand-data-for-multi-fingered-manipulation/06-practice.md) uses the downloadable [continuous-yaw standalone package](downloads/class06-continuous-yaw-standalone.zip). It contains a visible native-MuJoCo policy run, complete model assets, checkpoint and exported weights, guarded optional hardware bridge, tests, and the original MJLab task/training source. Existing records, videos and extracted frames remain available beside it.

## Evidence and execution boundary

The default Linux/macOS viewer smoothly replays the exact stable 30-second full-MJLab seed-11 trajectory supplied by the deployment bundle. The package also retains a lightweight live native approximation, the original preview MP4, and the complete accelerated Python 3.10 MJLab/MuJoCo-Warp training and recording route for a fresh compatible Linux run. Powered right-LEAP-Hand execution is optional, TA-supervised and requires station-specific serial configuration, a physical cutoff and a successful shadow pass.

## Source and file identity

Retained runtime code, numerical data and model files derive from the teaching authors' continuous-Z deployment and original MJLab project. The task identity is `Mjlab-Leap-Right-HandCube-MBZUAI-Rotate`; it is continuous positive-Z/yaw rotation, not arbitrary orientation-goal reorientation. The portable scene changes only asset paths and the declared initial cube placement needed to make the package independent of the author's workstation.

The package includes both `model_400.pt` and its lightweight NumPy actor export. Existing physical records remain evidence from their source trials and are not converted into a new autonomous-success claim by packaging the runnable simulation.

Use an isolated virtual environment as directed by the practice/package requirements. Installing dependencies or running a recipe is a separate step from reproducing a result; this distribution update does not report new training or powered-hardware tests.
