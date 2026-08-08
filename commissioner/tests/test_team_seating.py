from pathlib import Path
from uuid import uuid4

import yaml

from commissioners.common.models import PolicyPool, PolicyPoolEntry
from commissioners.common.ruleset_strategy.config import (
    RulesetStrategyCommissionerConfig,
)
from commissioners.common.ruleset_strategy.scheduling import schedule_entries


def test_variant_team_count_assigns_one_policy_to_each_six_agent_village() -> None:
    config_path = (
        Path(__file__).parents[1]
        / "commissioners"
        / "ruleset_strategy_commissioner"
        / "configs"
        / "default.yaml"
    )
    config = RulesetStrategyCommissionerConfig.model_validate(
        yaml.safe_load(config_path.read_text())
    )
    pool = PolicyPool(id=uuid4())
    entries = [
        PolicyPoolEntry(
            pool_id=pool.id,
            policy_version_id=uuid4(),
            seed_order=index,
        )
        for index in range(3)
    ]

    schedule = schedule_entries(
        pool=pool,
        primary_entries=entries,
        filler_entries=[],
        num_agents=18,
        team_count=3,
        variant_id="default",
        game_config=None,
        config=config,
    )

    assert len(schedule.episodes) == 1
    assert schedule.episodes[0].policy_version_ids == [
        policy_version_id
        for entry in entries
        for policy_version_id in [entry.policy_version_id] * 6
    ]
