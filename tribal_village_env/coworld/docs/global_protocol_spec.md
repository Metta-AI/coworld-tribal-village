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
  "frame": {
    "kind": "rgb",
    "width": 192,
    "height": 108,
    "data": []
  }
}
```

`frame.data` is a flat RGB uint8 array in row-major order. Replay snapshots use
`"type": "replay"` and loop to tick 0 after the recorded action log ends.
