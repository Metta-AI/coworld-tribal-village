from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from tribal_village_env.coworld.direct_env import CoworldTribalVillageEnv


class BuiltinAIPlayer:
    """Player-process wrapper for the existing Nim scripted AI.

    The Nim policy needs full engine state, so each packaged player keeps a
    deterministic local mirror of the episode and sends only its slot's action
    over the Coworld `/player` WebSocket.
    """

    def __init__(self, first_message: dict[str, Any]) -> None:
        game_config = first_message["game_config"]
        self.seed = int(game_config["seed"])
        self.env = CoworldTribalVillageEnv(
            max_steps=int(first_message["max_steps"]),
            config={"seed": self.seed},
        )
        self.env.reset()
        self.env.reset_builtin_ai(self.seed)

    def choose_action(self, message: dict[str, Any]) -> int:
        slot = int(message.get("slot", 0))
        tick = int(message.get("tick", 0))
        while self.env.step_count < tick:
            self.env.step(self.env.builtin_ai_actions())

        actions = self.env.builtin_ai_actions()
        action = actions[slot] if 0 <= slot < len(actions) else 0
        self.env.step(actions)
        return action

    def close(self) -> None:
        self.env.close()


async def run_player() -> None:
    url = os.environ.get("COWORLD_PLAYER_WS_URL")
    if not url:
        raise RuntimeError("COWORLD_PLAYER_WS_URL is required")

    player: BuiltinAIPlayer | None = None
    try:
        async with websockets.connect(url, max_size=None) as websocket:
            async for raw_message in websocket:
                message = json.loads(raw_message)
                if message.get("done") or message.get("type") == "final":
                    return
                if message.get("type") != "observation":
                    continue
                if player is None:
                    player = BuiltinAIPlayer(message)
                await websocket.send(
                    json.dumps(
                        {"type": "action", "action": player.choose_action(message)}
                    )
                )
    except ConnectionClosed as exc:
        close_code = getattr(getattr(exc, "rcvd", None), "code", None)
        if close_code in {1000, 1001, 1012}:
            return
        raise
    finally:
        if player is not None:
            player.close()


if __name__ == "__main__":
    asyncio.run(run_player())
