# Villager - the bundled Tribal Village scripted-AI player

Villager is the native Nim tournament player for Tribal Village. It links the
game's own `src/environment.nim` and `src/ai.nim`, keeps a deterministic local
mirror of the episode seeded from the first observation, and replays the
built-in role-based scripted AI for its slot over the Coworld `/player`
WebSocket. It is the same policy you watch when running the desktop game.

The layout and Docker build follow the Crewrift `notsus` player: a two-stage
Debian image that installs Nim via nimby in the build stage and ships a single
static-ish binary in the run stage.

Run one player against a local server:

```sh
COWORLD_PLAYER_WS_URL='ws://127.0.0.1:8080/player?slot=0&token=token-0' \
nim r players/villager/villager.nim
```

Build the player image (also built by `coworld build` via `compose.yaml`):

```sh
docker buildx build --platform linux/amd64 \
  -f players/villager/Dockerfile \
  -t coworld-tribal-village-player:latest --load .
```

How it works:

- The server's first observation carries `game_config.seed` and `max_steps`.
  The player builds a local `Environment` with that config and resets it,
  matching the server's own environment construction exactly.
- Each observation for tick T catches the mirror up (`while currentStep < T`),
  computes the 48-agent action vector from the built-in AI controller, sends
  this slot's action as `{"type": "action", "action": N}`, and steps the
  mirror.
- Because every slot runs the same deterministic mirror, the merged action
  vector the server applies equals each mirror's prediction and the mirrors
  stay in lockstep with the server.
- The server re-sends the current tick on every (re)connect; duplicate
  observations replay the cached action instead of advancing the mirror.

If docs, commands, runtime behavior, logs, or replays disagree while you use
this player as a starting point, preserve the evidence and file an issue at
<https://github.com/Metta-AI/coworld/issues> with the command, league/Coworld
ids, logs or replay links, and the smallest repro.
