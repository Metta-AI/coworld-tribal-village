# Tribal Village Environment

Multi‑agent RL playground in Nim with a Python wrapper (PufferLib compatible). 48 agents (8 teams, 6 per team) compete for
resources while hostile tumors spread a freezing “clippy” tint across the map. Code: <https://github.com/Metta-AI/coworld-tribal-village>

<img width="2932" height="1578" alt="image" src="https://github.com/user-attachments/assets/b1736191-ff85-48fa-b5cf-f47e441fd118" />

## Quick Start (prioritized)

**You’ll need**: Nim 2.2.10+ (via nimby), Python 3.12.x, `pip`, OpenGL libs.

1. Install Nim with nimby + sync deps

```bash
curl -L https://github.com/treeform/nimby/releases/download/0.1.27/nimby-macOS-ARM64 -o ./nimby
chmod +x ./nimby
./nimby use 2.2.10
./nimby sync -g nimby.lock
```

2. Install Python wrapper (editable) + quick smoke test

```bash
pip install -e .
python -c "import tribal_village_env; print('import ok')"
```

3. Play via CLI (builds/refreshes the Nim lib if missing)

```bash
tribal-village play
# this play command actually runs: nim r -d:release tribal_village.nim
# Space toggles play/pause; when paused, press Space to step once
```

4. Train integration status

CoGames has been retired upstream in favor of Coworld. The legacy train command is disabled unless a compatible local
training stack is present.

## Coworld

Tribal Village now ships a Coworld package surface with 48 player slots, one slot per agent. Build and run it with the
current `coworld` CLI from the Metta repository:

```bash
uv run coworld build compose.yaml coworld_manifest_template.json 0.1.0 tmp/tribal_village/coworld_manifest.json
uv run coworld certify tmp/tribal_village/coworld_manifest.json
uv run coworld play tmp/tribal_village/coworld_manifest.json
```

The game image serves `/client/global`, `/client/player?slot=0&token=...`, and `/client/replay`. Player containers read
`COWORLD_PLAYER_WS_URL`, receive JSON action observations, and send one discrete action in `0..63`. Live and replay
visuals use the canonical full-world sprite-cell stream on `/global` and `/replay`. The bundled `default-ai-agent`
player uses the existing Nim role-based scripted AI in a deterministic local mirror and still communicates through the
normal `/player` WebSocket route.

Replay mode is the same image with `COGAME_LOAD_REPLAY_URI` set. `/client/replay` autoplays, loops back to tick 0,
draws `#slot name` labels above agents, and supports the standard faster/slower controls. Replay artifacts are compact
JSON: an initial seed/config plus base64-encoded per-tick action deltas, not rendered frame dumps.

When docs, commands, runtime behavior, logs, or replays disagree while you are
building or submitting a Tribal Village policy, preserve the evidence and file
an issue in the Coworld repo: <https://github.com/Metta-AI/coworld/issues>.
Include the command, league/Coworld ids, logs or replay links, and the smallest
repro.

## Configuration (Python)

Pass a config dict to the Python wrapper (rendering + gameplay tuning):

```python
config = {
    'max_steps': 1000,          # Episode length (Python-side truncation)
    'seed': 1,                  # Optional deterministic map seed; 0/random by default
    'render_mode': 'rgb_array', # or 'ansi'
    'render_scale': 4,          # RGB scale factor (full-map render)
    'ansi_buffer_size': 1_000_000,
    # Nim gameplay tuning (optional)
    'tumor_spawn_rate': 0.1,
    'heart_reward': 1.0,
    'ore_reward': 0.1,
    'battery_reward': 0.8,
    'wood_reward': 0.0,
    'water_reward': 0.0,
    'wheat_reward': 0.0,
    'spear_reward': 0.0,
    'armor_reward': 0.0,
    'food_reward': 0.0,
    'cloth_reward': 0.0,
    'tumor_kill_reward': 0.0,
    'survival_penalty': -0.01,
    'death_penalty': -5.0,
}
env = TribalVillageEnv(config=config)
```
These gameplay settings map to `EnvironmentConfig` in `src/environment.nim`.

## Game Overview

- Map: 192x108 grid, procedural rivers/fields/trees.
- Agents: 48 agents (8 teams, 6 per team).
- Resources: ore, batteries, water, wheat, wood, spears, lanterns, armor, bread.
- Threats: tumors spread dark clippy tint; frozen tiles/objects cannot be harvested or used until thawed.
- Coalition touches we enjoyed while building it:
  - Territory control via lanterns
  - Tiny async loops (e.g., craft 5x armor from wood and hand off to teammates)
  - Tank / DPS / healer roles that synergize in combat
  - Hearts power respawns for your squad

### Core Gameplay Loop

1. **Gather** resources (mine ore, harvest wheat, chop wood, collect water)
2. **Craft** items using specialized buildings (forge spears, weave lanterns, etc.)
3. **Cooperate** within teams and compete across teams
4. **Defend** against tumors using crafted spears

## Controls

**Select**: click agent  
**Move**: Arrow keys / WASD (cardinal), QEZC (diagonal)  
**Act**: U (use/craft in facing direction)  
**Global**: Space (play/pause + step when paused), `-`/`=` or `[`/`]` (speed), N/M (cycle observation overlays), mouse drag (pan), scroll (zoom)

## Technical Details

### Observation Space

21 layers, 11x11 grid per agent:

- **Layer 0**: Team-aware agent presence (1..8=teams, 255=Tumor)
- **Layers 1-9**: Agent orientation + inventories (ore, battery, water, wheat, wood, spear, lantern, armor)
- **Layers 10-18**: Walls/mines/converters/assemblers + ready/resource status
- **Layers 19-20**: Action tint (combat/heal/freeze) + bread inventory

### Action Space

Discrete 64 (`verb * 8 + argument`), where the argument is a direction (0..7):

- **Directions**: N/S/E/W + diagonals
- **Verbs**: 0=noop, 1=move, 2=attack, 3=use/craft, 4=swap, 5=give, 6=plant lantern, 7=plant wheat/tree

### Architecture

- **Nim backend**: High-performance simulation and rendering
- **Python wrapper**: PufferLib-compatible interface for all 48 agents
- **Zero-copy communication**: Direct pointer passing for efficiency
- **Web ready**: Emscripten support for WASM deployment

## Build

- Native shared library for Python: `nim c --app:lib ... src/tribal_village_interface.nim` (see Quick Start step 3)
- Native desktop viewer: `nim r -d:release tribal_village.nim`
- WebAssembly demo (requires Emscripten): command in `scripts/` section below; outputs `build/web/tribal_village.html`

### PufferLib Rendering

- Python bindings default to `render_mode="rgb_array"` and stream full-map RGB frames via Nim.
- Adjust `render_scale` in the env config (default 4) to control output resolution.
- Set `render_mode="ansi"` for lightweight terminal output.

## Files

**Core**: `tribal_village.nim` (entry), `src/environment.nim` (simulation), `src/ai.nim` (built-ins)  
**Rendering**: `src/renderer.nim`, `data/` (sprites/fonts/UI)  
**Integration**: `src/tribal_village_interface.nim` (C interface), `tribal_village_env/` (Python wrapper + CLI)  
**Build**: `nimby.lock`, `tribal_village.nimble`, `pyproject.toml`

## Dependencies

**Nim**: 2.2.10+ with boxy, windy, vmath, chroma (installed via `nimby sync -g nimby.lock`)

**Python**: 3.12.x with numpy. Install `.[pufferlib]` only when using the legacy PufferLib training wrapper.

**System**: OpenGL for rendering
