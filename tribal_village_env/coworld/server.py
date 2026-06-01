from __future__ import annotations

import asyncio
import gzip
import json
import os
import zlib
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

from tribal_village_env.coworld.direct_env import (
    ACTION_ARGUMENT_COUNT,
    ACTION_SPACE_SIZE,
    ACTION_VERB_COUNT,
    CoworldTribalVillageEnv,
)

CLIENT_DIR = Path(__file__).parent / "clients"
HTTP_USER_AGENT = "coworld-tribal-village/0.1"

CONFIG_ENV_VAR = "COGAME_CONFIG_URI"
RESULTS_ENV_VAR = "COGAME_RESULTS_URI"
REPLAY_SAVE_ENV_VAR = "COGAME_SAVE_REPLAY_URI"
REPLAY_LOAD_ENV_VAR = "COGAME_LOAD_REPLAY_URI"
GAME_HOST = os.environ.get("COGAME_HOST", "0.0.0.0")
GAME_PORT = int(os.environ.get("COGAME_PORT", "8080"))

PLAYER_COUNT = 48
TEAM_COUNT = 8
AGENTS_PER_TEAM = 6
DEFAULT_MAX_STEPS = 256
DEFAULT_TICK_RATE = 20.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0


def read_data(uri: str) -> bytes:
    parsed = urlparse(uri)
    if parsed.scheme in ("http", "https"):
        request = Request(uri, headers={"User-Agent": HTTP_USER_AGENT})
        with urlopen(request, timeout=30) as response:
            return response.read()
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).read_bytes()
    if parsed.scheme == "":
        return Path(uri).read_bytes()
    raise ValueError(f"Unsupported URI for read_data: {uri}")


def artifact_method(env_var: str) -> Literal["POST", "PUT"]:
    method = os.environ.get(env_var, "PUT").upper()
    if method not in {"POST", "PUT"}:
        raise ValueError(f"{env_var} must be PUT or POST")
    return cast(Literal["POST", "PUT"], method)


def write_data(
    uri: str,
    data: bytes | str,
    *,
    content_type: str,
    http_method: Literal["POST", "PUT"],
) -> None:
    if isinstance(data, str):
        data = data.encode("utf-8")

    parsed = urlparse(uri)
    if parsed.scheme in ("http", "https"):
        request = Request(uri, data=data, method=http_method)
        request.add_header("Content-Type", content_type)
        request.add_header("User-Agent", HTTP_USER_AGENT)
        with urlopen(request, timeout=60):
            return
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return
    if parsed.scheme == "":
        path = Path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return
    raise ValueError(f"Unsupported URI for write_data: {uri}")


def load_replay_payload(uri: str) -> dict[str, Any]:
    data = read_data(uri)
    if uri.endswith(".json.z"):
        data = zlib.decompress(data)
    elif uri.endswith(".json.gz"):
        data = gzip.decompress(data)
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Replay payload must be a JSON object")
    return payload


@dataclass(frozen=True)
class CoworldConfig:
    tokens: list[str]
    players: list[dict[str, str]]
    max_steps: int
    tick_rate: float
    player_connect_timeout_seconds: float
    render_scale: int
    window_radius: int
    seed: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CoworldConfig":
        tokens = [str(token) for token in data.get("tokens", [])]
        if len(tokens) != PLAYER_COUNT:
            raise ValueError(
                f"Tribal Village Coworld requires {PLAYER_COUNT} tokens, "
                f"got {len(tokens)}"
            )
        if any(not token for token in tokens):
            raise ValueError("Coworld tokens must be non-empty strings")

        players = _player_configs(data.get("players", []))
        max_steps = int(data.get("max_steps", DEFAULT_MAX_STEPS))
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        tick_rate = float(data.get("tick_rate", DEFAULT_TICK_RATE))
        if tick_rate <= 0 or tick_rate > 60:
            raise ValueError("tick_rate must be > 0 and <= 60")
        connect_timeout = float(
            data.get(
                "player_connect_timeout_seconds",
                DEFAULT_CONNECT_TIMEOUT_SECONDS,
            )
        )
        if connect_timeout < 0:
            raise ValueError("player_connect_timeout_seconds must be non-negative")
        render_scale = max(1, int(data.get("render_scale", 1)))
        window_radius = max(1, int(data.get("window_radius", 5)))
        seed = max(1, int(data.get("seed", 1)))
        return cls(
            tokens=tokens,
            players=players,
            max_steps=max_steps,
            tick_rate=tick_rate,
            player_connect_timeout_seconds=connect_timeout,
            render_scale=render_scale,
            window_radius=window_radius,
            seed=seed,
        )

    @property
    def player_names(self) -> list[str]:
        return [player["name"] for player in self.players]

    def replay_config(self) -> dict[str, Any]:
        return {
            "players": self.players,
            "max_steps": self.max_steps,
            "tick_rate": self.tick_rate,
            "render_scale": self.render_scale,
            "window_radius": self.window_radius,
            "seed": self.seed,
        }


