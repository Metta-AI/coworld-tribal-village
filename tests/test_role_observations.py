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
        assert TRAINING_AGENT_STRIDE == 23
        assert agents.shape == (48, 23)
        np.testing.assert_array_equal(agents[:, 22].astype(np.int32), expected_roles)

        role_planes = env.observations[:, 21:26]
        expected_role_planes = np.eye(5, dtype=np.int32)[expected_roles] * 121
        np.testing.assert_array_equal(role_planes.sum(axis=(2, 3)), expected_role_planes)
    finally:
        env.close()
