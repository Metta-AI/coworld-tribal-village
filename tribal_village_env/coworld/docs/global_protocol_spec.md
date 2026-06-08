# Tribal Village Global And Replay Protocol

Global viewers connect to:

```text
ws://<game-host>:8080/global
```

Replay viewers connect to:

```text
ws://<game-host>:8080/replay
```

The live route sends `"type": "state"` snapshots. The replay route sends
`"type": "replay"` snapshots. Both routes send one JSON state snapshot followed
by one binary sprite-cell buffer for each rendered frame:

```json
{
  "type": "state",
  "tick": 12,
  "max_steps": 5000,
  "started": true,
  "done": false,
  "scores": [0.0],
  "team_scores": [0.0],
  "player_names": ["Agent 0"],
  "agents": [
    {"slot": 0, "name": "Agent 0", "team": 0, "x": 23, "y": 17}
  ],
  "frame": {
    "kind": "tribal-village-sprite-cells-v1",
    "encoding": "uint8-arraybuffer",
    "width": 196,
    "height": 112,
    "stride": 24,
    "asset_base": "/assets"
  }
}
```

The binary payload is a row-major `Uint8Array` with `width * height * stride`
bytes. Each 24-byte sprite cell contains terrain, tile tint, object kind,
orientation, agent/team ids, health, inventory counts, building counts,
cooldown/frozen state, and flags. Browser clients render the real sprite map by
loading assets from `/assets/...` and shared code from
`/client/common/view_common.js`.

Replay snapshots use `"type": "replay"` and loop to tick 0 after the recorded
action log ends. Replay artifacts store actions only:

```json
{
  "schema": "tribal-village-replay-v2",
  "initial": {
    "seed": 1,
    "max_steps": 5000,
    "tick_rate": 20,
    "players": ["Agent 0"]
  },
  "ticks": [{"a": "base64-encoded 48 action bytes"}],
  "results": {}
}
```
