"""Check and summarize the supplied simulation files using only Python's standard library."""
from pathlib import Path
import argparse
import csv
import json
import math
import statistics

ROOT = Path(__file__).resolve().parents[1]


def summarize(root):
    report = json.loads((root / 'results/inspection.json').read_text())
    with (root / 'results/joint2-trace.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        expected = ['time_s', 'target_deg', 'pre_step_position_deg']
        if reader.fieldnames != expected:
            raise ValueError('Unexpected CSV columns or order')
        rows = [[float(row[key]) for key in expected] for row in reader]
    if len(rows) < 2 or not all(math.isfinite(x) for row in rows for x in row):
        raise ValueError('Trace needs at least two finite rows')
    periods = [b[0] - a[0] for a, b in zip(rows, rows[1:])]
    if min(periods) <= 0:
        raise ValueError('Simulation timestamps must strictly increase')
    period = float(report['control_period_s'])
    if not math.isclose(report['substeps'] * report['physics_timestep_s'], period, abs_tol=1e-12):
        raise ValueError('Inspection timing fields disagree')
    if not all(math.isclose(dt, period, abs_tol=1e-10) for dt in periods):
        raise ValueError('Trace sampling does not match the inspected control period')
    residuals = [row[2] - row[1] for row in rows]
    return {
        'scope': 'supplied simulation data; target and state paired before each step',
        'dimensions': {key: report[key] for key in ['nq', 'nv', 'nu']},
        'frames': len(rows),
        'first_time_s': rows[0][0],
        'last_time_s': rows[-1][0],
        'mean_sample_period_s': statistics.mean(periods),
        'max_abs_pre_step_tracking_error_deg': max(map(abs, residuals)),
        'rmse_pre_step_tracking_error_deg': math.sqrt(statistics.mean(x*x for x in residuals)),
        'residual_definition': 'pre_step_position_deg - target_deg',
        'home_tcp_m': report['home_tcp_m'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='resource folder containing results/')
    args = parser.parse_args()
    print(json.dumps(summarize(args.root), indent=2))


if __name__ == '__main__':
    main()
