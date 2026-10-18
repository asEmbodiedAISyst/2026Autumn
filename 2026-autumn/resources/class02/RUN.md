# Class 02 demonstration and optional code

The required class demonstration follows the class outline and teaching-team demonstration. It traces application → asBrain/interface → actuator → telemetry using a qualified station or the named recorded fallback. The student activity is unpowered inspection and a document comparison; code execution is optional.

This package contains offline analysis, not a live asBrain or hardware-control driver. Keep the station's actual interface and qualification procedure separate from the saved-data script. During class, use the prepared figures, configuration and saved samples rather than installing packages or running a full campaign.

# Run Class 02

## Optional recorded-data inspection

Use Python 3.10–3.12. Create an isolated environment in this class folder; existing global installations and other projects need no changes.

```bash
python3 -m venv .venv
source .venv/bin/activate
python code/hardware_demo.py audit
python code/hardware_demo.py inspect --row 400
```

Windows PowerShell: activate with `.venv\Scripts\Activate.ps1`. The two optional commands require only the Python standard library and packaged CSV/JSON; no network, package installation, display, simulator or hardware connection is used. Installers and browser setup are preparation, outside the planned class time.

Expected: 2,601 telemetry rows, 1,301 commands, ID 5, firmware 53, Mode 5, H2 P/I/D 800/0/150, and unchanged critical before/after readback. Conversions agree with all original source engineering columns. Row 400 position is 26.279296875 degrees (0.4586602556 rad), velocity is −4.351 r/min (−0.4556356545 rad/s), and voltage is 5.1 V. Results are written to `results/hardware-demo/`; saved copies are supplied as fallback. The [data README](data/xc330-hardware-demo/README.md) explains identity and clock boundaries.

## Measured-record explorer

Open `interactive/hardware-telemetry.html` in a browser. It contains the supplied record and uses locally installed MiSans with a system-font fallback. It makes no external network or hardware calls. Set row 400, choose raw or engineering units, and select a channel. If the local viewer restricts file opening, run:

```bash
python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/media/interactive/hardware-telemetry.html`, then stop this local server with Ctrl+C. Download the resource folder before opening HTML; a GitHub file preview shows its source. Use the browser/localhost route for interaction, and the static figures and sample table for reading the lesson. Interactive execution inside GitBook or a Markdown viewer is not required.

# Optional campaign and model experiments

Use Python 3.10–3.12. Verification uses Python 3.12 and MuJoCo 3.3.7. Run from this class folder or the extracted standalone package. The optional replay path runs on CPU without hardware or a display.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python code/phyintel_lab.py audit
python code/phyintel_lab.py inspect
python code/phyintel_lab.py replay
```

Windows PowerShell: activate with `.venv\Scripts\Activate.ps1`. Install only inside the virtual environment. The first dependency installation needs internet; the actual experiments use packaged local data. The optional replay selects first recorded P06 held-out B1/G1 repeats under H1/H2 for each actuator, applies both frozen source candidates, and compares per-episode RMSE with source values. It is an actual native MuJoCo calculation, not a saved video or precomputed plot.

## Additional experiments

```bash
# All 126 XC330 and 108 RS06 primary episodes, both frozen candidates:
python code/phyintel_lab.py evaluate --actuator both
# Fresh integral regression, calibration only:
python code/phyintel_lab.py fit-integral --actuator xc330 --controller H1
python code/phyintel_lab.py fit-integral --actuator rs06 --controller H1
# Optional longer, multiple-start output-error fit:
python code/phyintel_lab.py fit-output-error --actuator xc330 --controller H1
python code/phyintel_lab.py fit-output-error --actuator rs06 --controller H1
```

`--controller H2` selects the second context. `--actuator xc330`, `rs06` or `both` selects campaigns. Fitting does not overwrite frozen published parameters. After calibration, each fresh fit is automatically frozen and evaluated on the other episode roles; its JSON contains per-episode gaps and equal-episode split means. Repeat evaluation is deterministic but small numerical differences can occur across platforms. Read the exact published-score discrepancy in `results/phyintel/*-replay.json`.

Outputs are resolved relative to the script location: `results/phyintel/*-audit.json`, `*-models.json`, `*-replay.json`, `*-replay.npz` and separate `*-fit-*.json`; figures go to `media/`. Repeating a command replaces that command's generated outputs, not `data/phyintel/*/published`. `evaluate` replaces the representative replay outputs with full-episode outputs; subsequent figures deliberately select H1/B1 and H1/G1/P06 first repeats from that output.

The earlier Mode-3 examples remain runnable with `python code/course_lab.py all`. These use the earlier CSVs, geometry and two-parameter command correction. They are separate from the campaign identification.

Optional older visual examples: on macOS use `mjpython code/view.py --model weighted --seconds 10` or `--model pendulum`; on Linux/Windows use `python`. Those viewer waveforms are illustrations, not campaign validation. No viewer is required for scoring. For a local Matplotlib cache set `MPLCONFIGDIR` to a writable folder, for example `export MPLCONFIGDIR="$PWD/.mpl-cache"`.

## Visual mechanism examples

Open `interactive/actuator-explorer.html` in a browser. It runs offline from the extracted class package and uses locally installed MiSans or the optional local font files; keep the package folders together. If local file opening is restricted, run `python -m http.server 8765 --bind 127.0.0.1` from the class folder and open `http://127.0.0.1:8765/media/interactive/actuator-explorer.html`. Stop this local server with Ctrl+C. No package installation or hardware connection is required. HTML execution inside asMagicBrain Preview/Present is not assumed; the supplied static equivalents remain the teaching fallback.
