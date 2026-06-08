## Ultra-Fast Direct Buffer Interface
## Zero-copy numpy buffer communication - no conversions

import std/tables
import vmath
import ai
import environment, external_actions

type
  ## C-compatible environment config passed from Python.
  ## Use NaN for float fields (or <=0 for maxSteps) to keep Nim defaults.
  CEnvironmentConfig* = object
    maxSteps*: int32
    seed*: int32
    tumorSpawnRate*: float32
    heartReward*: float32
    oreReward*: float32
    batteryReward*: float32
    woodReward*: float32
    waterReward*: float32
    wheatReward*: float32
    spearReward*: float32
    armorReward*: float32
    foodReward*: float32
    clothReward*: float32
    tumorKillReward*: float32
    survivalPenalty*: float32
    deathPenalty*: float32

proc isNan32(x: float32): bool {.inline.} =
  x != x

proc applyConfig(cfg: CEnvironmentConfig): EnvironmentConfig =
  result = defaultEnvironmentConfig()
  if cfg.maxSteps > 0:
    result.maxSteps = cfg.maxSteps.int
  if cfg.seed > 0:
    result.seed = cfg.seed.int

  template applyFloat(field: untyped, value: float32) =
    if not isNan32(value):
      result.field = value.float

  applyFloat(tumorSpawnRate, cfg.tumorSpawnRate)
  applyFloat(heartReward, cfg.heartReward)
  applyFloat(oreReward, cfg.oreReward)
  applyFloat(batteryReward, cfg.batteryReward)
  applyFloat(woodReward, cfg.woodReward)
  applyFloat(waterReward, cfg.waterReward)
  applyFloat(wheatReward, cfg.wheatReward)
  applyFloat(spearReward, cfg.spearReward)
  applyFloat(armorReward, cfg.armorReward)
  applyFloat(foodReward, cfg.foodReward)
  applyFloat(clothReward, cfg.clothReward)
  applyFloat(tumorKillReward, cfg.tumorKillReward)
  applyFloat(survivalPenalty, cfg.survivalPenalty)
  applyFloat(deathPenalty, cfg.deathPenalty)

var globalEnv: Environment = nil
var environmentsByPtr = initTable[pointer, Environment]()
var coworldBuiltinAiByEnv = initTable[pointer, Controller]()

proc environmentFromPointer(env: pointer): Environment =
  if env.isNil or env notin environmentsByPtr:
    return nil
  result = environmentsByPtr[env]

