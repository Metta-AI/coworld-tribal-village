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
    episodes_per_entrant: 1
    clone_score_aggregation: mean
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

## Proof and cutover

1. Land `clone_fill` planner and score-collapse replay-idempotency tests in
   Metta. Check plan size is `champions × episodes_per_entrant` and capped.
2. Hosted-smoke a full 48-seat self-play episode from the canonical manifest.
3. Compare frozen platform and container plans for one and three champions,
   including score aggregation and failure attribution.
4. Decide whether the container completion qualifier becomes platform generic
   qualification or direct Competition placement; then archive Qualifiers only
   after the chosen path works.
5. Write/read settings disabled, pause/drain, patch the full seed overrides to
   platform, enable/unpause, and prove one Temporal cycle and EWMA update.

Standings restart. Rollback drains Temporal, disables the ladder, restores the
seed to `container`, and proves a container round before unpausing. The bundled
commissioner remains available through soak.