def _player_configs(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) != PLAYER_COUNT:
        raise ValueError(f"players must be an array of {PLAYER_COUNT} objects")
    players: list[dict[str, str]] = []
    for slot, player in enumerate(value):
        if not isinstance(player, dict):
            raise ValueError(f"players[{slot}] must be an object")
        name = str(player.get("name", "")).strip()
        if not name:
            raise ValueError(f"players[{slot}].name must be non-empty")
        players.append({"name": name})
    return players


def _default_players() -> list[dict[str, str]]:
    return [{"name": f"Agent {slot}"} for slot in range(PLAYER_COUNT)]


def _make_env(
    *,
    max_steps: int,
    render_scale: int = 1,
    window_radius: int = 5,
    seed: int = 1,
) -> CoworldTribalVillageEnv:
    return CoworldTribalVillageEnv(
        max_steps=max_steps,
        render_scale=render_scale,
        window_radius=window_radius,
        config={"seed": seed},
    )


class TribalVillageCoworld:
    def __init__(
        self,
        *,
        config: CoworldConfig,
        results_uri: str,
        replay_uri: str,
    ) -> None:
        self.config = config
        self.results_uri = results_uri
        self.replay_uri = replay_uri
        self.env = _make_env(
            max_steps=config.max_steps,
            render_scale=config.render_scale,
            window_radius=config.window_radius,
            seed=config.seed,
        )
        self.env.reset()
        self.latest_rewards = [0.0 for _ in range(PLAYER_COUNT)]
        self.latest_terminated = [False for _ in range(PLAYER_COUNT)]
        self.latest_truncated = [False for _ in range(PLAYER_COUNT)]
        self.actions = [0 for _ in range(PLAYER_COUNT)]
        self.cumulative_scores = [0.0 for _ in range(PLAYER_COUNT)]
        self.action_log: list[list[int]] = []
        self.player_websockets: dict[int, list[WebSocket]] = {}
        self.connected_slots: set[int] = set()
        self.started = False
        self.done = False
        self.truncation_reason = ""
        self.game_task: asyncio.Task[None] | None = None
        self.timeout_task: asyncio.Task[None] | None = None
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        self.timeout_task = asyncio.create_task(self._start_after_connect_timeout())

    async def close(self) -> None:
        for task in (self.timeout_task, self.game_task):
            if task is not None and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        self.env.close()

    async def player(self, websocket: WebSocket) -> None:
        try:
            slot = int(websocket.query_params.get("slot", ""))
        except ValueError:
            await websocket.close(code=1008)
            return
        token = websocket.query_params.get("token", "")
        if slot < 0 or slot >= PLAYER_COUNT or self.config.tokens[slot] != token:
            await websocket.close(code=1008)
            return

        await websocket.accept()
        async with self.lock:
            self.player_websockets.setdefault(slot, []).append(websocket)
            self.connected_slots.add(slot)
            should_start = len(self.connected_slots) == PLAYER_COUNT
        await websocket.send_json(self.player_message(slot))
        if should_start:
            self.start_game()

        try:
            async for message in websocket.iter_json():
                action = _coerce_action(message)
                async with self.lock:
                    self.actions[slot] = action
        finally:
            async with self.lock:
                sockets = self.player_websockets.get(slot)
                if sockets is not None and websocket in sockets:
                    sockets.remove(websocket)

    async def global_viewer(self, websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(self.snapshot("state"))
                if self.done:
                    break
                await asyncio.sleep(0.25)
        except Exception:
            return

    def start_game(self) -> None:
        if self.started or self.done:
            return
        self.started = True
        self.game_task = asyncio.create_task(self._run_game())

    async def _start_after_connect_timeout(self) -> None:
        await asyncio.sleep(self.config.player_connect_timeout_seconds)
        self.start_game()

    async def _run_game(self) -> None:
        await asyncio.sleep(0.1)
        while self.env.step_count < self.config.max_steps and not self.done:
            async with self.lock:
                actions = self.actions.copy()
            self._step(actions)
            await self._broadcast_players()
            if self.env.step_count >= self.config.max_steps:
                self.truncation_reason = "max_steps"
                break
            if self._all_done():
                self.truncation_reason = "all_done"
                break
            await asyncio.sleep(1.0 / self.config.tick_rate)

        if not self.truncation_reason:
            self.truncation_reason = "max_steps"
        self.done = True
        results = self.results()
        write_data(
            self.results_uri,
            json.dumps(results, separators=(",", ":")) + "\n",
            content_type="application/json",
            http_method=artifact_method("COGAME_RESULTS_METHOD"),
        )
        write_data(
            self.replay_uri,
            json.dumps(self.replay_payload(results), separators=(",", ":")),
            content_type="application/json",
            http_method=artifact_method("COGAME_SAVE_REPLAY_METHOD"),
        )
        await self._broadcast_players(final=True)
        if server is not None:
            server.should_exit = True

    def _step(self, actions: list[int]) -> None:
        self.env.step([int(action) for action in actions])
        self.latest_rewards = [float(value) for value in self.env.rewards.tolist()]
        self.latest_terminated = [bool(value) for value in self.env.terminals.tolist()]
        self.latest_truncated = [
            bool(value) or self.env.step_count >= self.config.max_steps
            for value in self.env.truncations.tolist()
        ]
        for slot in range(PLAYER_COUNT):
            self.cumulative_scores[slot] += self.latest_rewards[slot]
        self.action_log.append(actions)

    async def _broadcast_players(self, *, final: bool = False) -> None:
        async with self.lock:
            sockets = {
                slot: list(slot_sockets)
                for slot, slot_sockets in self.player_websockets.items()
            }
        for slot, slot_sockets in sockets.items():
            message = self.player_message(slot, final=final)
            for websocket in slot_sockets:
                try:
                    await websocket.send_json(message)
                except Exception:
                    async with self.lock:
                        current = self.player_websockets.get(slot)
                        if current is not None and websocket in current:
                            current.remove(websocket)

    def player_message(self, slot: int, *, final: bool = False) -> dict[str, Any]:
        return {
            "type": "final" if final or self.done else "observation",
            "slot": slot,
            "name": self.config.players[slot]["name"],
            "tick": self.env.step_count,
            "max_steps": self.config.max_steps,
            "reward": float(self.latest_rewards[slot]),
            "score": float(self.cumulative_scores[slot]),
            "terminated": bool(self.latest_terminated[slot]),
            "truncated": bool(self.latest_truncated[slot]),
            "done": final or self.done,
            "action_space": {
                "type": "discrete",
                "n": ACTION_SPACE_SIZE,
                "verb_count": ACTION_VERB_COUNT,
                "argument_count": ACTION_ARGUMENT_COUNT,
            },
            "game_config": {
                "seed": self.config.seed,
                "max_steps": self.config.max_steps,
                "render_scale": self.config.render_scale,
                "window_radius": self.config.window_radius,
            },
            "view": self.env.player_view(slot),
        }

    def snapshot(self, message_type: str) -> dict[str, Any]:
        return {
            "type": message_type,
            "tick": self.env.step_count,
            "max_steps": self.config.max_steps,
            "started": self.started,
            "done": self.done,
            "scores": [float(score) for score in self.cumulative_scores],
            "team_scores": self.team_scores(),
            "player_names": self.config.player_names,
            "frame": self.env.frame_payload(),
        }

    def team_scores(self) -> list[float]:
        return [
            float(sum(self.cumulative_scores[start : start + AGENTS_PER_TEAM]))
            for start in range(0, PLAYER_COUNT, AGENTS_PER_TEAM)
        ]

    def results(self) -> dict[str, Any]:
        return {
            "scores": [float(score) for score in self.cumulative_scores],
            "team_scores": self.team_scores(),
            "ticks": int(self.env.step_count),
            "truncation_reason": self.truncation_reason or "unknown",
        }

    def replay_payload(self, results: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema": "tribal-village-replay-v1",
            "config": self.config.replay_config(),
            "player_names": self.config.player_names,
            "actions": self.action_log,
            "results": results,
        }

    def _all_done(self) -> bool:
        return all(
            bool(self.latest_terminated[slot]) or bool(self.latest_truncated[slot])
            for slot in range(PLAYER_COUNT)
        )


class TribalVillageReplay:
    def __init__(self, payload: dict[str, Any]) -> None:
        if payload.get("schema") != "tribal-village-replay-v1":
            raise ValueError("Unsupported Tribal Village replay schema")
        config = payload.get("config", {})
        if not isinstance(config, dict):
            raise ValueError("Replay config must be an object")
        actions = payload.get("actions", [])
        if not isinstance(actions, list):
            raise ValueError("Replay actions must be an array")
        self.actions = [
            [_coerce_action({"action": action}) for action in tick_actions]
            for tick_actions in actions
            if isinstance(tick_actions, list)
        ]
        players = config.get("players") or _default_players()
        if not isinstance(players, list) or len(players) != PLAYER_COUNT:
            players = _default_players()
        self.player_names = [
            str(player.get("name", f"Agent {slot}"))
            if isinstance(player, dict)
            else f"Agent {slot}"
            for slot, player in enumerate(players)
        ]
        self.max_steps = max(1, len(self.actions))
        self.tick_rate = float(config.get("tick_rate", DEFAULT_TICK_RATE))
        self.render_scale = max(1, int(config.get("render_scale", 1)))
        self.window_radius = max(1, int(config.get("window_radius", 5)))
        self.seed = max(1, int(config.get("seed", 1)))
        self.results = payload.get("results", {})

    async def stream(self, websocket: WebSocket) -> None:
        await websocket.accept()
        env = _make_env(
            max_steps=self.max_steps,
            render_scale=self.render_scale,
            window_radius=self.window_radius,
            seed=self.seed,
        )
        try:
            env.reset()
            while True:
                await websocket.send_json(self._snapshot(env))
                if env.step_count >= len(self.actions):
                    env.close()
                    env = _make_env(
                        max_steps=self.max_steps,
                        render_scale=self.render_scale,
                        window_radius=self.window_radius,
                        seed=self.seed,
                    )
                    env.reset()
                    await asyncio.sleep(0.2)
                    continue
                actions = self.actions[env.step_count]
                replay_actions = [
                    int(actions[slot]) if slot < len(actions) else 0
                    for slot in range(PLAYER_COUNT)
                ]
                env.step(replay_actions)
                await asyncio.sleep(1.0 / max(1.0, self.tick_rate))
        except Exception:
            return
        finally:
            env.close()

    def _snapshot(self, env: CoworldTribalVillageEnv) -> dict[str, Any]:
        return {
            "type": "replay",
            "tick": env.step_count,
            "max_steps": self.max_steps,
            "started": True,
            "done": env.step_count >= len(self.actions),
            "scores": self.results.get("scores", []),
            "team_scores": self.results.get("team_scores", []),
            "player_names": self.player_names,
            "frame": env.frame_payload(),
        }


def _coerce_action(message: Any) -> int:
    value: Any
    if isinstance(message, dict):
        if "action" in message:
            value = message["action"]
        elif "verb" in message:
            verb = int(message.get("verb", 0))
            argument = int(message.get("argument", 0))
            value = verb * ACTION_ARGUMENT_COUNT + argument
        else:
            value = 0
    else:
        value = message
    try:
        action = int(value)
    except (TypeError, ValueError):
        return 0
    if action < 0 or action >= ACTION_SPACE_SIZE:
        return 0
    return action


runtime: TribalVillageCoworld | TribalVillageReplay | None = None
server: uvicorn.Server | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global runtime
    if REPLAY_LOAD_ENV_VAR in os.environ:
        runtime = TribalVillageReplay(load_replay_payload(os.environ[REPLAY_LOAD_ENV_VAR]))
    else:
        config = CoworldConfig.from_dict(
            json.loads(read_data(os.environ[CONFIG_ENV_VAR]).decode("utf-8"))
        )
        runtime = TribalVillageCoworld(
            config=config,
            results_uri=os.environ[RESULTS_ENV_VAR],
            replay_uri=os.environ[REPLAY_SAVE_ENV_VAR],
        )
        await runtime.start()
    try:
        yield
    finally:
        if isinstance(runtime, TribalVillageCoworld):
            await runtime.close()
        runtime = None


app = FastAPI(lifespan=lifespan)


def _runtime() -> TribalVillageCoworld | TribalVillageReplay:
    if runtime is None:
        raise RuntimeError("Tribal Village Coworld runtime is not initialized")
    return runtime


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/client/global")
def global_client() -> HTMLResponse:
    return HTMLResponse((CLIENT_DIR / "global.html").read_text())


@app.get("/client/player")
def player_client() -> HTMLResponse:
    return HTMLResponse((CLIENT_DIR / "player.html").read_text())


@app.get("/client/replay")
def replay_client() -> HTMLResponse:
    return HTMLResponse((CLIENT_DIR / "replay.html").read_text())


@app.websocket("/global")
async def global_viewer(websocket: WebSocket) -> None:
    active = _runtime()
    if isinstance(active, TribalVillageReplay):
        await active.stream(websocket)
    else:
        await active.global_viewer(websocket)


@app.websocket("/replay")
async def replay_viewer(websocket: WebSocket) -> None:
    active = _runtime()
    if isinstance(active, TribalVillageReplay):
        await active.stream(websocket)
    else:
        await active.global_viewer(websocket)


@app.websocket("/player")
async def player(websocket: WebSocket) -> None:
    active = _runtime()
    if isinstance(active, TribalVillageReplay):
        await websocket.close(code=1008)
        return
    await active.player(websocket)


if __name__ == "__main__":
    server = uvicorn.Server(uvicorn.Config(app, host=GAME_HOST, port=GAME_PORT))
    server.run()
