from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

from tribal_village_env.coworld.direct_env import CoworldTribalVillageEnv
from tribal_village_env.coworld.player import BuiltinAIPlayer


ROOT = Path(__file__).resolve().parents[1]
PLAYER_COUNT = 48
SPRITE_FRAME_KIND = "tribal-village-sprite-cells-v2"
DELAYED_FIRST_ACTION_SLOT = 47
DELAYED_FIRST_ACTION = 11
CELL_OFFSET_FLAGS = 22
CELL_OFFSET_ACTION_R = 23
CELL_OFFSET_ACTION_G = 24
CELL_OFFSET_ACTION_B = 25
ACTION_TINT_FLAG = 4


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(port: int, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited early: {process.returncode}")
        try:
            with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.2)
    raise TimeoutError("timed out waiting for Coworld healthz")


async def assert_websocket_rejected(url: str, failure_message: str) -> None:
    rejected = False
    try:
        async with websockets.connect(
            url,
            open_timeout=5,
            max_size=None,
        ) as websocket:
            try:
                await asyncio.wait_for(websocket.recv(), timeout=2)
            except ConnectionClosed:
                rejected = True
    except InvalidStatus as exc:
        rejected = exc.response.status_code in {401, 403}
    if not rejected:
        raise AssertionError(failure_message)


async def assert_live_websockets(port: int) -> None:
    async with websockets.connect(
        f"ws://127.0.0.1:{port}/global",
        open_timeout=5,
        max_size=None,
    ) as global_ws:
        message, cell_bytes = await recv_world_frame(global_ws)
        assert message["type"] == "state"
        assert message["frame"]["kind"] == SPRITE_FRAME_KIND
        assert message["frame"]["encoding"] == "uint8-arraybuffer"
        assert len(cell_bytes) == (
            message["frame"]["width"]
            * message["frame"]["height"]
            * message["frame"]["stride"]
        )
        assert len(message["agents"]) == PLAYER_COUNT
        assert message["agents"][0]["slot"] == 0
        assert message["agents"][0]["name"] == "Agent 0"

        player_websockets = []
        try:
            for slot in range(PLAYER_COUNT):
                player_websockets.append(
                    await websockets.connect(
                        f"ws://127.0.0.1:{port}/player?slot={slot}&token=token-{slot}",
                        open_timeout=5,
                        max_size=None,
                    )
                )

            for slot, player_ws in enumerate(player_websockets):
                message = json.loads(
                    await asyncio.wait_for(player_ws.recv(), timeout=10)
                )
                assert message["type"] == "observation"
                assert message["slot"] == slot
                assert message["action_space"]["n"] == 64
                assert message["game_config"]["seed"] == 1
                assert "view" not in message
                assert "frame" not in message

            for slot, player_ws in enumerate(player_websockets):
                if slot != DELAYED_FIRST_ACTION_SLOT:
                    await player_ws.send(json.dumps({"type": "action", "action": 8}))

            await asyncio.sleep(0.2)
            await player_websockets[DELAYED_FIRST_ACTION_SLOT].send(
                json.dumps({"type": "action", "action": DELAYED_FIRST_ACTION})
            )
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and message["tick"] == 0:
                message, _ = await recv_world_frame(global_ws)
            assert message["tick"] > 0
        finally:
            for player_ws in player_websockets:
                await player_ws.close()


async def assert_replay_autoplays_and_loops(port: int) -> None:
    async with websockets.connect(
        f"ws://127.0.0.1:{port}/replay?speed=8",
        open_timeout=5,
        max_size=None,
    ) as replay_ws:
        seen_done = False
        seen_loop = False
        seek_sent = False
        seen_seek_reset = False
        for _ in range(18):
            message, cell_bytes = await recv_world_frame(replay_ws)
            if message["tick"] == 1:
                await replay_ws.send(json.dumps({"type": "speed", "speed": 4}))
            if message["tick"] >= 2 and not seek_sent:
                await replay_ws.send(json.dumps({"type": "seek", "tick": 0}))
                seek_sent = True
            elif seek_sent and message["tick"] == 0:
                seen_seek_reset = True
            assert message["type"] == "replay"
            assert message["started"] is True
            assert message["frame"]["kind"] == SPRITE_FRAME_KIND
            assert message["frame"]["encoding"] == "uint8-arraybuffer"
            assert len(cell_bytes) == (
                message["frame"]["width"]
                * message["frame"]["height"]
                * message["frame"]["stride"]
            )
            assert len(message["agents"]) == PLAYER_COUNT
            assert message["agents"][0]["slot"] == 0
            assert message["agents"][0]["name"] == "Agent 0"
            if message["done"]:
                seen_done = True
            elif seen_done and message["tick"] == 0:
                seen_loop = True
                break
        assert seen_seek_reset
        assert seen_done
        assert seen_loop


async def recv_world_frame(websocket: Any) -> tuple[dict[str, Any], bytes]:
    raw_message = await asyncio.wait_for(websocket.recv(), timeout=10)
    assert isinstance(raw_message, str)
    message = json.loads(raw_message)
    raw_cells = await asyncio.wait_for(websocket.recv(), timeout=10)
    assert isinstance(raw_cells, bytes)
    return message, raw_cells


