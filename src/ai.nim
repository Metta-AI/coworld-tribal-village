## Simplified AI system - clean and efficient
## Replaces the 1200+ line complex system with ~150 lines
import std/tables
import rng_compat
import vmath
import environment, common

type
  # Simple agent roles - one per team member
  AgentRole* = enum
    Hearter    # Handles assembler/battery workflow
    Armorer    # Wood -> Armor
    Hunter     # Wood -> Spear -> Hunt Tumors
    Baker      # Wheat -> Bread
    Lighter    # Wheat -> Lantern -> Plant
    Farmer     # Creates fertile ground and plants wheat/trees

  # Minimal state tracking with spiral search
  AgentState = object
    role: AgentRole
    # Spiral search state
    spiralStepsInArc: int
    spiralArcsCompleted: int
    basePosition: IVec2
    lastSearchPosition: IVec2
    # Bail-out / anti-oscillation state
    lastPosition: IVec2
    recentPositions: seq[IVec2]
    stuckCounter: int
    escapeMode: bool
    escapeStepsRemaining: int
    escapeDirection: IVec2

  # Simple controller
  Controller* = ref object
    rng*: Rand
    agents: Table[int, AgentState]

proc newController*(seed: int): Controller =
  result = Controller(
    rng: initRand(seed),
    agents: initTable[int, AgentState]()
  )

# Helper proc to save state and return action
proc saveStateAndReturn(controller: Controller, agentId: int, state: AgentState, action: uint8): uint8 =
  controller.agents[agentId] = state
  return action

proc vecToOrientation(vec: IVec2): int =
  ## Map a step vector to orientation index (0..7)
  let x = vec.x
  let y = vec.y
  if x == 0'i32 and y == -1'i32: return 0  # N
  elif x == 0'i32 and y == 1'i32: return 1  # S
  elif x == -1'i32 and y == 0'i32: return 2 # W
  elif x == 1'i32 and y == 0'i32: return 3  # E
  elif x == -1'i32 and y == -1'i32: return 4 # NW
  elif x == 1'i32 and y == -1'i32: return 5  # NE
  elif x == -1'i32 and y == 1'i32: return 6  # SW
  elif x == 1'i32 and y == 1'i32: return 7   # SE
  else: return 0

proc applyDirectionOffset(offset: var IVec2, direction: int, distance: int32) =
  case direction:
  of 0: offset.y -= distance  # North
  of 1: offset.x += distance  # East
  of 2: offset.y += distance  # South
  of 3: offset.x -= distance  # West
  else: discard

proc clampToPlayable(pos: IVec2): IVec2 {.inline.} =
  ## Keep positions inside the playable area (inside border walls).
  result.x = min(MapWidth - MapBorder - 1, max(MapBorder, pos.x))
  result.y = min(MapHeight - MapBorder - 1, max(MapBorder, pos.y))

proc getNextSpiralPoint(state: var AgentState, rng: var Rand): IVec2 =
  ## Generate next position in expanding spiral search pattern
  # Track current position in spiral
  var totalOffset = ivec2(0, 0)
  var currentArcLength = 1
  var direction = 0

  # Rebuild position by simulating all steps up to current point
  for arcNum in 0 ..< state.spiralArcsCompleted:
    let arcLen = (arcNum div 2) + 1  # 1,1,2,2,3,3,4,4...
    let dir = arcNum mod 4  # Direction cycles 0,1,2,3 (N,E,S,W)
    applyDirectionOffset(totalOffset, dir, int32(arcLen))

  # Add partial progress in current arc
  currentArcLength = (state.spiralArcsCompleted div 2) + 1
  direction = state.spiralArcsCompleted mod 4

  # Add steps taken in current arc
  applyDirectionOffset(totalOffset, direction, int32(state.spiralStepsInArc))

  # Calculate next step
  state.spiralStepsInArc += 1

  # Check if we completed the current arc
  if state.spiralStepsInArc > currentArcLength:
    # Move to next arc
    state.spiralArcsCompleted += 1
    state.spiralStepsInArc = 1

    # Reset spiral after ~100 arcs (radius ~50) to avoid going too far
    if state.spiralArcsCompleted > 100:
      state.spiralArcsCompleted = 0  # Reset to start of spiral
      state.spiralStepsInArc = 1
      # Don't return to base immediately, continue spiral from current area
      state.basePosition = state.lastSearchPosition

  # Calculate next position
  applyDirectionOffset(totalOffset, direction, 1)
  result = clampToPlayable(state.basePosition + totalOffset)

proc findNearestThing(env: Environment, pos: IVec2, kind: ThingKind): Thing =
  result = nil
  var minDist = 999999
  for thing in env.things:
    if thing.kind == kind:
      let dist = abs(thing.pos.x - pos.x) + abs(thing.pos.y - pos.y)
      if dist < minDist and dist < 30:  # Reasonable search radius
        minDist = dist
        result = thing

