# Class 03 standalone — basic digitization and the Sim2Real gap

Everything required to run this class is contained in this folder: prepared fixture MJCFs and meshes, an embedded V5 B0 physical record, the simulation workflow, and the TA-only XC330 hardware tools.

Start with the guide that matches your role:

- [Student guide](STUDENT_GUIDE.md) — simulation-only B0 replay and pre-identification gap.
- [TA guide](TA_GUIDE.md) — XC330 ID/baud visualizer, guarded hardware collection, and lesson flow.

## Quick start

```bash
uv sync
uv run pytest
```

Students normally run:

```bash
uv run python simulation_only/b0_data_collection.py
```

TAs can inspect or configure the connected XC330 through the desktop interface:

```bash
uv run python simulation_and_hardware/xc330_setup.py --visualizer
```

The setup screen is read-only until its explicit Apply action is confirmed. It never sends a motion command.
