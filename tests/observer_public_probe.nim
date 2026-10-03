## Execute the shipped public C interface identically in native and WASM builds.
## Controlled saturation/private-field mutations exist only in this test binary.
import public_probe_interface
publicProbeInterface()
import std/[base64, json, os, strutils]

proc require(ok: bool, message: string) =
  if not ok:
    raise newException(ValueError, message)

proc configured(seed, teams: int): pointer =
  result = tribal_village_create()
  require(result != nil, "create failed")
  var cfg = CEnvironmentConfig(maxSteps: 64, seed: seed.int32,
    teamCount: teams.int32)
  for field in [addr cfg.tumorSpawnRate, addr cfg.heartReward,
      addr cfg.oreReward, addr cfg.batteryReward, addr cfg.woodReward,
      addr cfg.waterReward,
      addr cfg.wheatReward, addr cfg.spearReward, addr cfg.armorReward,
      addr cfg.foodReward, addr cfg.clothReward, addr cfg.tumorKillReward,
      addr cfg.survivalPenalty, addr cfg.deathPenalty]:
    field[] = NaN.float32
  require(tribal_village_set_config(result, addr cfg) == 1, "config failed")

proc frame(env: pointer): string =
  result = newString(MapWidth * MapHeight * CoworldCellStride)
  require(tribal_village_export_world_cells(env,
    cast[ptr UncheckedArray[uint8]](addr result[0]), result.len.int32) == 1,
    "public export failed")

proc resetPublic(env: pointer) =
  var rewards: array[MapAgents, float32]
  var terminals, truncations: array[MapAgents, uint8]
  require(tribal_village_reset_for_coworld(env,
    cast[ptr UncheckedArray[float32]](addr rewards[0]),
    cast[ptr UncheckedArray[uint8]](addr terminals[0]),
    cast[ptr UncheckedArray[uint8]](addr truncations[0])) == 1, "reset failed")
  require(rewards == default(typeof(rewards)) and
    terminals == default(typeof(terminals)) and
    truncations == default(typeof(truncations)), "reset outputs not cleared")

proc record(seed, teams: int, path: string) =
  let env = configured(seed, teams)
  defer: tribal_village_destroy(env)
  resetPublic(env)
  require(tribal_village_reset_builtin_ai(env, seed.int32) == 1, "AI reset failed")
  var ticks = newJArray()
  for tick in 0 ..< 64:
    var actions: array[MapAgents, uint8]
    var rewards: array[MapAgents, float32]
    var terminals, truncations: array[MapAgents, uint8]
    require(tribal_village_builtin_ai_actions(env,
      cast[ptr UncheckedArray[uint8]](addr actions[0])) == 1, "AI failed")
    var wire = newString(teams * 6)
    for i in 0 ..< wire.len: wire[i] = actions[i].char
    ticks.add(%*{"a": encode(wire)})
    require(tribal_village_step_for_coworld(env,
      cast[ptr UncheckedArray[uint8]](addr actions[0]),
      cast[ptr UncheckedArray[float32]](addr rewards[0]),
      cast[ptr UncheckedArray[uint8]](addr terminals[0]),
      cast[ptr UncheckedArray[uint8]](addr truncations[0])) == 1, "step failed")
  var players: seq[string]
  for i in 0 ..< teams * 6: players.add("Player " & $i)
  writeFile(path, $(%*{"schema": "tribal-village-replay-v2",
    "initial": {"seed": seed, "team_count": teams, "max_steps": 64,
      "tick_rate": 30, "players": players}, "ticks": ticks, "results": {}}))

