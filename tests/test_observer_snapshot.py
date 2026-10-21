"""Public presentation must leave the native episode and player ABI intact."""

import dataclasses
import hashlib
import json

import numpy as np
import pytest

from tribal_village_env.coworld.direct_env import CoworldTribalVillageEnv
from tribal_village_env.coworld.observer import ObserverSnapshot


@pytest.mark.parametrize("teams", [2, 8])
def test_observing_does_not_change_native_episode(teams):
    baseline = CoworldTribalVillageEnv(
        max_steps=12, config={"seed": 17, "team_count": teams}
    )
    observed = CoworldTribalVillageEnv(
        max_steps=12, config={"seed": 17, "team_count": teams}
    )
    try:
        baseline.reset()
        observed.reset()
        baseline.reset_builtin_ai(17)
        observed.reset_builtin_ai(17)
        for tick in range(13):
            metadata, original = baseline.sprite_frame()
            public = ObserverSnapshot.from_sprite_frame(tick, *observed.sprite_frame())
            assert public.cells == original
            assert public.width == metadata["width"]
            assert public.height == metadata["height"]
            assert public.tick == tick
            for name, dtype in (
                ("observations", np.uint8),
                ("rewards", np.float32),
                ("terminals", np.uint8),
                ("truncations", np.uint8),
            ):
                a, b = getattr(baseline, name), getattr(observed, name)
                assert a.dtype == b.dtype == dtype
                assert a.flags.c_contiguous and b.flags.c_contiguous
                np.testing.assert_array_equal(a, b)
            assert observed.observations.shape == (48, 26, 11, 11)
            # Display edits operate on a copy, never native observation memory.
            edited = bytearray(public.cells)
            edited[:] = bytes(len(edited))
            assert observed.sprite_frame()[1] == original
            assert public.cells == original
            with pytest.raises(dataclasses.FrozenInstanceError):
                public.tick = 999
            if tick < 12:
                actions = baseline.builtin_ai_actions()
                assert observed.builtin_ai_actions() == actions
                baseline.step(actions)
                observed.step(actions)
        assert observed.truncations.any()
    finally:
        baseline.close()
        observed.close()


def test_snapshot_rejects_private_or_malformed_buffers():
    metadata = {
        "kind": "tribal-village-sprite-cells-v2",
        "encoding": "uint8-arraybuffer",
        "width": 2,
        "height": 1,
        "stride": 28,
    }
    for change, payload in (
        ({"stride": 26}, bytes(56)),
        ({"kind": "player"}, bytes(56)),
        ({}, bytes(55)),
        ({"width": -2}, bytes(56)),
    ):
        with pytest.raises(ValueError):
            ObserverSnapshot.from_sprite_frame(0, metadata | change, payload)
    with pytest.raises(ValueError):
        ObserverSnapshot.from_sprite_frame(-1, metadata, bytes(56))


def test_snapshot_owns_immutable_public_copy():
    source = bytearray(28)
    metadata = {
        "kind": "tribal-village-sprite-cells-v2",
        "encoding": "uint8-arraybuffer",
        "width": 1,
        "height": 1,
        "stride": 28,
    }
    public = ObserverSnapshot.from_sprite_frame(0, metadata, source)
    source[0] = 255
    assert public.cells == bytes(28)


def test_spectator_socket_cannot_supply_player_actions(monkeypatch):
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from tribal_village_env.coworld import server

    config = server.CoworldConfig.from_dict(
        {
            "team_count": 2,
            "num_agents": 12,
            "seed": 17,
            "max_steps": 12,
            "tokens": [f"test-{i}" for i in range(12)],
            "players": [{"name": f"Player {i}"} for i in range(12)],
        }
    )
    runtime = server.TribalVillageCoworld(config=config, results_uri="", replay_uri="")
    monkeypatch.setattr(server, "runtime", runtime)
    client = TestClient(server.app)
    try:
        before = runtime.env.sprite_frame()[1]
        private = runtime.env.observations.copy()
        with client.websocket_connect("/global") as spectator:
            spectator.receive_json()
            assert spectator.receive_bytes() == before
            spectator.send_json({"action": 63, "slot": 0})
            spectator.receive_json()
            assert spectator.receive_bytes() == before
        assert runtime.actions == [0] * 12
        assert runtime.action_versions == [0] * 12
        assert runtime.env.step_count == 0
        np.testing.assert_array_equal(runtime.env.observations, private)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/player?slot=0&token=spectator"):
                pass
    finally:
        runtime.env.close()


@pytest.mark.parametrize("teams", [2, 8])
def test_runtime_replay_is_identical_with_public_observer(teams):
    from tribal_village_env.coworld.server import (
        CoworldConfig,
        TribalVillageCoworld,
        TribalVillageReplay,
    )

    config = CoworldConfig.from_dict(
        {
            "team_count": teams,
            "num_agents": teams * 6,
            "seed": 17,
            "max_steps": 64,
            "tokens": [f"test-{i}" for i in range(teams * 6)],
            "players": [{"name": f"Player {i}"} for i in range(teams * 6)],
        }
    )
    runs = [
        TribalVillageCoworld(config=config, results_uri="", replay_uri="")
        for _ in range(2)
    ]
    restored = None
    try:
        for runtime in runs:
            runtime.env.reset_builtin_ai(17)
        for tick in range(64):
            action = runs[0].env.builtin_ai_actions()[: teams * 6]
            assert runs[1].env.builtin_ai_actions()[: teams * 6] == action
            for runtime in runs:
                runtime._step(action.copy())
            ObserverSnapshot.from_sprite_frame(
                tick + 1, *runs[1].env.sprite_frame()
            ).payload()
        payloads = [r.replay_payload(r.results()) for r in runs]
        hashes = [
            hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
            for p in payloads
        ]
        assert hashes[0] == hashes[1]
        restored = TribalVillageReplay(payloads[1]).env_at_tick(64)
        assert restored.sprite_frame()[1] == runs[0].env.sprite_frame()[1]
        for name in ("observations", "rewards", "terminals", "truncations"):
            np.testing.assert_array_equal(
                getattr(restored, name), getattr(runs[0].env, name)
            )
    finally:
        if restored is not None:
            restored.close()
        for runtime in runs:
            runtime.env.close()