def assert_builtin_ai_player_can_choose_action() -> None:
    player = BuiltinAIPlayer(
        {
            "slot": 0,
            "tick": 0,
            "max_steps": 4,
            "game_config": {
                "seed": 1,
                "max_steps": 4,
            },
        }
    )
    try:
        action = player.choose_action({"slot": 0, "tick": 0})
        assert 0 <= action < 64
    finally:
        player.close()


def assert_coworld_envs_have_independent_builtin_ai() -> None:
    env_a = CoworldTribalVillageEnv(max_steps=4, config={"seed": 1})
    env_b = CoworldTribalVillageEnv(max_steps=4, config={"seed": 1})
    try:
        env_a.reset()
        env_b.reset()
        env_a.reset_builtin_ai(1)
        env_b.reset_builtin_ai(1)
        actions_a0 = env_a.builtin_ai_actions()
        env_a.step(actions_a0)
        assert env_b.builtin_ai_actions() == actions_a0
    finally:
        env_a.close()
        env_b.close()


def assert_action_tints_are_exported_as_sprite_state() -> None:
    env = CoworldTribalVillageEnv(max_steps=1000, config={"seed": 52})
    try:
        env.reset()
        env.reset_builtin_ai(52)
        for _ in range(1000):
            env.step(env.builtin_ai_actions())
            frame, cells = env.sprite_frame()
            stride = frame["stride"]
            for cell in range(frame["width"] * frame["height"]):
                idx = cell * stride
                if cells[idx + CELL_OFFSET_FLAGS] & ACTION_TINT_FLAG:
                    assert cells[idx + CELL_OFFSET_ACTION_R] > 0
                    assert cells[idx + CELL_OFFSET_ACTION_G] > 0
                    assert cells[idx + CELL_OFFSET_ACTION_B] > 0
                    return
        raise AssertionError("built-in AI never produced an exported action tint")
    finally:
        env.close()


def assert_client_websockets_are_proxy_relative() -> None:
    client_dir = ROOT / "tribal_village_env" / "coworld" / "clients"
    for client, websocket_path in {
        "global.html": "/global",
        "player.html": "/player",
        "replay.html": "/replay",
    }.items():
        html = (client_dir / client).read_text()
        assert './common/view_common.js' in html
        assert 'src="/client/' not in html
        assert "rgb_window" not in html
        assert 'kind !== "rgb"' not in html
        assert f"${{location.host}}{websocket_path}" not in html
    common_js = (client_dir / "view_common.js").read_text()
    assert f'const SPRITE_FRAME_KIND = "{SPRITE_FRAME_KIND}"' in common_js
    assert "const MIN_TILE_SCALE = 0.01" in common_js
    assert "minTileScale()" in common_js
    assert "clampView()" in common_js
    assert "this.tileScale * factor, this.minTileScale(), MAX_TILE_SCALE" in common_js
    assert "this.showLabels = options.showLabels === true" in common_js
    assert "setShowLabels(showLabels)" in common_js
    assert "if (!this.showLabels) return" in common_js
    assert "strokeRect(rectX + 1, rectY + 1" in common_js
    assert "function routedHttpAddress" in common_js
    assert "function websocketAddress" in common_js
    assert "function assetBaseAddress" in common_js
    assert "new URL(address || window.location.href, window.location.href)" in common_js
    assert "tilePanel" not in common_js
    assert "updateTilePanel" not in common_js
    assert "drawFrame(frame)" not in common_js
    global_html = (client_dir / "global.html").read_text()
    assert 'id="status"' not in global_html
    assert 'class="top-status"' not in global_html
    assert "team_scores" not in global_html
    assert "tilePanel" not in global_html
    player_html = (client_dir / "player.html").read_text()
    assert 'worldAddress.pathname.replace(/\\/player$/, "/global")' in player_html
    assert "worldAddress.search = \"\"" in player_html
    assert "tilePanel" not in player_html
    replay_html = (client_dir / "replay.html").read_text()
    assert "Tribal Village Replay</strong>" not in replay_html
    assert 'id="status"' not in replay_html
    assert 'class="top-status"' not in replay_html
    assert "tilePanel" not in replay_html
    assert 'data-replay="restart"' in replay_html
    assert 'id="timeline"' in replay_html
    assert 'id="names"' in replay_html
    assert "renderer.setShowLabels(namesEl.checked)" in replay_html
    assert 'data-speed="slower"' in replay_html
    assert 'data-speed="faster"' in replay_html
    assert 'type: "speed"' in replay_html
    assert 'type: "seek"' in replay_html
    assert "keydown" in replay_html
    manifest = json.loads((ROOT / "coworld_manifest_template.json").read_text())
    assert manifest["variants"][0]["game_config"]["max_steps"] == 2000
    assert manifest["certification"]["game_config"]["max_steps"] == 64
    assert manifest["variants"][0]["game_config"]["tick_rate"] == 20
    assert manifest["certification"]["game_config"]["tick_rate"] == 20
    assert (
        manifest["commissioner"][0]["source_url"]
        == "https://github.com/Metta-AI/commissioners/tree/main/commissioners/default"
    )


