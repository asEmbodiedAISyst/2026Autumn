# Class 03 standalone — basic digitization of the XC330 fixture

Everything required for the Class 03 activity is contained in this folder: prepared fixture MJCFs and meshes, structural inspection tools, a simulation-only mass-distribution activity, and TA-only XC330 connection tools.

Start with the guide that matches your role:

- [Student guide](STUDENT_GUIDE.md) — structural MJCF inspection and simulation-only mass-distribution activity.
- [TA guide](TA_GUIDE.md) — XC330 ID/baud visualizer, guarded hardware procedure, and lesson flow.

## Quick start

```bash
uv sync
uv run pytest
```

Students normally run:

```bash
uv run python simulation_only/demo.py
uv run python simulation_only/activity.py --model B0 --payload-scale 1.25 --torque-nm 0.05 --duration-s 0.10
```

TAs can inspect or configure the connected XC330 through the desktop interface:

```bash
uv run python simulation_and_hardware/xc330_setup.py --visualizer
```

The setup screen is read-only until its explicit Apply action is confirmed. It never sends a motion command.
