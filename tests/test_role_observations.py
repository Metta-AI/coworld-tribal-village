from __future__ import annotations

import numpy as np
import pytest

pufferlib = pytest.importorskip("pufferlib")
del pufferlib

from tribal_village_env import ensure_nim_library_current
from tribal_village_env.environment import TRAINING_AGENT_STRIDE, TribalVillageEnv


def test_scripted_role_observations_match_training_state() -> None:
    ensure_nim_library_current(verbose=False)
    env = TribalVillageEnv(config={"seed": 1, "max_steps": 4})
    try:
        env.reset(seed=1)
        agents, _objects = env.export_training_state()
        expected_roles = np.tile(np.asarray([3, 3, 2, 3, 3, 4], dtype=np.int32), 8)

        assert env.obs_layers == 26
        assert TRAINING_AGENT_STRIDE == 27
        assert agents.shape == (48, 27)
        np.testing.assert_array_equal(agents[:, 22].astype(np.int32), expected_roles)
        assert np.all(agents[:, 23] == 0)
        assert np.all(agents[:, 26] == 0)

        role_planes = env.observations[:, 21:26]
        expected_role_planes = np.eye(5, dtype=np.int32)[expected_roles] * 121
        np.testing.assert_array_equal(role_planes.sum(axis=(2, 3)), expected_role_planes)

        env.reset_builtin_ai(seed=1)
        actions = env.builtin_ai_actions()
        assert len(actions) == 48
        agents, _objects = env.export_training_state()
        assert agents.shape == (48, 27)
        assert np.any(agents[:, 23] > 0)
        valid_target_rows = agents[:, 26] > 0
        assert np.any(valid_target_rows)
        assert np.all(agents[valid_target_rows, 24] >= 0)
        assert np.all(agents[valid_target_rows, 25] >= 0)
    finally:
        env.close()
