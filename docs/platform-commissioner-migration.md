# Platform commissioner migration

Tribal Village's live league (`league_aedc4933-a75a-40ab-aaef-1653e0796875`)
seats one champion in each active village. Platform `team_n` with block layout
is the direct replacement for its container commissioner. The checked-in active
settings currently select three teams because the live league has three
champions; the manifest and contract support every team count from two through
eight.

## Proposed ladder

Competition is `div_60d931c6-0d6d-483c-9a51-bf33f36016b7`; legacy Qualifiers
is `div_87ebea85-52ca-42ef-a5c3-555f3db373e5`.

```yaml
round_interval_minutes: 30
ladder:
  enabled: false
  scheduler:
    strategy: team_n
    insufficient_players: do_not_run
    team_count: 3
    team_layout: blocks
    min_episodes_per_entrant: 1
    variant_rotation: [default]
  ranking:
    algorithm: score
    round_scoring_rule: mean
    standing_aggregation: ewma
    half_life_hours: 2
  fulfillment:
    allowed_failures: 0.05
    retry_times: 2
  divisions:
    - division_id: div_60d931c6-0d6d-483c-9a51-bf33f36016b7
      name: Competition
      disqualify_after_consecutive_failures: 3
```

For a configured N-team shape, the planner derives `ceil(champions / N)` tables,
assigns one champion to each village, and clones that champion across the
village's contiguous six-seat block. Clone seats are filler-marked after the
first occurrence so every champion receives one credited score per episode. A
production round readback for the current three-team shape confirmed
`[A×6, B×6, C×6]` rather than 48-seat self-play.

`platform_commissioner/settings.staged.json` and `settings.active.json` are
complete settings-API payloads and differ only at `ladder.enabled`. The explicit
default-variant rotation pins the live 18-seat, three-team shape.
`contract.json` pins the live IDs, the 2-8 variant map, and the six-seat team
block invariant. The repository validator checks all seven shapes against
Metta's current schemas. Render the complete settings payload for a roster size
with `python scripts/render_platform_settings.py N`; apply that full payload
when the active champion count changes.

## Proof and cutover

1. Land block-layout `team_n` planner and score-attribution tests in Metta.
   Check plan size is `ceil(champions / 3)` and every champion appears.
2. Hosted-smoke the canonical 18-seat, three-village variant.
3. Compare frozen platform and container plans for one and three champions,
   including `[A×6, B×6, C×6]` seating, score aggregation, and failure
   attribution.
4. Route a test submission directly to Competition and confirm no qualification
   experience is created; archive Qualifiers only after this succeeds.
5. Write/read settings disabled, pause/drain, patch the full seed overrides to
   platform, enable/unpause, and prove one Temporal cycle and EWMA update.

Standings restart. Rollback drains Temporal, disables the ladder, restores the
seed to `container`, and proves a container round before unpausing. The bundled
commissioner remains available through soak.

Run the repository-owned contract check locally with:

```bash
uv run --no-project --with pydantic --with jsonschema \
  python scripts/validate_platform_commissioner.py --metta-root ../metta
```
