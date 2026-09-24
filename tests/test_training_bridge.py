"""Focused native training bridge checks without the WASM build dependency."""

from __future__ import annotations

import json

from tools.training_bridge import TrainingSession


def test_all_roster_sizes_finish_with_native_teacher() -> None:
    for variant, players in (
        ("certification", 18),
        ("2-teams", 12),
        ("4-teams", 24),
        ("5-teams", 30),
        ("6-teams", 36),
        ("7-teams", 42),
        ("8-teams", 48),
    ):
        session = TrainingSession(variant, "choice", 2)
        try:
            observation = session.reset({"players": players, "seed": 17})
            while observation["kind"] == "decision":
                encoding = session.encode()
                assert encoding["decision_id"] == observation["decision_id"]
                assert len(encoding["values"]) == 26 * 11 * 11
                assert len(encoding["actions"]) == 64
                result = session.step(
                    {
                        "decision_id": observation["decision_id"],
                        "response": session.teacher()["response"],
                    }
                )
                assert result["kind"] == "accepted"
                observation = result["observation"]
            assert session.env is not None
            assert session.env.step_count == 2
            assert len(observation["scores"]) == players
        finally:
            session.close()


def test_text_mode_uses_same_action_and_observation() -> None:
    session = TrainingSession("2-teams", "text", 1)
    try:
        observation = session.reset({"players": 12, "seed": 17})
        assert observation["typed_question"] is None
        assert json.loads(observation["messages"][1]["content"])["seat"] == 0
        assert (
            session.step(
                {"decision_id": observation["decision_id"], "response": '{"action":64}'}
            )["kind"]
            == "rejected"
        )
        assert (
            session.step(
                {"decision_id": observation["decision_id"], "response": '{"action":8}'}
            )["kind"]
            == "accepted"
        )
    finally:
        session.close()


def test_hashed_episode_seed_stays_in_native_range() -> None:
    session = TrainingSession("certification", "choice", 1)
    try:
        first = session.reset({"players": 18, "seed": "full-cert"})
        assert session.env is not None
        seed = session.env.config["seed"]
        assert 1 <= seed <= 2**31 - 1
        second = session.reset({"players": 18, "seed": "full-cert"})
        assert session.env.config["seed"] == seed
        assert first["semantic_view"] == second["semantic_view"]
    finally:
        session.close()


if __name__ == "__main__":
    test_all_roster_sizes_finish_with_native_teacher()
    test_text_mode_uses_same_action_and_observation()
    test_hashed_episode_seed_stays_in_native_range()
