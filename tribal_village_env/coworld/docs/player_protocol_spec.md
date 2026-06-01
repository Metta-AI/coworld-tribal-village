# Tribal Village Player Protocol

Players connect to the runner-supplied `COWORLD_PLAYER_WS_URL`, which points at:

```text
ws://<game-host>:8080/player?slot=<0-47>&token=<runner-token>
```

The server sends JSON observations:

```json
{
  "type": "observation",
  "slot": 0,
  "name": "Agent 0",
  "tick": 12,
  "max_steps": 256,
  "reward": 0.0,
  "score": -0.12,
  "terminated": false,
  "truncated": false,
  "done": false,
  "action_space": {
    "type": "discrete",
    "n": 64,
    "verb_count": 8,
    "argument_count": 8
  },
  "game_config": {
    "seed": 1,
    "max_steps": 256,
    "render_scale": 1,
    "window_radius": 5
  },
  "view": {
    "kind": "rgb_window",
    "width": 11,
    "height": 11,
    "tile_width": 11,
    "tile_height": 11,
    "tile_size": 1,
    "radius": 5,
    "center": {"x": 10, "y": 10},
    "data": []
  }
}
```

`view.data` is a flat RGB uint8 array in row-major order. It is a rendered
window centered on the player's current agent, using the same tile/sprite colors
as the global viewer. Players that want neural observations should derive them
from this game-facing view in their own player container.

The bundled `default-ai-agent` uses `game_config.seed` to run the existing Nim
role-based scripted AI in a deterministic local mirror, then sends its selected
slot action back over this same protocol.

Players respond with one action:

```json
{"type": "action", "action": 11}
```

The action is encoded as `verb * 8 + argument`. Verbs are `0=noop`, `1=move`,
`2=attack`, `3=use`, `4=swap`, `5=give`, `6=plant_lantern`, and
`7=plant_resource`. Arguments are the eight directions in engine order:
`N`, `S`, `W`, `E`, `NW`, `NE`, `SW`, `SE`.