const thingRenderColors: array[ThingKind, tuple[r, g, b: uint8]] = [
  # Matches previous hardcoded RGB choices for renderer export.
  (r: 255'u8, g: 255'u8, b: 0'u8),    # Agent
  (r: 96'u8,  g: 96'u8,  b: 96'u8),   # Wall
  (r: 184'u8, g: 134'u8, b: 11'u8),   # Mine
  (r: 0'u8,   g: 200'u8, b: 200'u8),  # Converter
  (r: 220'u8, g: 0'u8,   b: 220'u8),  # assembler
  (r: 255'u8, g: 170'u8, b: 0'u8),    # Spawner
  (r: 160'u8, g: 32'u8,  b: 240'u8),  # Tumor
  (r: 255'u8, g: 120'u8, b: 40'u8),   # Armory
  (r: 255'u8, g: 80'u8,  b: 0'u8),    # Forge
  (r: 255'u8, g: 180'u8, b: 120'u8),  # ClayOven
  (r: 0'u8,   g: 180'u8, b: 255'u8),  # WeavingLoom
  (r: 255'u8, g: 240'u8, b: 128'u8)   # PlantedLantern
]

const CoworldCellStride* = 28
const CoworldNoThing* = 255'u8

proc toByte(value: float32): uint8 =
  var iv = int(value * 255.0)
  if iv < 0:
    iv = 0
  elif iv > 255:
    iv = 255
  result = uint8(iv)

proc toCountByte(value: int): uint8 =
  if value <= 0:
    return 0'u8
  if value >= 255:
    return 255'u8
  result = uint8(value)

proc tribal_village_create(): pointer {.exportc, dynlib.} =
  ## Create environment for direct buffer interface
  try:
    let config = defaultEnvironmentConfig()
    let env = newEnvironment(config)
    let envPtr = cast[pointer](env)
    environmentsByPtr[envPtr] = env
    globalEnv = env
    return envPtr
  except:
    return nil

proc tribal_village_set_config(
  env: pointer,
  cfg: ptr CEnvironmentConfig
): int32 {.exportc, dynlib.} =
  ## Update runtime config (rewards, spawn rates, max steps) from Python.
  let envObj = environmentFromPointer(env)
  if envObj == nil or cfg.isNil:
    return 0
  try:
    envObj.config = applyConfig(cfg[])
    return 1
  except:
    return 0

proc tribal_village_reset_and_get_obs(
  env: pointer,
  obs_buffer: ptr UncheckedArray[uint8],    # [60, 21, 11, 11] direct
  rewards_buffer: ptr UncheckedArray[float32],
  terminals_buffer: ptr UncheckedArray[uint8],
  truncations_buffer: ptr UncheckedArray[uint8]
): int32 {.exportc, dynlib.} =
  ## Reset and write directly to buffers - no conversions
  let envObj = environmentFromPointer(env)
  if envObj == nil:
    return 0

  try:
    envObj.reset()
    if not envObj.observationsInitialized:
      envObj.rebuildObservations()

    # Direct memory copy of observations (zero conversion)
    let obs_size = MapAgents * ObservationLayers * ObservationWidth * ObservationHeight
    copyMem(obs_buffer, envObj.observations.addr, obs_size)

    # Clear rewards/terminals/truncations
    for i in 0..<MapAgents:
      rewards_buffer[i] = 0.0
      terminals_buffer[i] = 0
      truncations_buffer[i] = 0

    return 1
  except:
    return 0

proc tribal_village_reset_for_coworld(
  env: pointer,
  rewards_buffer: ptr UncheckedArray[float32],
  terminals_buffer: ptr UncheckedArray[uint8],
  truncations_buffer: ptr UncheckedArray[uint8]
): int32 {.exportc, dynlib.} =
  ## Reset for Coworld runtime without exporting neural observation tensors.
  let envObj = environmentFromPointer(env)
  if envObj == nil:
    return 0

  try:
    envObj.reset()
    for i in 0..<MapAgents:
      rewards_buffer[i] = 0.0
      terminals_buffer[i] = 0
      truncations_buffer[i] = 0
    return 1
  except:
    return 0

proc tribal_village_step_with_pointers(
  env: pointer,
  actions_buffer: ptr UncheckedArray[uint8],    # [MapAgents] direct read
  obs_buffer: ptr UncheckedArray[uint8],        # [60, 21, 11, 11] direct write
  rewards_buffer: ptr UncheckedArray[float32],
  terminals_buffer: ptr UncheckedArray[uint8],
  truncations_buffer: ptr UncheckedArray[uint8]
): int32 {.exportc, dynlib.} =
  ## Ultra-fast step with direct buffer access
  let envObj = environmentFromPointer(env)
  if envObj == nil:
    return 0

  try:
    # Read actions directly from buffer (no conversion)
    var actions: array[MapAgents, uint8]
    for i in 0..<MapAgents:
      actions[i] = actions_buffer[i]

    # Step environment
    envObj.step(unsafeAddr actions)

    # Direct memory copy of observations (zero conversion overhead)
    let obs_size = MapAgents * ObservationLayers * ObservationWidth * ObservationHeight
    copyMem(obs_buffer, envObj.observations.addr, obs_size)

    # Direct buffer writes (no dict conversion)
    for i in 0..<MapAgents:
      let agent = (if i < envObj.agents.len: envObj.agents[i] else: nil)
      let reward = if agent.isNil: 0.0'f32 else: agent.reward
      rewards_buffer[i] = reward
      if not agent.isNil:
        agent.reward = 0.0'f32
      terminals_buffer[i] = if envObj.terminated[i] > 0.0: 1 else: 0
      truncations_buffer[i] = if envObj.truncated[i] > 0.0: 1 else: 0

    return 1
  except:
    return 0

proc tribal_village_step_for_coworld(
  env: pointer,
  actions_buffer: ptr UncheckedArray[uint8],
  rewards_buffer: ptr UncheckedArray[float32],
  terminals_buffer: ptr UncheckedArray[uint8],
  truncations_buffer: ptr UncheckedArray[uint8]
): int32 {.exportc, dynlib.} =
  ## Step for Coworld runtime without copying observation tensors.
  let envObj = environmentFromPointer(env)
  if envObj == nil:
    return 0

  try:
    var actions: array[MapAgents, uint8]
    for i in 0..<MapAgents:
      actions[i] = actions_buffer[i]

    envObj.step(unsafeAddr actions)

    for i in 0..<MapAgents:
      let agent = (if i < envObj.agents.len: envObj.agents[i] else: nil)
      let reward = if agent.isNil: 0.0'f32 else: agent.reward
      rewards_buffer[i] = reward
      if not agent.isNil:
        agent.reward = 0.0'f32
      terminals_buffer[i] = if envObj.terminated[i] > 0.0: 1 else: 0
      truncations_buffer[i] = if envObj.truncated[i] > 0.0: 1 else: 0

    return 1
  except:
    return 0

proc tribal_village_reset_builtin_ai(
  env: pointer,
  seed: int32
): int32 {.exportc, dynlib.} =
  ## Reset the bundled scripted AI used by Coworld player containers.
  let envObj = environmentFromPointer(env)
  if envObj == nil:
    return 0
  try:
    let controllerSeed = if seed > 0: seed.int else: 1
    coworldBuiltinAiByEnv[env] = newController(controllerSeed)
    return 1
  except:
    return 0

proc tribal_village_builtin_ai_actions(
  env: pointer,
  actions_buffer: ptr UncheckedArray[uint8]
): int32 {.exportc, dynlib.} =
  ## Compute one full 48-agent action vector from the existing Nim AI.
  let envObj = environmentFromPointer(env)
  if envObj == nil or actions_buffer.isNil:
    return 0
  try:
    if env notin coworldBuiltinAiByEnv:
      coworldBuiltinAiByEnv[env] = newController(1)
    let coworldBuiltinAi = coworldBuiltinAiByEnv[env]
    for i in 0..<MapAgents:
      actions_buffer[i] = coworldBuiltinAi.decideAction(envObj, i)
    coworldBuiltinAi.updateController()
    return 1
  except:
    return 0

proc tribal_village_get_num_agents(): int32 {.exportc, dynlib.} =
  return MapAgents.int32

proc tribal_village_get_obs_layers(): int32 {.exportc, dynlib.} =
  return ObservationLayers.int32

proc tribal_village_get_obs_width(): int32 {.exportc, dynlib.} =
  return ObservationWidth.int32


proc tribal_village_get_map_width(): int32 {.exportc, dynlib.} =
  return MapWidth.int32

proc tribal_village_get_map_height(): int32 {.exportc, dynlib.} =
  return MapHeight.int32

proc tribal_village_get_agent_x(
  env: pointer,
  agent_id: int32
): int32 {.exportc, dynlib.} =
  let idx = agent_id.int
  let envObj = environmentFromPointer(env)
  if envObj == nil or idx < 0 or idx >= envObj.agents.len:
    return -1
  return envObj.agents[idx].pos.x

proc tribal_village_get_agent_y(
  env: pointer,
  agent_id: int32
): int32 {.exportc, dynlib.} =
  let idx = agent_id.int
  let envObj = environmentFromPointer(env)
  if envObj == nil or idx < 0 or idx >= envObj.agents.len:
    return -1
  return envObj.agents[idx].pos.y

# Export compact Coworld cell state for sprite-based browser clients.
proc tribal_village_export_world_cells(
  env: pointer,
  out_buffer: ptr UncheckedArray[uint8],
  out_len: int32
): int32 {.exportc, dynlib.} =
  let envObj = environmentFromPointer(env)
  if envObj == nil or out_buffer.isNil:
    return 0

  let required = MapWidth * MapHeight * CoworldCellStride
  if out_len.int < required:
    return 0

  for y in 0 ..< MapHeight:
    for x in 0 ..< MapWidth:
      let idx = (y * MapWidth + x) * CoworldCellStride
      let tileColor = envObj.tileColors[x][y]
      let finalR = min(tileColor.r * tileColor.intensity, 1.5'f32)
      let finalG = min(tileColor.g * tileColor.intensity, 1.5'f32)
      let finalB = min(tileColor.b * tileColor.intensity, 1.5'f32)

      out_buffer[idx] = ord(envObj.terrain[x][y]).uint8
      out_buffer[idx + 1] = toByte(finalR)
      out_buffer[idx + 2] = toByte(finalG)
      out_buffer[idx + 3] = toByte(finalB)
      out_buffer[idx + 4] = CoworldNoThing
      out_buffer[idx + 5] = 0'u8
      out_buffer[idx + 6] = CoworldNoThing
      out_buffer[idx + 7] = CoworldNoThing
      out_buffer[idx + 8] = 0'u8
      out_buffer[idx + 9] = 0'u8
      out_buffer[idx + 10] = 0'u8
      out_buffer[idx + 11] = 0'u8
      out_buffer[idx + 12] = 0'u8
      out_buffer[idx + 13] = 0'u8
      out_buffer[idx + 14] = 0'u8
      out_buffer[idx + 15] = 0'u8
      out_buffer[idx + 16] = 0'u8
      out_buffer[idx + 17] = 0'u8
      out_buffer[idx + 18] = 0'u8
      out_buffer[idx + 19] = 0'u8
      out_buffer[idx + 20] = 0'u8
      out_buffer[idx + 21] = 0'u8
      out_buffer[idx + 22] = 0'u8
      out_buffer[idx + 23] = 0'u8
      out_buffer[idx + 24] = 0'u8
      out_buffer[idx + 25] = 0'u8
      out_buffer[idx + 26] = 0'u8
      out_buffer[idx + 27] = 0'u8

      var flags = 0'u8
      if envObj.actionTintCountdown[x][y] > 0:
        let actionTint = envObj.actionTintColor[x][y]
        flags = flags or 4'u8
        out_buffer[idx + 23] = toByte(actionTint.r)
        out_buffer[idx + 24] = toByte(actionTint.g)
        out_buffer[idx + 25] = toByte(actionTint.b)
        out_buffer[idx + 26] = toByte(actionTint.intensity)

      let thing = envObj.grid[x][y]
      if thing != nil:
        out_buffer[idx + 4] = ord(thing.kind).uint8
        out_buffer[idx + 5] = ord(thing.orientation).uint8
        out_buffer[idx + 8] = toCountByte(thing.hp)
        out_buffer[idx + 9] = toCountByte(thing.maxHp)
        out_buffer[idx + 19] =
          case thing.kind
          of assembler:
            toCountByte(thing.hearts)
          of Mine:
            toCountByte(thing.resources)
          else:
            0'u8
        out_buffer[idx + 20] = toCountByte(thing.cooldown)
        out_buffer[idx + 21] = toCountByte(thing.frozen)

        if thing.hasClaimedTerritory:
          flags = flags or 1'u8
        if thing.lanternHealthy:
          flags = flags or 2'u8

        if thing.kind == Agent:
          out_buffer[idx + 6] = toCountByte(thing.agentId)
          out_buffer[idx + 7] = toCountByte(getTeamId(thing.agentId))
          out_buffer[idx + 10] = toCountByte(thing.inventoryOre)
          out_buffer[idx + 11] = toCountByte(thing.inventoryBattery)
          out_buffer[idx + 12] = toCountByte(thing.inventoryWater)
          out_buffer[idx + 13] = toCountByte(thing.inventoryWheat)
          out_buffer[idx + 14] = toCountByte(thing.inventoryWood)
          out_buffer[idx + 15] = toCountByte(thing.inventorySpear)
          out_buffer[idx + 16] = toCountByte(thing.inventoryLantern)
          out_buffer[idx + 17] = toCountByte(thing.inventoryArmor)
          out_buffer[idx + 18] = toCountByte(thing.inventoryBread)
        elif thing.kind == PlantedLantern:
          out_buffer[idx + 7] = toCountByte(thing.teamId)
      out_buffer[idx + 22] = flags

  return 1

proc tribal_village_render_rgb(
  env: pointer,
  out_buffer: ptr UncheckedArray[uint8],
  out_w: int32,
  out_h: int32
): int32 {.exportc, dynlib.} =
  let envObj = environmentFromPointer(env)
  if envObj == nil or out_buffer.isNil:
    return 0

  let width = int(out_w)
  let height = int(out_h)
  if width <= 0 or height <= 0:
    return 0
  if width mod MapWidth != 0 or height mod MapHeight != 0:
    return 0

  let scaleX = width div MapWidth
  let scaleY = height div MapHeight
  let stride = width * 3

  try:
    for y in 0 ..< MapHeight:
      for sy in 0 ..< scaleY:
        let rowBase = (y * scaleY + sy) * stride
        for x in 0 ..< MapWidth:
          var rByte = toByte(envObj.tileColors[x][y].r)
          var gByte = toByte(envObj.tileColors[x][y].g)
          var bByte = toByte(envObj.tileColors[x][y].b)

          let thing = envObj.grid[x][y]
          if thing != nil:
            let tint = thingRenderColors[thing.kind]
            rByte = tint.r
            gByte = tint.g
            bByte = tint.b

          let xBase = rowBase + x * scaleX * 3
          for sx in 0 ..< scaleX:
            let idx = xBase + sx * 3
            out_buffer[idx] = rByte
            out_buffer[idx + 1] = gByte
            out_buffer[idx + 2] = bByte
    return 1
  except:
    return 0
proc tribal_village_get_obs_height(): int32 {.exportc, dynlib.} =
  return ObservationHeight.int32

proc tribal_village_destroy(env: pointer) {.exportc, dynlib.} =
  ## Clean up environment
  if env in coworldBuiltinAiByEnv:
    coworldBuiltinAiByEnv.del(env)
  if env in environmentsByPtr:
    environmentsByPtr.del(env)
  if globalEnv != nil and cast[pointer](globalEnv) == env:
    globalEnv = nil

# --- Rendering interface (ANSI) ---
proc tribal_village_render_ansi(
  env: pointer,
  out_buffer: ptr UncheckedArray[char],
  buf_len: int32
): int32 {.exportc, dynlib.} =
  ## Write an ANSI string render into out_buffer (null-terminated).
  ## Returns number of bytes written (excluding terminator). 0 on error.
  let envObj = environmentFromPointer(env)
  if envObj == nil or out_buffer.isNil or buf_len <= 1:
    return 0

  try:
    let s = render(envObj)  # environment.render*(env: Environment): string
    let n = min(s.len, max(0, buf_len - 1).int)
    if n > 0:
      copyMem(out_buffer, cast[pointer](s.cstring), n)
    out_buffer[n] = '\0'  # null-terminate
    return n.int32
  except:
    return 0
