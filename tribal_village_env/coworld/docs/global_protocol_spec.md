# Tribal Village Global And Replay Protocol

Global viewers connect to:

```text
ws://<game-host>:8080/global
```

Replay viewers connect to:

```text
ws://<game-host>:8080/replay
```

Both routes send JSON state snapshots:

```json
{
  "type": "state",
  "tick": 12,
  "max_steps": 256,
  "started": true,
  "done": false,
  "scores": [0.0],
  "team_scores": [0.0],
  "player_names": ["Agent 0"],
  "agents": [
    {"slot": 0, "name": "Agent 0", "team": 0, "x": 23, "y": 17}
  ],
  "frame": {
    "kind": "rgb",
    "width": 192,
    "height": 108,
    "tile_size": 1,
    "data": []
  }
}
```

`frame.data` is a flat RGB uint8 array in row-major order. Replay snapshots use
`"type": "replay"` and loop to tick 0 after the recorded action log ends.
`agents` gives the current world tile position for each slot so browser clients
can draw `#slot name` labels above players.

The replay artifact uses the compact `tribal-village-replay-v2` schema:

```json
{
  "schema": "tribal-village-replay-v2",
  "initial": {
    "seed": 1,
    "max_steps": 256,
    "tick_rate": 20,
    "render_scale": 1,
    "window_radius": 5,
    "players": ["Agent 0"]
  },
  "ticks": [{"a": "base64-encoded 48 action bytes"}],
  "results": {}
}
```

The initial seed/config reconstructs the map and deterministic tumor/spawner
updates. Each tick stores only the 48 player action bytes; no rendered frames are
stored in the replay artifact.
