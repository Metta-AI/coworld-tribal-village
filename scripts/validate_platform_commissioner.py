#!/usr/bin/env python3
"""Validate Tribal Village's platform commissioner deployment contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import ModuleType

from jsonschema import Draft202012Validator
from render_platform_settings import settings_for_team_count

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_metta_ladder_model(metta_root: Path):
    sys.path.insert(0, str(metta_root / "app_backend" / "src"))
    models = ModuleType("metta.app_backend.v2.ladders.models")
    models.DEFAULT_ELO_RATING = 1500.0
    sys.modules[models.__name__] = models
    from metta.app_backend.v2.ladders.config import LeagueLadderConfig

    return LeagueLadderConfig


def validate_settings(settings: dict, ladder_model) -> None:
    assert set(settings) == {"round_interval_minutes", "ladder"}
    assert 0 < settings["round_interval_minutes"] <= 40320
    ladder_model.model_validate(settings["ladder"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metta-root", required=True, type=Path)
    args = parser.parse_args()
    contract = load_json(REPO_ROOT / "platform_commissioner" / "contract.json")
    staged = load_json(REPO_ROOT / "platform_commissioner" / "settings.staged.json")
    active = load_json(REPO_ROOT / "platform_commissioner" / "settings.active.json")
    manifest = load_json(REPO_ROOT / contract["manifest_path"])

    ladder_model = load_metta_ladder_model(args.metta_root.resolve())
    validate_settings(staged, ladder_model)
    validate_settings(active, ladder_model)
    assert staged["ladder"]["enabled"] is False
    assert active["ladder"]["enabled"] is True
    staged_without_enabled = json.loads(json.dumps(staged))
    active_without_enabled = json.loads(json.dumps(active))
    del staged_without_enabled["ladder"]["enabled"]
    del active_without_enabled["ladder"]["enabled"]
    assert staged_without_enabled == active_without_enabled

    schema = load_json(
        args.metta_root
        / "packages"
        / "coworld"
        / "src"
        / "coworld"
        / "coworld_manifest_schema.json"
    )
    resolved_manifest = json.loads(json.dumps(manifest))
    resolved_manifest["game"].setdefault("version", "0.0.0")
    Draft202012Validator(schema).validate(resolved_manifest)
    topology = contract["topology"]
    assert topology["kind"] == "team_blocks"
    assert contract["supported_team_counts"] == list(range(2, 9))
    variants = {item["id"]: item for item in manifest["variants"]}
    for team_count in contract["supported_team_counts"]:
        variant_id = contract["variant_by_team_count"][str(team_count)]
        config = variants[variant_id]["game_config"]
        seats = len(config["players"])
        assert config["team_count"] == team_count
        assert seats == config["num_agents"] == team_count * topology["seats_per_team"]
        rendered = settings_for_team_count(team_count)
        validate_settings(rendered, ladder_model)
        rendered_scheduler = rendered["ladder"]["scheduler"]
        assert rendered_scheduler["team_count"] == team_count
        assert rendered_scheduler["variant_rotation"] == [variant_id]
    assert [item["division_id"] for item in active["ladder"]["divisions"]] == [
        contract["competition_division_id"]
    ]
    scheduler = active["ladder"]["scheduler"]
    assert scheduler["strategy"] == "team_n"
    active_team_count = scheduler["team_count"]
    assert active_team_count in contract["supported_team_counts"]
    assert scheduler["team_layout"] == "blocks"
    assert scheduler["min_episodes_per_entrant"] == 1
    active_variant_id = contract["variant_by_team_count"][str(active_team_count)]
    assert active_variant_id == contract["active_variant_id"]
    assert scheduler["variant_rotation"] == [active_variant_id]
    assert "qualification" not in active["ladder"]
    assert contract["admission"] == "direct_competition"
    print(
        f"validated {contract['league_id']} "
        f"({active_team_count}x{topology['seats_per_team']} active; 2-8 supported)"
    )


if __name__ == "__main__":
    main()
