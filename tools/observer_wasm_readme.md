# Native/WASM public observer parity

The headless probe executes the production public C interface in both native and
compiled WASM binaries. Node runs the WASM; there is no browser or GUI. It does
not replace the simulation, modify game rules, or export player observation
contents or training state.

`tests/public_probe_interface.nim` parses the original interface at compile time
and removes only `exportc`/`dynlib` visibility from functions outside the public
observer API. Function bodies and types are unchanged. This is necessary because
Nim's `dynlib` declarations retain exports even when Emscripten's
`EXPORTED_FUNCTIONS` list is narrower. This filter affects the experimental probe
only; the production native ABI is unchanged. The test checks the actual WASM
export table for private exports.

Use the existing Nim 2.2.10 compiler, the exact packages in `nimby.lock`, and an
already installed Emscripten toolchain. The executed proof used Emscripten 4.0.13
and Node 22.16.0 with a frozen cache. Do not install or update shared packages to
run this experiment. Supply each locked package's `src` directory as a Nim
`--path` argument, plus this repository's `src` directory.

Both compile commands use these common arguments:

```text
nim c --parallelBuild:1 --threads:off --mm:arc -d:release
  --skipUserCfg:on --skipParentCfg:on <locked --path arguments>
  --nimcache:<separate target cache> --out:<target output>
  tests/observer_public_probe.nim
```

For WASM, add the following arguments before the source filename. Set `EM_CONFIG`
to the existing toolchain configuration, with its installed cache frozen, and
set `EMCC_CORES=1` and `EMSDK_NUM_CORES=1`. Use a `.js` output filename.

```text
-d:emscripten --os:linux --cpu:wasm32 --cc:clang
--clang.exe:<emcc> --clang.linkerexe:<emcc>
--exceptions:goto -d:noSignalHandler
--passL:-sENVIRONMENT=node --passL:-sEXIT_RUNTIME=1
--passL:-sNODERAWFS=1 --passL:-sALLOW_MEMORY_GROWTH=1
--passL:-sSTACK_SIZE=8388608 --passL:-sINITIAL_MEMORY=67108864
```

Pass one `--passL:-sEXPORTED_FUNCTIONS=<JSON array>` argument naming `_main`,
`_malloc`, `_free`, and these `_tribal_village_` functions: `create`, `set_config`,
`reset_for_coworld`, `step_for_coworld`, `export_world_cells`, `destroy`,
`get_num_agents`, `get_map_width`, `get_map_height`. `_malloc` is required by the
existing Windy platform helper even in the headless build. No window is created.

Run each compile and the following test command serially through the host's
normal CPU FIFO, with one worker, a 2 GiB memory limit, zero swap and finite
runtime bounds. The executed proof used at most 300 seconds per stage and a
15-minute total CPU-stage budget. Supply a **new** output directory to retain
the real replay inputs, public binary frames, commands, exit codes and hashes:

```sh
TRIBAL_NATIVE_PROBE=/path/to/native-probe \
TRIBAL_WASM_PROBE=/path/to/wasm-probe.js \
TRIBAL_NODE=/path/to/node \
TRIBAL_PARITY_OUTPUT=/path/to/new-evidence \
python -m pytest tests/test_observer_wasm_parity.py -v
```

The four predeclared fixtures use seeds 17 and 52, two/eight teams and 64 ticks.
Native built-in AI records the real action-delta replay once; both binaries read
that same input. Every public byte is compared at ticks 0–64, after explicit
reset, and at controlled saturation boundaries. Both outputs also pass through
the original `ObserverSnapshot` adapter. Tick/reward/terminal traces, entity IDs,
team assignments, config layout, output canaries, invalid handles and private
field exclusions are checked. The saturation/private mutations are test-only;
they neither change shipped game rules nor add a hidden-state export.

Malformed replay controls require the specific validation error and no output,
so an unrelated startup crash cannot count as rejection. A deliberately changed
entity ID must fail the comparator. The executed result is exact parity for this
public seam, including its existing uint8 saturation. It is not full hidden-state
parity, browser/input/renderer parity, arbitrary-seed or long-training coverage,
or a replacement RL engine. The original native/frame evidence remains separate.
