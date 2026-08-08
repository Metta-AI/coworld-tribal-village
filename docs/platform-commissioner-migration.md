# Platform commissioner migration

Tribal Village's live league (`league_aedc4933-a75a-40ab-aaef-1653e0796875`)
evaluates each champion in full self-play. Platform `clone_fill` is the direct
replacement for its container commissioner.

## Proposed ladder

Competition is `div_60d931c6-0d6d-483c-9a51-bf33f36016b7`; legacy Qualifiers
is `div_87ebea85-52ca-42ef-a5c3-555f3db373e5`.

```yaml
round_interval_minutes: 30
ladder:
  enabled: false
  scheduler:
    strategy: clone_fill
    insufficient_players: do_not_run
    seat_count: 48
    episodes_per_entrant: 1
    clone_score_aggregation: mean
    variant_rotation: [8-teams]
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

For each champion, the planner fills every 8×6 team seat with that policy.
Clone seats are not fillers: all authored seat scores collapse to one credited
episode score for the champion. Marking clones as filler would silently rank an
arbitrary single seat and is forbidden.

`platform_commissioner/settings.staged.json` and `settings.active.json` are
complete settings-API payloads and differ only at `ladder.enabled`. The explicit
48-seat count and single-variant rotation prevent the league's 18-seat default
variant from being resized without also updating `team_count`. `contract.json`
pins the live IDs and asserts the 8×6 topology against the manifest. The
repository validator checks all three artifacts against Metta's current
schemas.

## Proof and cutover

1. Land `clone_fill` planner and score-collapse replay-idempotency tests in
   Metta. Check plan size is `champions × episodes_per_entrant` and capped.
2. Hosted-smoke a full 48-seat self-play episode from the canonical manifest.
3. Compare frozen platform and container plans for one and three champions,
   including score aggregation and failure attribution.
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
