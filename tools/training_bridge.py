"""Certified Tribal Village decisions over the shared Coworld JSONL bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from tribal_village_env.coworld.direct_env import (
    ACTION_SPACE_SIZE,
    CoworldTribalVillageEnv,
)

ROOT = Path(__file__).resolve().parents[1]
ACTION_NAMES = (
    "noop",
    "move",
    "attack",
    "use",
    "swap",
    "give",
    "plant lantern",
    "plant resource",
)
DIRECTIONS = (
    "north",
    "south",
    "east",
    "west",
    "northeast",
    "northwest",
    "southeast",
    "southwest",
)


def compact(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


class TrainingSession:
    def __init__(self, variant: str, mode: str, steps: int | None) -> None:
        manifest = json.loads((ROOT / "coworld_manifest_template.json").read_text())
        self.config = (
            manifest["certification"]["game_config"]
            if variant == "certification"
            else next(
                entry["game_config"]
                for entry in manifest["variants"]
                if entry["id"] == variant
            )
        )
        self.mode = mode
        self.max_steps = int(self.config["max_steps"]) if steps is None else steps
        if self.max_steps < 1:
            raise ValueError("Episode steps must be positive")
        self.env: CoworldTribalVillageEnv | None = None

    def reset(self, request: dict[str, object]) -> dict[str, object]:
        players = int(request["players"])
        if players != int(self.config["num_agents"]):
            raise ValueError(f"Variant requires {self.config['num_agents']} players")
        if self.env is not None:
            self.env.close()
        seed = (
            int.from_bytes(
                hashlib.sha256(str(request["seed"]).encode()).digest()[:4], "big"
            )
            or 1
        )
        self.env = CoworldTribalVillageEnv(
            max_steps=self.max_steps,
            config={"seed": seed, "team_count": int(self.config["team_count"])},
        )
        self.env.reset()
        self.env.reset_builtin_ai(seed)
        self.players = players
        self.seat = 0
        self.decision_id = 0
        self.actions: list[int] = []
        self.scores = [0.0] * players
        self.teacher_actions: list[int] | None = None
        return self.observation()

    def observation(self) -> dict[str, object]:
        assert self.env is not None
        if self.env.step_count >= self.max_steps or all(
            self.env.terminals[: self.players]
        ):
            scores = {seat: score for seat, score in enumerate(self.scores)}
            return {
                "kind": "terminal",
                "scores": scores,
                "utilities": {
                    seat: score / (1 + abs(score)) for seat, score in scores.items()
                },
            }
        tensor = self.env.player_observation(self.seat)
        visible = [
            [int(layer), int(x), int(y), int(tensor[layer, x, y])]
            for layer, x, y in zip(*tensor.nonzero(), strict=True)
        ]
        view = {
            "tick": self.env.step_count,
            "seat": self.seat,
            "team": self.seat // 6,
            "observation_shape": list(tensor.shape),
            "visible_cells": visible,
            "score": self.scores[self.seat],
        }
        messages = [
            {
                "role": "system",
                "content": "You control one Tribal Village agent. Reply with one JSON action id from 0 to 63. "
                "Action id = verb * 8 + direction; verbs: "
                + ", ".join(f"{i}={name}" for i, name in enumerate(ACTION_NAMES))
                + "; directions: "
                + ", ".join(f"{i}={name}" for i, name in enumerate(DIRECTIONS))
                + ". Visible cells are [layer,x,y,value] from your local 26x11x11 observation.",
            },
            {"role": "user", "content": compact(view)},
        ]
        return {
            "kind": "decision",
            "game": "tribal_village",
            "decision_id": self.decision_id,
            "seat": self.seat,
            "engine_seat": self.seat,
            "turn": self.env.step_count,
            "semantic_view": view,
            "inbox": [],
            "messages": messages,
            "speech_messages": [],
            "action_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": ACTION_SPACE_SIZE - 1,
                    }
                },
                "required": ["action"],
            },
            "typed_question": (
                {
                    "state": view,
                    "instructions": "Choose one action for this agent.",
                    "candidates": {
                        str(action): {
                            "decision": {"action": action},
                            "criterion": {
                                "verb": ACTION_NAMES[action // 8],
                                "direction": DIRECTIONS[action % 8],
                            },
                        }
                        for action in range(ACTION_SPACE_SIZE)
                    },
                }
                if self.mode == "choice"
                else None
            ),
        }

    def encode(self) -> dict[str, object]:
        assert self.env is not None
        if self.mode != "choice":
            raise ValueError("Numeric encoding requires choice mode")
        tensor = self.env.player_observation(self.seat)
        return {
            "decision_id": self.decision_id,
            "values": [int(value) / 255 for value in tensor.flat],
            "actions": [{"action": action} for action in range(ACTION_SPACE_SIZE)],
        }

    def teacher(self) -> dict[str, str]:
        assert self.env is not None
        if self.teacher_actions is None:
            self.teacher_actions = self.env.builtin_ai_actions()
        return {"response": compact({"action": self.teacher_actions[self.seat]})}

    def step(self, request: dict[str, object]) -> dict[str, object]:
        assert self.env is not None
        if request["decision_id"] != self.decision_id:
            return {"kind": "rejected", "reason": "stale decision"}
        response = json.loads(str(request["response"]))
        if not isinstance(response, dict) or type(response.get("action")) is not int:
            return {"kind": "rejected", "reason": "response needs an integer action"}
        action = response["action"]
        if not 0 <= action < ACTION_SPACE_SIZE:
            return {"kind": "rejected", "reason": "action outside 0..63"}
        self.actions.append(action)
        self.decision_id += 1
        self.seat += 1
        if self.seat == self.players:
            self.env.step(self.actions)
            self.scores = [
                score + float(reward)
                for score, reward in zip(self.scores, self.env.rewards, strict=False)
            ]
            self.actions = []
            self.teacher_actions = None
            self.seat = 0
        return {
            "kind": "accepted",
            "action": {"action": action},
            "observation": self.observation(),
        }

    def close(self) -> None:
        if self.env is not None:
            self.env.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="certification")
    parser.add_argument("--mode", choices=("choice", "text"), default="choice")
    parser.add_argument("--steps", type=int)
    args = parser.parse_args()
    session = TrainingSession(args.variant, args.mode, args.steps)
    try:
        for line in sys.stdin:
            request = json.loads(line)
            match request["kind"]:
                case "reset":
                    response = session.reset(request)
                case "encode":
                    response = session.encode()
                case "teacher":
                    response = session.teacher()
                case "step":
                    response = session.step(request)
                case _:
                    raise ValueError(f"Unknown training command {request['kind']}")
            print(compact(response), flush=True)
    finally:
        session.close()


if __name__ == "__main__":
    main()