proc replay(path, output: string) =
  let data = parseFile(path)
  require(data["schema"].getStr == "tribal-village-replay-v2", "invalid schema")
  let seed = data["initial"]["seed"].getInt
  let teams = data["initial"]["team_count"].getInt
  require(seed > 0 and seed <= high(int32).int, "invalid seed")
  require(teams in [2, 8], "fixture roster must be two or eight teams")
  require(data["initial"]["max_steps"].getInt == 64 and
    data["ticks"].len == 64, "invalid replay boundary")
  var inputs: seq[array[MapAgents, uint8]]
  for row in data["ticks"]:
    let wire = decode(row["a"].getStr)
    require(wire.len == teams * 6, "invalid action roster")
    var actions: array[MapAgents, uint8]
    for i, action in wire:
      require(action.ord < 64, "invalid action code")
      actions[i] = action.uint8
    inputs.add(actions)
  require(not dirExists(output), "output already exists")
  createDir(output)
  require(sizeof(CEnvironmentConfig) == 68, "config ABI changed")
  require(tribal_village_get_num_agents() == 48 and
    tribal_village_get_obs_layers() == 26 and
    tribal_village_get_obs_width() == 11 and
    tribal_village_get_obs_height() == 11, "player ABI changed")
  let env = configured(seed, teams)
  defer: tribal_village_destroy(env)
  resetPublic(env)
  let initial = frame(env)
  writeFile(output / "0.bin", initial)
  var trace = newJArray()
  for tick, row in inputs:
    var actions = row
    var rewards: array[MapAgents, float32]
    var terminals, truncations: array[MapAgents, uint8]
    require(tribal_village_step_for_coworld(env,
      cast[ptr UncheckedArray[uint8]](addr actions[0]),
      cast[ptr UncheckedArray[float32]](addr rewards[0]),
      cast[ptr UncheckedArray[uint8]](addr terminals[0]),
      cast[ptr UncheckedArray[uint8]](addr truncations[0])) == 1, "step failed")
    require(environmentFromPointer(env).currentStep == tick + 1, "tick changed")
    for i in 0 ..< teams * 6:
      require(truncations[i] == (if tick == 63 and terminals[i] ==
          0: 1'u8 else: 0'u8),
        "terminal boundary changed")
    writeFile(output / $(tick + 1) & ".bin", frame(env))
    trace.add(%*{"tick": tick + 1, "terminals": terminals,
      "truncations": truncations, "rewards": rewards})
  writeFile(output / "trace.json", $trace)
  resetPublic(env)
  require(frame(env) == initial, "explicit reset changed initial public state")
  writeFile(output / "reset.bin", frame(env))

  # Errors must not write any part of the caller's public buffer.
  var sentinel = newString(initial.len)
  for c in sentinel.mitems: c = '\xA5'
  let untouched = repeat('\xA5', initial.len)
  let buf = cast[ptr UncheckedArray[uint8]](addr sentinel[0])
  for handle in [nil, cast[pointer](1)]:
    require(tribal_village_export_world_cells(handle, buf,
        sentinel.len.int32) == 0,
      "invalid handle accepted")
  require(tribal_village_export_world_cells(env, nil, sentinel.len.int32) == 0,
    "null output accepted")
  for size in [-1'i32, 0'i32, sentinel.len.int32 - 1]:
    require(tribal_village_export_world_cells(env, buf, size) == 0,
      "short output accepted")
  require(sentinel == untouched and frame(env) == initial, "rejection mutated state")
  var guarded = repeat('\xA5', initial.len + 2)
  require(tribal_village_export_world_cells(env,
    cast[ptr UncheckedArray[uint8]](addr guarded[1]), initial.len.int32) == 1,
    "guarded export failed")
  require(guarded[0] == '\xA5' and guarded[^1] == '\xA5' and
    guarded[1 .. ^2] == initial, "export crossed output boundary")
  require(tribal_village_set_config(env, nil) == 0, "null config accepted")
  require(tribal_village_reset_for_coworld(nil, nil, nil, nil) == 0,
    "null reset handle accepted")
  require(tribal_village_step_for_coworld(nil, nil, nil, nil, nil) == 0,
    "null step handle accepted")

  let agent = environmentFromPointer(env).agents[0]
  let offset = (agent.pos.y.int * MapWidth + agent.pos.x.int) * CoworldCellStride
  for index, value in [-1, 0, 254, 255, 256, 300]:
    agent.inventoryOre = value
    let public = frame(env)
    require(public[offset + 10].ord == [0, 0, 254, 255, 255, 255][index],
      "public inventory saturation changed")
    writeFile(output / "saturation-" & $index & ".bin", public)
  let beforePrivate = frame(env)
  agent.reward = 123.5
  environmentFromPointer(env).observations[0][0][0][0] = 231
  require(frame(env) == beforePrivate, "private state leaked into public frame")
  writeFile(output / "private-exclusion.bin", frame(env))
  tribal_village_destroy(env)
  require(tribal_village_export_world_cells(env, buf, sentinel.len.int32) == 0,
    "destroyed handle accepted")
  require(sentinel == untouched, "destroyed handle wrote output")
  writeFile(output / "controls.json", $(%*{"config_bytes": 68,
    "width": MapWidth, "height": MapHeight, "stride": CoworldCellStride,
    "saturation": true, "private_exclusion": true, "invalid_abi": true,
    "reset": true, "terminal_tick": 64}))

when isMainModule:
  if paramCount() == 4 and paramStr(1) == "record":
    record(parseInt(paramStr(2)), parseInt(paramStr(3)), paramStr(4))
  elif paramCount() == 3 and paramStr(1) == "replay":
    replay(paramStr(2), paramStr(3))
  else:
    quit("usage: observer_public_probe record SEED TEAMS FILE | replay FILE DIRECTORY", 2)
