# Public observer proof

`observer_episode.py` runs the existing native simulation and writes its public
world snapshot plus the existing action-delta replay. Player observations are
never written to either display artifact. The snapshot preserves all 28 bytes per
tile, including public entity IDs, team IDs, inventories and resource counts.
These counts are the existing saturated uint8 display values, not a new export
of full internal state.

From the repository root, with the native library and Coworld dependencies built:

```sh
python -m pytest tests/test_training_bridge.py tests/test_observer_snapshot.py
python -m tools.observer_episode /tmp/tribal-observer-example --teams 8 --ticks 64
```

The output directory must be new. `observer.json` is an immutable public copy at
one native tick; `replay.json` remains the original replay format. The adapter
does not change simulation code, action timing, player observations or rewards.
Tests compare native tensors and public bytes with observation enabled/disabled,
restore through the shipped replay consumer, and send an action to the spectator
WebSocket to check that it cannot update the player action queue.

`observer_view.nim` is a separate, finite presentation executable. It imports
`polyworld/shapes` from Polyworld commit
`449ad184052567c30fa54c269ef45ff8c9e8e29b`, plus that checkout's pinned Nim
dependencies. Supply their `src` directories as Nim `--path` arguments, and
compile with `nim c --parallelBuild:1 -d:release tools/observer_view.nim`.
It does not link Tribal Village's native simulation. Once the host's graphical
slot is available, run it through the host verification queue:

```sh
LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=1 tools/observer_view \
  /tmp/tribal-observer-example/observer.json /tmp/tribal-observer-example/frame.png
```

It needs an X display on Linux, opens one hidden window, writes one frame and
exits. It draws public terrain colors and entity markers with the shared shape
batcher. The view intentionally does not implement sprite artwork, animation,
input, a live network subscriber or replay controls. Successful execution proves
a detached presentation boundary; it does not establish a replacement RL engine,
browser parity, long-episode determinism or production visual/performance parity.
The separate [native/WASM public observer proof](observer_wasm_readme.md) checks
the compiled headless public seam without rerunning this frame experiment.
