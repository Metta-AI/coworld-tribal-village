#!/usr/bin/env python3
"""Render the complete Tribal Village ladder settings for an active team count."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def settings_for_team_count(team_count: int) -> dict:
    contract = json.loads(
        (ROOT / "platform_commissioner" / "contract.json").read_text()
    )
    if team_count not in contract["supported_team_counts"]:
        raise ValueError("team count must be between 2 and 8")
    settings = json.loads(
        (ROOT / "platform_commissioner" / "settings.active.json").read_text()
    )
    rendered = copy.deepcopy(settings)
    scheduler = rendered["ladder"]["scheduler"]
    scheduler["team_count"] = team_count
    scheduler["variant_rotation"] = [contract["variant_by_team_count"][str(team_count)]]
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("team_count", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(settings_for_team_count(args.team_count), indent=2) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered)


if __name__ == "__main__":
    main()
