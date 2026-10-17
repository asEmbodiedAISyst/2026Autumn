# Native MuJoCo identification and replay

This optional CPU-only package supports [Class 04](../../../module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md). No actuator or graphics viewer is required. Once dependencies are available, replay and fitting use local inputs. Analysing the supplied saved outputs receives equal student activity credit.

The XC330 example is the 98 g campaign: a 6 g link plus two assemblies of 4 g pin and 42 g payload. The separate 110 g inspection model is not used. RS06 remains a distinct controller/measurement example with its own metadata.

## Prepared environment and commands

Use Python 3.12 with [the five pinned dependencies](requirements.txt): NumPy, Matplotlib, MuJoCo, SciPy and PyArrow. PyArrow is imported by the unchanged upstream XC330 engine even though this wrapper loads NPZ arrays. Prepare the environment before class. No virtual environment or downloaded packages are included.

Prepare an isolated environment before class. From the repository root:

```bash
cd 2026-autumn/resources/class04/native
python3.12 -m venv .venv-native
. .venv-native/bin/activate
python -m pip install -r requirements.txt
```

Windows: use `py -3.12 -m venv .venv-native`, then `.venv-native\Scripts\python.exe -m pip install -r requirements.txt`; substitute that executable for `python`. POSIX `export` commands below only configure the local cache and bytecode output. PowerShell equivalents are `$env:MPLCONFIGDIR="$PWD/.mpl-cache"` and `$env:PYTHONDONTWRITEBYTECODE="1"`.

For the prepared environment, the complete command path from the repository root is:

```bash
cd 2026-autumn/resources/class04/native
export MPLCONFIGDIR="$PWD/.mpl-cache"
export PYTHONDONTWRITEBYTECODE=1
python code/phyintel_lab.py audit --actuator xc330
python code/phyintel_lab.py inspect --actuator xc330
python code/phyintel_lab.py replay --actuator xc330
python code/phyintel_lab.py fit-integral --actuator xc330 --controller H1
```

`audit` verifies source-engine and exported-data hashes, episode identities, time order and finite positions. `inspect` constructs the native models. `replay` freshly simulates frozen M1 and M2 candidates for the first P06 held-out repeats under B1/G1 and H1/H2. `fit-integral` estimates the three parameters from H1 calibration records, freezes the estimate and scores H1 episodes by role. Outputs go to `results/phyintel/`; published inputs in `data/phyintel/*/published/` remain unchanged.

Optional instructor preparation:

```bash
python code/phyintel_lab.py audit --actuator rs06
python code/phyintel_lab.py inspect --actuator rs06
python code/phyintel_lab.py replay --actuator rs06
python code/phyintel_lab.py evaluate --actuator xc330
python code/phyintel_lab.py fit-output-error --actuator xc330 --controller H1
```

`evaluate` scores all primary episodes and replaces the replay output with full-episode traces. Output-error optimization uses multiple starts and is longer preparation work. The supplied M2 replay uses released output-error parameters; replaying them is not a fresh optimizer run. For `audit`, `inspect` or `replay`, `--actuator both` selects both campaigns.

## Evidence and boundaries

| Location | Contents |
|---|---|
| `code/phyintel_lab.py` | Exact course wrapper; resolves paths relative to this package |
| `code/upstream/` | Exact upstream identification/replay engines |
| `data/phyintel/xc330/` | 126 processed episodes, fixture/controller properties and source published results |
| `data/phyintel/rs06/` | 108 processed episodes, model sources, fixture metadata and source results |
| `data/phyintel/simulation-reference/` | Separate constructed known-answer summaries with C1/C2 controllers; these are not XC330 validation evidence |
| `results/phyintel/` | Supplied audit/inspection, XC330 representative replay and H1 integral-fit outputs; commands can regenerate them |
| `source-manifest.json` | SHA-256 values and course-relative source identities for the immutable files |

The NPZ inputs are lossless exports of adapter output, not raw telemetry. XC330 retains the source active-profile cropping and 10 ms interpolation. This package does not recollect hardware data or repeat raw-archive parsing. Archive identities and hashes remain in campaign `provenance.json` files. Read the nested published READMEs as upstream result documentation: their raw-archive reproduction commands refer to the upstream project. Use the commands above for this package.

XC330 replay receives recorded internal position and velocity references and computes feedback from its evolving simulated state. Firmware external-goal-to-reference generation lies outside the prediction boundary. The fixed Mode-5 controller engineering map and current-derived ±0.1551 N m effort limit are modelling assumptions, not independently measured shaft torque. H1 and H2 have separately estimated effective joint parameters. RS06 uses its own controller boundary.

Source verification used Python 3.12.14 and MuJoCo 3.3.7. The four representative XC330 episodes, each replayed with two candidates, reproduced released position RMSEs exactly in that environment. The H1 integral-fit parameters and split means also reproduced the saved source result. Report numerical differences on another platform rather than changing the frozen reference values. The [compact activity guide](../data/README.md) defines the exact selected-case scoring contract.

The [recorded verification summary](results/verification/summary.json) preserves the numeric checks for the supplied package. These checks concern implementation reproducibility, not independent hardware calibration.
