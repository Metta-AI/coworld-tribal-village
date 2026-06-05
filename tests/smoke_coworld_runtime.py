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
from urllib.error import URLError
from urllib.request import urlopen

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

from tribal_village_env.coworld.player import BuiltinAIPlayer


ROOT = Path(__file__).resolve().parents[1]
PLAYER_COUNT = 48


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


async def assert_bad_token_rejected(port: int) -> None:
    rejected = False
    try:
        async with websockets.connect(
            f"ws://127.0.0.1:{port}/player?slot=0&token=bad",
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
        raise AssertionError("bad token was accepted")


async def assert_live_websockets(port: int) -> None:
    async with websockets.connect(
        f"ws://127.0.0.1:{port}/global",
        open_timeout=5,
        max_size=None,
    ) as global_ws:
        message = json.loads(await asyncio.wait_for(global_ws.recv(), timeout=10))
        assert message["type"] == "state"
        assert message["frame"]["kind"] == "rgb"
        assert message["frame"]["tile_size"] == 1
        assert len(message["agents"]) == PLAYER_COUNT
        assert message["agents"][0]["slot"] == 0
        assert message["agents"][0]["name"] == "Agent 0"

    async with websockets.connect(
        f"ws://127.0.0.1:{port}/player?slot=0&token=token-0",
        open_timeout=5,
        max_size=None,
    ) as player_ws:
        message = json.loads(await asyncio.wait_for(player_ws.recv(), timeout=10))
        assert message["type"] == "observation"
        assert message["slot"] == 0
        assert message["action_space"]["n"] == 64
        assert message["game_config"]["seed"] == 1
        assert message["view"]["kind"] == "rgb_window"
        assert message["view"]["width"] > 0
        await player_ws.send(json.dumps({"type": "action", "action": 8}))


async def assert_replay_autoplays_and_loops(port: int) -> None:
    async with websockets.connect(
        f"ws://127.0.0.1:{port}/replay",
        open_timeout=5,
        max_size=None,
    ) as replay_ws:
        seen_done = False
        seen_loop = False
        for _ in range(12):
            message = json.loads(await asyncio.wait_for(replay_ws.recv(), timeout=10))
            assert message["type"] == "replay"
            assert message["started"] is True
            assert message["frame"]["kind"] == "rgb"
            assert len(message["agents"]) == PLAYER_COUNT
            assert message["agents"][0]["slot"] == 0
            assert message["agents"][0]["name"] == "Agent 0"
            if message["done"]:
                seen_done = True
            elif seen_done and message["tick"] == 0:
                seen_loop = True
                break
        assert seen_done
        assert seen_loop


def assert_builtin_ai_player_can_choose_action() -> None:
    player = BuiltinAIPlayer(
        {
            "slot": 0,
            "tick": 0,
            "max_steps": 4,
            "game_config": {
                "seed": 1,
                "max_steps": 4,
                "render_scale": 1,
                "window_radius": 5,
            },
        }
    )
    try:
        action = player.choose_action({"slot": 0, "tick": 0})
        assert 0 <= action < 64
    finally:
        player.close()


def assert_client_websockets_are_proxy_relative() -> None:
    client_dir = ROOT / "tribal_village_env" / "coworld" / "clients"
    for client, websocket_path in {
        "global.html": "/global",
        "player.html": "/player",
        "replay.html": "/replay",
    }.items():
        html = (client_dir / client).read_text()
        assert "function websocketAddress(path)" in html
        assert "new URL(address || window.location.href, window.location.href)" in html
        assert f'websocketAddress("{websocket_path}")' in html
        assert f"${{location.host}}{websocket_path}" not in html
    assert "replace(/\\/client\\/replay(\\/.*)?$/, `${path}$1`)" in (client_dir / "replay.html").read_text()


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
                    "render_scale": 1,
                    "window_radius": 5,
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
            asyncio.run(assert_bad_token_rejected(port))
            asyncio.run(assert_live_websockets(port))
            assert_builtin_ai_player_can_choose_action()
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
