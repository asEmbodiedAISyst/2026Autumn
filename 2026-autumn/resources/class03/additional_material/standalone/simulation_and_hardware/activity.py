#!/usr/bin/env python3
"""Print the inspection worksheet for one physical/model configuration."""

from __future__ import annotations

import argparse
import json

from demo import EXPECTED, model_external_mass_g


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=tuple(EXPECTED), default="B2")
    args = parser.parse_args()
    record = EXPECTED[args.model]
    result = {
        "configuration": args.model,
        "recorded_external_mass_g": record["external_mass_g"],
        "recorded_payload_centres_mm": record["positions_mm"],
        "model_external_mass_g": model_external_mass_g(args.model),
        "inspection_prompts": [
            "Identify the fixed body, moving link, joint axis and joint limits.",
            "Which values are physical measurements and which are model declarations?",
            "Name one geometric check and one behavioral validation still required.",
        ],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