proc findNearestThingSpiral(env: Environment, state: var AgentState, kind: ThingKind, rng: var Rand): Thing =
  ## Find nearest thing using spiral search pattern - more systematic than random search
  # First check immediate area around current position
  result = findNearestThing(env, state.lastSearchPosition, kind)
  if result != nil:
    return result

  # Also check around agent's current position before advancing spiral
  result = findNearestThing(env, state.basePosition, kind)
  if result != nil:
    return result

  # If not found, advance spiral search only every few calls to reduce dithering
  let nextSearchPos = getNextSpiralPoint(state, rng)
  state.lastSearchPosition = nextSearchPos

  # Search from new spiral position
  result = findNearestThing(env, nextSearchPos, kind)
  return result

proc findNearestTerrain(env: Environment, pos: IVec2, terrain: TerrainType): IVec2 =
  result = ivec2(-1, -1)
  var minDist = 999999
  for x in max(0, pos.x - 20)..<min(MapWidth, pos.x + 21):
    for y in max(0, pos.y - 20)..<min(MapHeight, pos.y + 21):
      if env.terrain[x][y] == terrain:
        let terrainPos = ivec2(x.int32, y.int32)
        let dist = abs(terrainPos.x - pos.x) + abs(terrainPos.y - pos.y)
        if dist < minDist:
          minDist = dist
          result = terrainPos

proc findNearestEmpty(env: Environment, pos: IVec2, fertileNeeded: bool, maxRadius: int = 8): IVec2 =
  ## Find nearest empty, non-water tile matching fertile flag
  result = ivec2(-1, -1)
  var minDist = 999999
  let startX = max(0, pos.x - maxRadius)
  let endX = min(MapWidth - 1, pos.x + maxRadius)
  let startY = max(0, pos.y - maxRadius)
  let endY = min(MapHeight - 1, pos.y + maxRadius)
  for x in startX..endX:
    for y in startY..endY:
      let terrainOk = if fertileNeeded: env.terrain[x][y] == Fertile else: env.terrain[x][y] == Empty
      if terrainOk and env.isEmpty(ivec2(x, y)):
        let dist = abs(x - pos.x) + abs(y - pos.y)
        if dist < minDist:
          minDist = dist
          result = ivec2(x.int32, y.int32)

proc countFertileEmpty(env: Environment, center: IVec2, radius: int = 8): int =
  ## Count fertile tiles within Chebyshev radius that are empty and plantable
  let startX = max(0, center.x - radius)
  let endX = min(MapWidth - 1, center.x + radius)
  let startY = max(0, center.y - radius)
  let endY = min(MapHeight - 1, center.y + radius)
  result = 0
  for x in startX..endX:
    for y in startY..endY:
      if env.terrain[x][y] == Fertile and env.isEmpty(ivec2(x, y)):
        inc result

proc findNearestTerrainSpiral(env: Environment, state: var AgentState, terrain: TerrainType, rng: var Rand): IVec2 =
  ## Find terrain using spiral search pattern
  # First check from current spiral search position
  result = findNearestTerrain(env, state.lastSearchPosition, terrain)
  if result.x >= 0:
    return result

  # Also check around agent's current position before advancing spiral
  result = findNearestTerrain(env, state.basePosition, terrain)
  if result.x >= 0:
    return result

  # If not found, advance spiral search
  let nextSearchPos = getNextSpiralPoint(state, rng)
  state.lastSearchPosition = nextSearchPos

  # Search from new spiral position
  result = findNearestTerrain(env, nextSearchPos, terrain)
  return result

proc getCardinalDirIndex(fromPos, toPos: IVec2): int =
  ## Convert direction to orientation (0=N, 1=S, 2=W, 3=E, 4=NW, 5=NE, 6=SW, 7=SE)
  let dx = toPos.x - fromPos.x
  let dy = toPos.y - fromPos.y

  # Handle cardinal directions first (simpler pathfinding)
  if abs(dx) > abs(dy):
    if dx > 0: return 3  # East
    else: return 2       # West
  else:
    if dy > 0: return 1  # South
    else: return 0       # North

