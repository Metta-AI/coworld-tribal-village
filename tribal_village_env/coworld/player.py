from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import websockets


def choose_action(message: dict[str, Any]) -> int:
    """Small deterministic baseline for one Tribal Village agent slot."""
    slot = int(message.get("slot", 0))
    tick = int(message.get("tick", 0))
    phase = tick % 12
    direction = (slot + tick) % 8
    if phase < 7:
        return 1 * 8 + direction  # move
    if phase == 7:
        return 3 * 8 + direction  # use/craft/gather
    if phase == 8:
        return 2 * 8 + direction  # attack
    if phase == 9:
        return 6 * 8 + direction  # plant lantern
    return 0


async def run_player() -> None:
    url = os.environ.get("COWORLD_PLAYER_WS_URL") or os.environ.get(
        "COGAMES_ENGINE_WS_URL"
    )
    if not url:
        raise RuntimeError("COWORLD_PLAYER_WS_URL is required")

    async with websockets.connect(url, max_size=None) as websocket:
        async for raw_message in websocket:
            message = json.loads(raw_message)
            if message.get("done"):
                return
            if message.get("type") not in {"observation", "final"}:
                continue
            await websocket.send(
                json.dumps({"type": "action", "action": choose_action(message)})
            )


if __name__ == "__main__":
    asyncio.run(run_player())
