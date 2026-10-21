"""Write a deterministic native episode's public snapshot and action replay.

Run from the repository root with ``python -m tools.observer_episode OUTPUT``.
The output directory must not exist. No player observations are written.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tribal_village_env.coworld.observer import ObserverSnapshot
from tribal_village_env.coworld.server import CoworldConfig, TribalVillageCoworld


def capture(output: Path, *, seed: int, teams: int, ticks: int) -> None:
    config = CoworldConfig.from_dict(
        {
            "team_count": teams,
            "num_agents": teams * 6,
            "seed": seed,
            "max_steps": ticks,
            "players": [{"name": f"Player {i}"} for i in range(teams * 6)],
            "tokens": [f"offline-{i}" for i in range(teams * 6)],
        }
    )
    output.mkdir(parents=True, exist_ok=False)
    runtime = TribalVillageCoworld(config=config, results_uri="", replay_uri="")
    try:
        runtime.env.reset_builtin_ai(seed)
        for _ in range(ticks):
            runtime._step(runtime.env.builtin_ai_actions()[: config.player_count])
        runtime.truncation_reason = "max_steps"
        snapshot = ObserverSnapshot.from_sprite_frame(
            runtime.env.step_count, *runtime.env.sprite_frame()
        )
        (output / "observer.json").write_text(json.dumps(snapshot.payload()) + "\n")
        (output / "replay.json").write_text(
            json.dumps(runtime.replay_payload(runtime.results()), sort_keys=True) + "\n"
        )
    finally:
        runtime.env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--teams", type=int, choices=range(2, 9), default=8)
    parser.add_argument("--ticks", type=int, default=64)
    args = parser.parse_args()
    if args.ticks < 1 or args.seed < 1:
        parser.error("ticks and seed must be positive")
    capture(args.output, seed=args.seed, teams=args.teams, ticks=args.ticks)