proc neighborDirIndex(fromPos, toPos: IVec2): int =
  ## Orientation index (0..7) toward adjacent target (includes diagonals)
  let dx = toPos.x - fromPos.x
  let dy = toPos.y - fromPos.y
  let sx = (if dx > 0: 1'i32 elif dx < 0: -1'i32 else: 0'i32)
  let sy = (if dy > 0: 1'i32 elif dy < 0: -1'i32 else: 0'i32)
  return vecToOrientation(ivec2(sx.int, sy.int))

proc chebyshevDist(a, b: IVec2): int32 =
  let dx = abs(a.x - b.x)
  let dy = abs(a.y - b.y)
  return (if dx > dy: dx else: dy)

proc isValidEmptyTile(env: Environment, pos: IVec2): bool =
  pos.x >= 0 and pos.x < MapWidth and pos.y >= 0 and pos.y < MapHeight and
  env.isEmpty(pos) and env.terrain[pos.x][pos.y] != Water

proc getMoveAway(env: Environment, fromPos, threatPos: IVec2, rng: var Rand): int =
  ## Pick a step that increases distance from the threat (chebyshev), prioritizing empty tiles.
  var best: seq[IVec2] = @[]
  var bestDist = int32(-1)
  for dx in -1 .. 1:
    for dy in -1 .. 1:
      if dx == 0 and dy == 0: continue
      let candidate = fromPos + ivec2(dx.int32, dy.int32)
      if not isValidEmptyTile(env, candidate): continue
      let dist = chebyshevDist(candidate, threatPos)
      if dist > bestDist:
        bestDist = dist
        best.setLen(0)
        best.add(candidate)
      elif dist == bestDist:
        best.add(candidate)
  if best.len == 0:
    return vecToOrientation(ivec2(0, -1))  # fallback north
  let pick = sample(rng, best)
  return vecToOrientation(pick - fromPos)

proc findNearestLantern(env: Environment, pos: IVec2): tuple[pos: IVec2, found: bool, dist: int32] =
  var best = (pos: ivec2(0, 0), found: false, dist: int32.high)
  for t in env.things:
    if t.kind == PlantedLantern:
      let d = chebyshevDist(pos, t.pos)
      if d < best.dist:
        best = (pos: t.pos, found: true, dist: d)
  return best

proc isAdjacentToLantern(env: Environment, agentPos: IVec2): bool =
  for t in env.things:
    if t.kind == PlantedLantern and chebyshevDist(agentPos, t.pos) == 1'i32:
      return true
  return false

proc spearAttackDir(agentPos: IVec2, targetPos: IVec2): int {.inline.} =
  ## Pick an orientation whose spear wedge covers the target (matches attackAction pattern).
  var bestDir = -1
  var bestStep = int.high
  for dirIdx in 0 .. 7:
    let d = getOrientationDelta(Orientation(dirIdx))
    let left = ivec2(-d.y, d.x)
    let right = ivec2(d.y, -d.x)
    for step in 1 .. 3:
      let forward = agentPos + ivec2(d.x * step, d.y * step)
      if forward == targetPos or forward + left == targetPos or forward + right == targetPos:
        if step < bestStep:
          bestStep = step
          bestDir = dirIdx
        break
  return bestDir

proc sameTeam(agentA, agentB: Thing): bool =
  (agentA.agentId div MapAgentsPerHouse) == (agentB.agentId div MapAgentsPerHouse)

proc findAttackOpportunity(env: Environment, agent: Thing): int =
  ## Return attack orientation index if a valid target is in reach, else -1.
  ## Prefer the closest tumor; fall back to spawners or enemy agents if present.
  var bestTumor = (dir: -1, dist: int.high)
  var bestSpawner = (dir: -1, dist: int.high)
  var bestEnemy = (dir: -1, dist: int.high)

  if agent.inventorySpear > 0:
    for thing in env.things:
      if thing.kind notin {Tumor, Spawner, Agent}:
        continue
      # Safety: skip stale things whose grid entry was already cleared (can happen after destruction
      # but before env.things is pruned). Without this, agents may attack an empty tile where the
      # object used to live.
      if thing.pos.x < 0 or thing.pos.x >= MapWidth or thing.pos.y < 0 or thing.pos.y >= MapHeight:
        continue
      if env.grid[thing.pos.x][thing.pos.y] != thing:
        continue
      if thing.kind == Agent:
        if thing.frozen > 0:
          continue
        if sameTeam(agent, thing):
          continue
      let dirIdx = spearAttackDir(agent.pos, thing.pos)
      if dirIdx < 0:
        continue
      let dist = int(chebyshevDist(agent.pos, thing.pos))
      case thing.kind
      of Tumor:
        if dist < bestTumor.dist:
          bestTumor = (dirIdx, dist)
      of Spawner:
        if dist < bestSpawner.dist:
          bestSpawner = (dirIdx, dist)
      of Agent:
        if dist < bestEnemy.dist:
          bestEnemy = (dirIdx, dist)
      else:
        discard

    if bestTumor.dir >= 0: return bestTumor.dir
    if bestSpawner.dir >= 0: return bestSpawner.dir
    if bestEnemy.dir >= 0: return bestEnemy.dir

  # Fallback for non-spear attacks: 1-tile direct neighbors.
  for dirIdx in 0 .. 7:
    let delta = getOrientationDelta(Orientation(dirIdx))
    let targetPos = agent.pos + ivec2(delta.x, delta.y)
    if targetPos.x < 0 or targetPos.x >= MapWidth or
       targetPos.y < 0 or targetPos.y >= MapHeight:
      continue
    let occupant = env.grid[targetPos.x][targetPos.y]
    if occupant == nil:
      continue

    if occupant.kind == Tumor:
      return dirIdx
    elif occupant.kind == Spawner and bestSpawner.dir < 0:
      bestSpawner = (dirIdx, 1)
    elif occupant.kind == Agent and bestEnemy.dir < 0 and occupant.frozen == 0 and not sameTeam(agent, occupant):
      bestEnemy = (dirIdx, 1)

  if bestSpawner.dir >= 0: return bestSpawner.dir
  if bestEnemy.dir >= 0: return bestEnemy.dir
  return -1

type NeedType = enum
  NeedArmor
  NeedBread

proc findNearestTeammateNeeding(env: Environment, me: Thing, need: NeedType): Thing =
  var best: Thing = nil
  var bestDist = int.high
  for other in env.agents:
    if other.agentId == me.agentId: continue
    if not sameTeam(me, other): continue
    var needs = false
    case need
    of NeedArmor:
      needs = other.inventoryArmor == 0
    of NeedBread:
      needs = other.inventoryBread < 1
    if not needs: continue
    let d = int(chebyshevDist(me.pos, other.pos))
    if d < bestDist:
      bestDist = d
      best = other
  return best

proc isPassable(env: Environment, pos: IVec2): bool =
  ## Consider lantern tiles passable for movement planning
  if env.isEmpty(pos): return true
  for t in env.things:
    if t.pos == pos and t.kind == PlantedLantern:
      return true
  return false

proc getMoveTowards(env: Environment, fromPos, toPos: IVec2, rng: var Rand): int =
  ## Get a movement direction towards target, with obstacle avoidance
  let clampedTarget = clampToPlayable(toPos)
  if clampedTarget == fromPos:
    # Target is outside playable bounds; push back inward toward the widest margin.
    let directions = [
      ivec2(0, -1),  # 0: North
      ivec2(0, 1),   # 1: South
      ivec2(-1, 0),  # 2: West
      ivec2(1, 0),   # 3: East
      ivec2(-1, -1), # 4: NW
      ivec2(1, -1),  # 5: NE
      ivec2(-1, 1),  # 6: SW
      ivec2(1, 1)    # 7: SE
    ]
    var bestDir = -1
    var bestMargin = -1
    for idx, d in directions:
      let np = fromPos + d
      if not isPassable(env, np):
        continue
      let marginX = min(np.x - MapBorder, (MapWidth - MapBorder - 1) - np.x)
      let marginY = min(np.y - MapBorder, (MapHeight - MapBorder - 1) - np.y)
      let margin = min(marginX, marginY)
      if margin > bestMargin:
        bestMargin = margin
        bestDir = idx
    if bestDir >= 0:
      return bestDir
    return randIntInclusive(rng, 0, 3)

  let primaryDir = getCardinalDirIndex(fromPos, clampedTarget)

  # Try primary direction first
  let directions = [
    ivec2(0, -1),  # 0: North
    ivec2(0, 1),   # 1: South
    ivec2(-1, 0),  # 2: West
    ivec2(1, 0),   # 3: East
    ivec2(-1, -1), # 4: NW
    ivec2(1, -1),  # 5: NE
    ivec2(-1, 1),  # 6: SW
    ivec2(1, 1)    # 7: SE
  ]

  let primaryMove = fromPos + directions[primaryDir]
  if isPassable(env, primaryMove):
    return primaryDir

  # Primary blocked, try adjacent directions
  let alternatives = case primaryDir:
    of 0: @[5, 4, 1, 3, 2]  # North blocked, try NE, NW, South, East, West
    of 1: @[7, 6, 0, 3, 2]  # South blocked, try SE, SW, North, East, West
    of 2: @[4, 6, 3, 0, 1]  # West blocked, try NW, SW, East, North, South
    of 3: @[5, 7, 2, 0, 1]  # East blocked, try NE, SE, West, North, South
    else: @[0, 1, 2, 3]     # Diagonal blocked, try cardinals

  for altDir in alternatives:
    let altMove = fromPos + directions[altDir]
    if isPassable(env, altMove):
      return altDir

  # All blocked, try random movement
  return randIntInclusive(rng, 0, 3)

proc tryPlantOnFertile(controller: Controller, env: Environment, agent: Thing,
                       agentId: int, state: var AgentState): tuple[did: bool, action: uint8] =
  ## If carrying wood/wheat and a fertile tile is nearby, plant; otherwise move toward it.
  if agent.inventoryWheat > 0 or agent.inventoryWood > 0:
    let fertilePos = findNearestEmpty(env, agent.pos, true)
    if fertilePos.x >= 0:
      let dx = abs(fertilePos.x - agent.pos.x)
      let dy = abs(fertilePos.y - agent.pos.y)
      if max(dx, dy) == 1'i32 and (dx == 0 or dy == 0):
        let dirIdx = getCardinalDirIndex(agent.pos, fertilePos)
        let plantArg = (if agent.inventoryWheat > 0: dirIdx else: dirIdx + 4)
        return (true, saveStateAndReturn(controller, agentId, state,
                 encodeAction(7'u8, plantArg.uint8)))
      else:
        return (true, saveStateAndReturn(controller, agentId, state,
                 encodeAction(1'u8, getMoveTowards(env, agent.pos, fertilePos, controller.rng).uint8)))
  return (false, 0'u8)

proc moveNextSearch(controller: Controller, env: Environment, agent: Thing, agentId: int,
                    state: var AgentState): uint8 =
  let nextSearchPos = getNextSpiralPoint(state, controller.rng)
  return saveStateAndReturn(controller, agentId, state,
    encodeAction(1'u8, getMoveTowards(env, agent.pos, nextSearchPos, controller.rng).uint8))

proc useOrMove(controller: Controller, env: Environment, agent: Thing, agentId: int,
               state: var AgentState, targetPos: IVec2): uint8 =
  let dx = abs(targetPos.x - agent.pos.x)
  let dy = abs(targetPos.y - agent.pos.y)
  if max(dx, dy) == 1'i32:
    return saveStateAndReturn(controller, agentId, state,
      encodeAction(3'u8, neighborDirIndex(agent.pos, targetPos).uint8))
  return saveStateAndReturn(controller, agentId, state,
    encodeAction(1'u8, getMoveTowards(env, agent.pos, targetPos, controller.rng).uint8))

proc findAndUseBuilding(controller: Controller, env: Environment, agent: Thing, agentId: int,
                        state: var AgentState, kind: ThingKind): tuple[did: bool, action: uint8] =
  let b = env.findNearestThingSpiral(state, kind, controller.rng)
  if b != nil:
    return (true, controller.useOrMove(env, agent, agentId, state, b.pos))
  (true, controller.moveNextSearch(env, agent, agentId, state))

proc findAndHarvest(controller: Controller, env: Environment, agent: Thing, agentId: int,
                    state: var AgentState, terrain: TerrainType): tuple[did: bool, action: uint8] =
  let pos = env.findNearestTerrainSpiral(state, terrain, controller.rng)
  if pos.x >= 0:
    return (true, controller.useOrMove(env, agent, agentId, state, pos))
  (true, controller.moveNextSearch(env, agent, agentId, state))


proc decideAction*(controller: Controller, env: Environment, agentId: int): uint8 =
  let agent = env.agents[agentId]

  # Skip frozen agents
  if agent.frozen > 0:
    return encodeAction(0'u8, 0'u8)

  # Initialize agent role if needed (per-house pattern, 6 agents per house)
  if agentId notin controller.agents:
    let role = case agentId mod MapAgentsPerHouse:  # MapAgentsPerHouse = 6
      of 0: Hearter
      of 1: Armorer
      of 2: Hunter
      of 3: Baker
      of 4: Lighter
      of 5: Farmer
      else: Hearter

    controller.agents[agentId] = AgentState(
      role: role,
      spiralStepsInArc: 0,
      spiralArcsCompleted: 0,
      basePosition: agent.pos,
      lastSearchPosition: agent.pos,
      lastPosition: agent.pos,
      recentPositions: @[],
      stuckCounter: 0,
      escapeMode: false,
      escapeStepsRemaining: 0,
      escapeDirection: ivec2(0, -1)
    )

  var state = controller.agents[agentId]

  # --- Simple bail-out and dithering to avoid getting stuck/oscillation ---
  # Update recent positions history (size 4)
  state.recentPositions.add(agent.pos)
  if state.recentPositions.len > 4:
    state.recentPositions.delete(0)

  # Detect stuck: same position or simple 2-cycle oscillation
  if state.recentPositions.len >= 2 and agent.pos == state.lastPosition:
    inc state.stuckCounter
  elif state.recentPositions.len >= 4:
    let p0 = state.recentPositions[^1]
    let p1 = state.recentPositions[^2]
    let p2 = state.recentPositions[^3]
    let p3 = state.recentPositions[^4]
    if (p0 == p2 and p1 == p3) or (p0 == p1):
      inc state.stuckCounter
    else:
      state.stuckCounter = 0
  else:
    state.stuckCounter = 0

  # Enter escape mode if stuck
  if not state.escapeMode and state.stuckCounter >= 3:
    state.escapeMode = true
    state.escapeStepsRemaining = 6
    state.recentPositions.setLen(0)
    # Choose an escape direction: prefer any empty cardinal, shuffled
    var dirs = @[ivec2(0, -1), ivec2(1, 0), ivec2(0, 1), ivec2(-1, 0)]
    for i in countdown(dirs.len - 1, 1):
      let j = randIntInclusive(controller.rng, 0, i)
      let tmp = dirs[i]
      dirs[i] = dirs[j]
      dirs[j] = tmp
    var chosen = ivec2(0, -1)
    for d in dirs:
      if env.isEmpty(agent.pos + d):
        chosen = d
        break
    state.escapeDirection = chosen

  # If in escape mode, try to move in escape direction for a few steps
  if state.escapeMode and state.escapeStepsRemaining > 0:
    let tryDirs = @[state.escapeDirection,
                    ivec2(state.escapeDirection.y, -state.escapeDirection.x),  # perpendicular 1
                    ivec2(-state.escapeDirection.y, state.escapeDirection.x),  # perpendicular 2
                    ivec2(-state.escapeDirection.x, -state.escapeDirection.y)] # opposite
    for d in tryDirs:
      let np = agent.pos + d
      if env.isEmpty(np):
        dec state.escapeStepsRemaining
        if state.escapeStepsRemaining <= 0:
          state.escapeMode = false
          state.stuckCounter = 0
        state.lastPosition = agent.pos
        return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, vecToOrientation(d).uint8))
    # If all blocked, drop out of escape for this tick
    state.escapeMode = false
    state.stuckCounter = 0

  # Small dithering chance to break deadlocks (higher for non-assembler roles)
  let ditherChance = if state.role == Hearter: 0.10 else: 0.20
  if randFloat(controller.rng) < ditherChance:
    var candidates = @[ivec2(0, -1), ivec2(1, 0), ivec2(0, 1), ivec2(-1, 0),
                       ivec2(1, -1), ivec2(1, 1), ivec2(-1, 1), ivec2(-1, -1)]
    for i in countdown(candidates.len - 1, 1):
      let j = randIntInclusive(controller.rng, 0, i)
      let tmp = candidates[i]
      candidates[i] = candidates[j]
      candidates[j] = tmp
    for d in candidates:
      if isPassable(env, agent.pos + d):
        state.lastPosition = agent.pos
        return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, vecToOrientation(d).uint8))

  # From here on, ensure lastPosition is updated this tick regardless of branch
  state.lastPosition = agent.pos
  # Anchor spiral search around current agent position each tick
  state.basePosition = agent.pos

  # Emergency self-heal: eat bread if below half HP (applies to all roles)
  if agent.inventoryBread > 0 and agent.hp * 2 < agent.maxHp:
    let healDirs = @[ivec2(0, -1), ivec2(1, 0), ivec2(0, 1), ivec2(-1, 0),  # cardinals first
                     ivec2(1, -1), ivec2(1, 1), ivec2(-1, 1), ivec2(-1, -1)] # diagonals
    for d in healDirs:
      let target = agent.pos + d
      if isValidEmptyTile(env, target):
        return saveStateAndReturn(
          controller, agentId, state,
          encodeAction(3'u8, neighborDirIndex(agent.pos, target).uint8))

  let attackDir = findAttackOpportunity(env, agent)
  if attackDir >= 0:
    return saveStateAndReturn(controller, agentId, state, encodeAction(2'u8, attackDir.uint8))

  # Role-based decision making
  case state.role:

  of Lighter:
    # Priority 1: Plant lanterns outward in rings from home assembler
    if agent.inventoryLantern > 0:
      # Determine home center (agent.homeassembler); if unset, use agent.pos
      let center = if agent.homeassembler.x >= 0: agent.homeassembler else: agent.pos

      # Compute current preferred ring radius: smallest R where no plantable tile found yet; start at 3
      var planted = false
      let maxR = 12  # don't search too far per step
      for radius in 3 .. maxR:
        # scan the ring (Chebyshev distance == radius) around center
        var bestDir = -1
        for i in 0 .. 7:
          let dir = orientationToVec(Orientation(i))
          let target = agent.pos + dir
          let dist = max(abs(target.x - center.x), abs(target.y - center.y))
          if dist != radius: continue
          if target.x < 0 or target.x >= MapWidth or target.y < 0 or target.y >= MapHeight:
            continue
          if not env.isEmpty(target):
            continue
          if env.terrain[target.x][target.y] == Water:
            continue
          var spaced = true
          for t in env.things:
            if t.kind == PlantedLantern and chebyshevDist(target, t.pos) < 3'i32:
              spaced = false
              break
          if spaced:
            bestDir = i
            break
        if bestDir >= 0:
          planted = true
          return saveStateAndReturn(controller, agentId, state, encodeAction(6'u8, bestDir.uint8))

      # If no ring slot found, step outward to expand search radius next tick
      let awayFromCenter = getMoveAway(env, agent.pos, center, controller.rng)
      return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, awayFromCenter.uint8))

    # Priority 2: If adjacent to an existing lantern without one to plant, push it further away
    elif isAdjacentToLantern(env, agent.pos):
      let near = findNearestLantern(env, agent.pos)
      if near.found and near.dist == 1'i32:
        # Move into the lantern tile to push it (env will relocate; we bias pushing away in moveAction)
        return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, neighborDirIndex(agent.pos, near.pos).uint8))
      # If diagonally close, step to set up a push next
      let dx = near.pos.x - agent.pos.x
      let dy = near.pos.y - agent.pos.y
      let step = agent.pos + ivec2((if dx != 0: dx div abs(dx) else: 0'i32), (if dy != 0: dy div abs(dy) else: 0'i32))
      return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, neighborDirIndex(agent.pos, step).uint8))

    # Priority 3: Craft lantern if we have wheat
    if agent.inventoryWheat > 0:
      let (did, act) = controller.findAndUseBuilding(env, agent, agentId, state, WeavingLoom)
      if did: return act

    # Priority 3: Collect wheat using spiral search
    else:
      let (did, act) = controller.findAndHarvest(env, agent, agentId, state, Wheat)
      if did: return act

  of Armorer:
    # Priority 1: If we have armor, deliver it to teammates who need it
    if agent.inventoryArmor > 0:
      let teammate = findNearestTeammateNeeding(env, agent, NeedArmor)
      if teammate != nil:
        let dx = abs(teammate.pos.x - agent.pos.x)
        let dy = abs(teammate.pos.y - agent.pos.y)
        if max(dx, dy) == 1'i32:
          # Give armor via PUT to teammate
          return saveStateAndReturn(controller, agentId, state, encodeAction(5'u8, neighborDirIndex(agent.pos, teammate.pos).uint8))
        else:
          return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, teammate.pos, controller.rng).uint8))

    # Priority 2: Craft armor if we have wood
    if agent.inventoryWood > 0:
      let (did, act) = controller.findAndUseBuilding(env, agent, agentId, state, Armory)
      if did: return act

    # Priority 3: Collect wood using spiral search
    else:
      let (did, act) = controller.findAndHarvest(env, agent, agentId, state, Tree)
      if did: return act

  of Hunter:
    # Priority 1: Hunt clippies if we have spear using spiral search
    if agent.inventorySpear > 0:
      let tumor = env.findNearestThingSpiral(state, Tumor, controller.rng)
      if tumor != nil:
        let orientIdx = spearAttackDir(agent.pos, tumor.pos)
        if orientIdx >= 0:
          return saveStateAndReturn(controller, agentId, state, encodeAction(2'u8, orientIdx.uint8))
        else:
          return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, tumor.pos, controller.rng).uint8))
      else:
        # No clippies found, continue spiral search for hunting
        return controller.moveNextSearch(env, agent, agentId, state)

    # Priority 2: If no spear and a nearby tumor (<=3), retreat away
    let nearbyTumor = env.findNearestThingSpiral(state, Tumor, controller.rng)
    if nearbyTumor != nil and chebyshevDist(agent.pos, nearbyTumor.pos) <= 3:
      let awayDir = getMoveAway(env, agent.pos, nearbyTumor.pos, controller.rng)
      return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, awayDir.uint8))

    # Priority 3: Craft spear if we have wood
    if agent.inventoryWood > 0:
      let (did, act) = controller.findAndUseBuilding(env, agent, agentId, state, Forge)
      if did: return act

    # Priority 4: Collect wood using spiral search
    else:
      let (did, act) = controller.findAndHarvest(env, agent, agentId, state, Tree)
      if did: return act

  of Farmer:
    let targetFertile = 10
    let fertileCount = countFertileEmpty(env, agent.pos, 8)

    # Step 1: Create fertile ground until target reached
    if fertileCount < targetFertile:
      let wateringPos = findNearestEmpty(env, agent.pos, false, 8)
      if wateringPos.x >= 0:
        if agent.inventoryWater == 0:
          let waterPos = env.findNearestTerrainSpiral(state, Water, controller.rng)
          if waterPos.x >= 0:
            let dx = abs(waterPos.x - agent.pos.x)
            let dy = abs(waterPos.y - agent.pos.y)
            if max(dx, dy) == 1'i32:
              return saveStateAndReturn(controller, agentId, state, encodeAction(3'u8, neighborDirIndex(agent.pos, waterPos).uint8))
            else:
              return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, waterPos, controller.rng).uint8))
        else:
          let dx = abs(wateringPos.x - agent.pos.x)
          let dy = abs(wateringPos.y - agent.pos.y)
          if max(dx, dy) == 1'i32:
            return saveStateAndReturn(controller, agentId, state, encodeAction(3'u8, neighborDirIndex(agent.pos, wateringPos).uint8))
          else:
            return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, wateringPos, controller.rng).uint8))

      return controller.moveNextSearch(env, agent, agentId, state)

    # Step 2: Plant on fertile tiles if holding resources
    block planting:
      let (didPlant, act) = tryPlantOnFertile(controller, env, agent, agentId, state)
      if didPlant:
        return act

    # Step 3: Gather resources to plant (wood then wheat)
    if agent.inventoryWood == 0:
      let (did, act) = controller.findAndHarvest(env, agent, agentId, state, Tree)
      if did: return act

    if agent.inventoryWheat == 0:
      let (did, act) = controller.findAndHarvest(env, agent, agentId, state, Wheat)
      if did: return act

    # Step 4: If stocked but couldn't plant (no fertile nearby), roam to expand search
    return controller.moveNextSearch(env, agent, agentId, state)

  of Baker:
    # Priority 1: If carrying food, deliver to teammates needing it
    if agent.inventoryBread > 0:
      let teammate = findNearestTeammateNeeding(env, agent, NeedBread)
      if teammate != nil:
        let dx = abs(teammate.pos.x - agent.pos.x)
        let dy = abs(teammate.pos.y - agent.pos.y)
        if max(dx, dy) == 1'i32:
          return saveStateAndReturn(controller, agentId, state, encodeAction(5'u8, neighborDirIndex(agent.pos, teammate.pos).uint8))
        else:
          return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, teammate.pos, controller.rng).uint8))

    # Priority 2: Craft bread if we have wheat
    if agent.inventoryWheat > 0:
      let (did, act) = controller.findAndUseBuilding(env, agent, agentId, state, ClayOven)
      if did: return act

    # Priority 3: Collect wheat using spiral search
    else:
      let (did, act) = controller.findAndHarvest(env, agent, agentId, state, Wheat)
      if did: return act

  of Hearter:
    # Handle ore → battery → assembler workflow
    if agent.inventoryBattery > 0:
      # Find assembler and deposit battery
      for thing in env.things:
        if thing.kind == assembler and thing.pos == agent.homeassembler:
          let dx = abs(thing.pos.x - agent.pos.x)
          let dy = abs(thing.pos.y - agent.pos.y)
          if max(dx, dy) == 1'i32:
            return saveStateAndReturn(controller, agentId, state, encodeAction(3'u8, neighborDirIndex(agent.pos, thing.pos).uint8))
          else:
            return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, thing.pos, controller.rng).uint8))

    elif agent.inventoryOre > 0:
      # Find converter and make battery using spiral search
      let converterThing = env.findNearestThingSpiral(state, Converter, controller.rng)
      if converterThing != nil:
        # Converter uses GET to consume ore and produce battery
        let dx = abs(converterThing.pos.x - agent.pos.x)
        let dy = abs(converterThing.pos.y - agent.pos.y)
        if max(dx, dy) == 1'i32:
          return saveStateAndReturn(controller, agentId, state, encodeAction(3'u8, neighborDirIndex(agent.pos, converterThing.pos).uint8))
        else:
          return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, converterThing.pos, controller.rng).uint8))
      else:
        # No converter found, continue spiral search
        let nextSearchPos = getNextSpiralPoint(state, controller.rng)
        return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, nextSearchPos, controller.rng).uint8))

    else:
      # Find mine and collect ore using spiral search
      let mine = env.findNearestThingSpiral(state, Mine, controller.rng)
      if mine != nil:
        let dx = abs(mine.pos.x - agent.pos.x)
        let dy = abs(mine.pos.y - agent.pos.y)
        if max(dx, dy) == 1'i32:
          return saveStateAndReturn(controller, agentId, state, encodeAction(3'u8, neighborDirIndex(agent.pos, mine.pos).uint8))
        else:
          return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, mine.pos, controller.rng).uint8))
      else:
        # No mine found, continue spiral search
        let nextSearchPos = getNextSpiralPoint(state, controller.rng)
        return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, getMoveTowards(env, agent.pos, nextSearchPos, controller.rng).uint8))

  # Save last position for next tick and return a default random move
  state.lastPosition = agent.pos
  return saveStateAndReturn(controller, agentId, state, encodeAction(1'u8, randIntInclusive(controller.rng, 0, 7).uint8))

# Compatibility function for updateController
proc updateController*(controller: Controller) =
  # No complex state to update - keep it simple
  discard