def assert_static_clients_are_served(port: int) -> None:
    with urlopen(
        f"http://127.0.0.1:{port}/client/common/view_common.js", timeout=5
    ) as response:
        assert response.status == 200
        assert b"WorldRenderer" in response.read()
    with urlopen(
        f"http://127.0.0.1:{port}/assets/objects/floor.png", timeout=5
    ) as response:
        assert response.status == 200
        assert response.read(8) == b"\x89PNG\r\n\x1a\n"


def main() -> None:
    assert_client_websockets_are_proxy_relative()
    with tempfile.TemporaryDirectory(prefix="tribal-village-coworld-") as temp:
        tempdir = Path(temp)
        config_path = tempdir / "config.json"
        results_path = tempdir / "results.json"
        replay_path = tempdir / "replay.json"
        replay_z_path = tempdir / "replay.json.z"
        config_path.write_text(
            json.dumps(
                {
                    "tokens": [f"token-{slot}" for slot in range(PLAYER_COUNT)],
                    "players": [
                        {"name": f"Agent {slot}"} for slot in range(PLAYER_COUNT)
                    ],
                    "max_steps": 4,
                    "tick_rate": 20,
                    "player_connect_timeout_seconds": 1,
                    "seed": 1,
                }
            )
        )
        port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(ROOT),
                "COGAME_HOST": "127.0.0.1",
                "COGAME_PORT": str(port),
                "COGAME_CONFIG_URI": f"file://{config_path}",
                "COGAME_RESULTS_URI": f"file://{results_path}",
                "COGAME_SAVE_REPLAY_URI": f"file://{replay_path}",
            }
        )
        process = subprocess.Popen(
            [sys.executable, "-m", "tribal_village_env.coworld.server"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_for_health(port, process)
            assert_static_clients_are_served(port)
            asyncio.run(
                assert_websocket_rejected(
                    f"ws://127.0.0.1:{port}/player?slot=0&token=bad",
                    "bad token was accepted",
                )
            )
            asyncio.run(
                assert_websocket_rejected(
                    f"ws://127.0.0.1:{port}/replay",
                    "live runtime accepted /replay as a visual stream",
                )
            )
            asyncio.run(assert_live_websockets(port))
            assert_builtin_ai_player_can_choose_action()
            assert_coworld_envs_have_independent_builtin_ai()
            assert_action_tints_are_exported_as_sprite_state()
            process.wait(timeout=30)
            if process.returncode != 0:
                stderr = process.stderr.read() if process.stderr else ""
                raise RuntimeError(f"server failed: {stderr[-4000:]}")
            results = json.loads(results_path.read_text())
            replay = json.loads(replay_path.read_text())
            assert len(results["scores"]) == PLAYER_COUNT
            assert len(results["team_scores"]) == 8
            assert results["truncation_reason"] == "max_steps"
            assert replay["schema"] == "tribal-village-replay-v2"
            assert replay["initial"]["players"][0] == "Agent 0"
            assert len(replay["ticks"]) == results["ticks"]
            assert "actions" not in replay
            assert "frame" not in replay_path.read_text()
            first_actions = base64.b64decode(
                replay["ticks"][0]["a"].encode("ascii"),
                validate=True,
            )
            assert len(first_actions) == PLAYER_COUNT
            assert first_actions[DELAYED_FIRST_ACTION_SLOT] == DELAYED_FIRST_ACTION
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)

        replay_z_path.write_bytes(zlib.compress(replay_path.read_bytes()))
        replay_port = free_port()
        replay_env = os.environ.copy()
        replay_env.update(
            {
                "PYTHONPATH": str(ROOT),
                "COGAME_HOST": "127.0.0.1",
                "COGAME_PORT": str(replay_port),
                "COGAME_LOAD_REPLAY_URI": f"file://{replay_z_path}",
            }
        )
        replay_process = subprocess.Popen(
            [sys.executable, "-m", "tribal_village_env.coworld.server"],
            cwd=ROOT,
            env=replay_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_for_health(replay_port, replay_process)
            asyncio.run(
                assert_websocket_rejected(
                    f"ws://127.0.0.1:{replay_port}/global",
                    "replay runtime accepted /global as a visual stream",
                )
            )
            asyncio.run(
                assert_websocket_rejected(
                    f"ws://127.0.0.1:{replay_port}/player?slot=0&token=token-0",
                    "replay runtime accepted /player",
                )
            )
            asyncio.run(assert_replay_autoplays_and_loops(replay_port))
        finally:
            if replay_process.poll() is None:
                replay_process.terminate()
                replay_process.wait(timeout=10)
            if replay_process.returncode not in {0, -15}:
                stderr = replay_process.stderr.read() if replay_process.stderr else ""
                raise RuntimeError(f"replay server failed: {stderr[-4000:]}")


if __name__ == "__main__":
    main()
