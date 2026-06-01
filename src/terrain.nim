import std/math, vmath
import rng_compat

type
  TerrainType* = enum
    Empty
    Water
    Bridge
    Wheat
    Tree
    Fertile

  TerrainGrid* = array[256, array[256, TerrainType]]

  Structure* = object
    width*, height*: int
    centerPos*: IVec2
    layout*: seq[seq[char]]

template randInclusive(r: var Rand, a, b: int): int = randIntInclusive(r, a, b)
template randChance(r: var Rand, p: float): bool = randFloat(r) < p

const
  RiverWidth* = 6

proc inCornerReserve(x, y, mapWidth, mapHeight, mapBorder: int, reserve: int): bool =
  ## Returns true if the coordinate is within a reserved corner area
  let left = mapBorder
  let right = mapWidth - mapBorder
  let top = mapBorder
  let bottom = mapHeight - mapBorder
  let rx = reserve
  let ry = reserve
  let inTopLeft = (x >= left and x < left + rx) and (y >= top and y < top + ry)
  let inTopRight = (x >= right - rx and x < right) and (y >= top and y < top + ry)
  let inBottomLeft = (x >= left and x < left + rx) and (y >= bottom - ry and y < bottom)
  let inBottomRight = (x >= right - rx and x < right) and (y >= bottom - ry and y < bottom)
  inTopLeft or inTopRight or inBottomLeft or inBottomRight

proc generateRiver*(terrain: var TerrainGrid, mapWidth, mapHeight, mapBorder: int, r: var Rand) =
  var riverPath: seq[IVec2] = @[]

  # Reserve corners for villages so river doesn't block them
  let reserve = max(8, min(mapWidth, mapHeight) div 10)

  # Start near left edge and centered vertically (avoid corner reserves)
  let centerY = mapHeight div 2
  let span = max(6, mapHeight div 6)
  var startMin = max(mapBorder + RiverWidth + reserve, centerY - span)
  var startMax = min(mapHeight - mapBorder - RiverWidth - reserve, centerY + span)
  if startMin > startMax: swap(startMin, startMax)
  var currentPos = ivec2(mapBorder.int32, randInclusive(r, startMin, startMax).int32)

  var hasFork = false
  var forkPoint: IVec2
  var secondaryPath: seq[IVec2] = @[]

  while currentPos.x >= mapBorder and currentPos.x < mapWidth - mapBorder and
        currentPos.y >= mapBorder and currentPos.y < mapHeight - mapBorder:
    riverPath.add(currentPos)

    if not hasFork and riverPath.len > max(20, mapWidth div 8) and randChance(r, 0.5):
      hasFork = true
      forkPoint = currentPos

      let towardTop = int(forkPoint.y) - mapBorder
      let towardBottom = (mapHeight - mapBorder) - int(forkPoint.y)
      let dirY = (if towardTop < towardBottom: -1 else: 1)
      var secondaryDirection = ivec2(1, dirY.int32)

      var secondaryPos = forkPoint
      let maxSteps = max(mapWidth * 2, mapHeight * 2)
      var steps = 0
      while secondaryPos.y > mapBorder + RiverWidth and secondaryPos.y < mapHeight - mapBorder - RiverWidth and steps < maxSteps:
        secondaryPos.x += 1
        secondaryPos.y += secondaryDirection.y
        if randChance(r, 0.15):
          secondaryPos.y += sample(r, [-1, 0, 1]).int32
        if secondaryPos.x >= mapBorder and secondaryPos.x < mapWidth - mapBorder and
           secondaryPos.y >= mapBorder and secondaryPos.y < mapHeight - mapBorder:
          if not inCornerReserve(secondaryPos.x, secondaryPos.y, mapWidth, mapHeight, mapBorder, reserve):
            secondaryPath.add(secondaryPos)
        else:
          break
        inc steps
      # Ensure the branch touches the edge vertically with a short vertical run
      var tip = secondaryPos
      var pushSteps = 0
      let maxPush = mapHeight
      if dirY < 0:
        while tip.y > mapBorder and pushSteps < maxPush:
          dec tip.y
          if tip.x >= mapBorder and tip.x < mapWidth and tip.y >= mapBorder and tip.y < mapHeight:
            if not inCornerReserve(tip.x, tip.y, mapWidth, mapHeight, mapBorder, reserve):
              secondaryPath.add(tip)
          inc pushSteps
      else:
        while tip.y < mapHeight - mapBorder and pushSteps < maxPush:
          inc tip.y
          if tip.x >= mapBorder and tip.x < mapWidth and tip.y >= mapBorder and tip.y < mapHeight:
            if not inCornerReserve(tip.x, tip.y, mapWidth, mapHeight, mapBorder, reserve):
              secondaryPath.add(tip)
          inc pushSteps

    currentPos.x += 1  # Always move right
    if randChance(r, 0.3):
      currentPos.y += sample(r, [-1, 0, 0, 1]).int32  # Bias towards staying straight

  # Place water tiles for main river (skip reserved corners)
  for pos in riverPath:
    for dx in -RiverWidth div 2 .. RiverWidth div 2:
      for dy in -RiverWidth div 2 .. RiverWidth div 2:
        let waterPos = pos + ivec2(dx.int32, dy.int32)
        if waterPos.x >= 0 and waterPos.x < mapWidth and
           waterPos.y >= 0 and waterPos.y < mapHeight:
          if not inCornerReserve(waterPos.x, waterPos.y, mapWidth, mapHeight, mapBorder, reserve):
            terrain[waterPos.x][waterPos.y] = Water

  # Place water tiles for secondary branch (skip reserved corners)
  for pos in secondaryPath:
    for dx in -(RiverWidth div 2 - 1) .. (RiverWidth div 2 - 1):
      for dy in -(RiverWidth div 2 - 1) .. (RiverWidth div 2 - 1):
        let waterPos = pos + ivec2(dx.int32, dy.int32)
        if waterPos.x >= 0 and waterPos.x < mapWidth and
           waterPos.y >= 0 and waterPos.y < mapHeight:
          if not inCornerReserve(waterPos.x, waterPos.y, mapWidth, mapHeight, mapBorder, reserve):
            terrain[waterPos.x][waterPos.y] = Water

  # Place bridges across the river and any tributary branch.
  # Bridges are three tiles wide (east-west) and span slightly beyond river width north-south.
  proc placeBridgeMain(t: var TerrainGrid, center: IVec2) =
    let startY = max(mapBorder, int(center.y) - (RiverWidth div 2 + 1))
    let endY = min(mapHeight - mapBorder - 1, int(center.y) + (RiverWidth div 2 + 1))
    let baseX = max(mapBorder, min(mapWidth - mapBorder - 3, int(center.x) - 1))
    for dx in 0 .. 2:
      for y in startY .. endY:
        if not inCornerReserve(baseX + dx, y, mapWidth, mapHeight, mapBorder, reserve):
          t[baseX + dx][y] = Bridge

  # Branch bridges run horizontally (east-west span) across the tributary.
  proc placeBridgeBranch(t: var TerrainGrid, center: IVec2) =
    let startX = max(mapBorder, int(center.x) - (RiverWidth div 2 + 1))
    let endX = min(mapWidth - mapBorder - 1, int(center.x) + (RiverWidth div 2 + 1))
    let baseY = max(mapBorder, min(mapHeight - mapBorder - 3, int(center.y) - 1))
    for dy in 0 .. 2:
      for x in startX .. endX:
        if not inCornerReserve(x, baseY + dy, mapWidth, mapHeight, mapBorder, reserve):
          t[x][baseY + dy] = Bridge

  var mainCandidates: seq[IVec2] = @[]
  for pos in riverPath:
    if pos.x > mapBorder + RiverWidth and pos.x < mapWidth - mapBorder - RiverWidth and
       pos.y > mapBorder + RiverWidth and pos.y < mapHeight - mapBorder - RiverWidth and
       not inCornerReserve(pos.x, pos.y, mapWidth, mapHeight, mapBorder, reserve):
      mainCandidates.add(pos)

  var branchCandidates: seq[IVec2] = @[]
  for pos in secondaryPath:
    if pos.x > mapBorder + RiverWidth and pos.x < mapWidth - mapBorder - RiverWidth and
       pos.y > mapBorder + RiverWidth and pos.y < mapHeight - mapBorder - RiverWidth and
       not inCornerReserve(pos.x, pos.y, mapWidth, mapHeight, mapBorder, reserve):
      branchCandidates.add(pos)

  let hasBranch = secondaryPath.len > 0
  let desiredBridges = max(randInclusive(r, 4, 5), (if hasBranch: 3 else: 0))

  var placed: seq[IVec2] = @[]
  template placeFrom(cands: seq[IVec2], useBranch: bool) =
    if cands.len > 0:
      let center = cands[cands.len div 2]
      if useBranch:
        placeBridgeBranch(terrain, center)
      else:
        placeBridgeMain(terrain, center)
      placed.add(center)

  if hasBranch:
    let forkIdx = riverPath.find(forkPoint)
    if forkIdx >= 0:
      let upstream = if forkIdx > 0: mainCandidates[0 ..< min(forkIdx, mainCandidates.len)] else: @[]
      let downstream = if forkIdx < mainCandidates.len: mainCandidates[min(forkIdx, mainCandidates.len-1) ..< mainCandidates.len] else: @[]
      placeFrom(upstream, false)
      placeFrom(branchCandidates, true)
      placeFrom(downstream, false)

  # Fill remaining bridges by spreading along main river first, then branch.
  proc uniqueAdd(pos: IVec2, list: var seq[IVec2]) =
    for p in list:
      if p == pos: return
    list.add(pos)

  var remaining = desiredBridges - placed.len
  if remaining > 0 and mainCandidates.len > 0:
    let stride = max(1, mainCandidates.len div (remaining + 1))
    var idx = stride
    while remaining > 0 and idx < mainCandidates.len:
      let center = mainCandidates[idx]
      uniqueAdd(center, placed)
      placeBridgeMain(terrain, center)
      dec remaining
      idx += stride

  if remaining > 0 and branchCandidates.len > 0:
    let stride = max(1, branchCandidates.len div (remaining + 1))
    var idx = stride
    while remaining > 0 and idx < branchCandidates.len:
      let center = branchCandidates[idx]
      uniqueAdd(center, placed)
      placeBridgeBranch(terrain, center)
      dec remaining
      idx += stride

proc createTerrainCluster*(terrain: var TerrainGrid, centerX, centerY: int, size: int,
                          mapWidth, mapHeight: int, terrainType: TerrainType,
                          baseDensity: float, falloffRate: float, r: var Rand) =
  ## Create a terrain cluster around a center point with configurable density
  let radius = (size.float / 2.0).int
  for dx in -radius .. radius:
    for dy in -radius .. radius:
      let x = centerX + dx
      let y = centerY + dy
      if x >= 0 and x < mapWidth and y >= 0 and y < mapHeight:
        if terrain[x][y] == Empty:
          let dist = sqrt((dx * dx + dy * dy).float)
          if dist <= radius.float:
            let chance = baseDensity - (dist / radius.float) * falloffRate
            if randChance(r, chance):
              terrain[x][y] = terrainType

proc generateWheatFields*(terrain: var TerrainGrid, mapWidth, mapHeight, mapBorder: int, r: var Rand) =
  ## Generate clustered wheat fields; 4x previous count for larger maps
  let numFields = randInclusive(r, 14, 20) * 4

  for i in 0 ..< numFields:
    var placed = false
    for attempt in 0 ..< 20:
      let x = randInclusive(r, mapBorder + 3, mapWidth - mapBorder - 3)
      let y = randInclusive(r, mapBorder + 3, mapHeight - mapBorder - 3)

      var nearWater = false
      for dx in -5 .. 5:
        for dy in -5 .. 5:
          let checkX = x + dx
          let checkY = y + dy
          if checkX >= 0 and checkX < mapWidth and checkY >= 0 and checkY < mapHeight:
            if terrain[checkX][checkY] == Water:
              nearWater = true
              break
        if nearWater:
          break

      if nearWater or attempt > 10:
        let fieldSize = randInclusive(r, 3, 10)
        terrain.createTerrainCluster(x, y, fieldSize, mapWidth, mapHeight, Wheat, 1.0, 0.3, r)
        placed = true
        break

    if not placed:
      let x = randInclusive(r, mapBorder + 3, mapWidth - mapBorder - 3)
      let y = randInclusive(r, mapBorder + 3, mapHeight - mapBorder - 3)
      let fieldSize = randInclusive(r, 3, 10)
      terrain.createTerrainCluster(x, y, fieldSize, mapWidth, mapHeight, Wheat, 1.0, 0.3, r)

proc generateTrees*(terrain: var TerrainGrid, mapWidth, mapHeight, mapBorder: int, r: var Rand) =
  ## Generate tree groves; 4x previous count for larger maps
  let numGroves = randInclusive(r, 14, 20) * 4

  for i in 0 ..< numGroves:
    let x = randInclusive(r, mapBorder + 3, mapWidth - mapBorder - 3)
    let y = randInclusive(r, mapBorder + 3, mapHeight - mapBorder - 3)
    let groveSize = randInclusive(r, 3, 10)
    terrain.createTerrainCluster(x, y, groveSize, mapWidth, mapHeight, Tree, 0.8, 0.4, r)

proc initTerrain*(terrain: var TerrainGrid, mapWidth, mapHeight, mapBorder: int, seed: int = 2024) =
  ## Initialize terrain with all features
  var r = initRand(seed)

  for x in 0 ..< mapWidth:
    for y in 0 ..< mapHeight:
      terrain[x][y] = Empty

  terrain.generateRiver(mapWidth, mapHeight, mapBorder, r)
  terrain.generateWheatFields(mapWidth, mapHeight, mapBorder, r)
  terrain.generateTrees(mapWidth, mapHeight, mapBorder, r)

proc getStructureElements*(structure: Structure, topLeft: IVec2): tuple[
    walls: seq[IVec2],
    floors: seq[IVec2],
    assemblers: seq[IVec2],
    forges: seq[IVec2],
    armories: seq[IVec2],
    clayOvens: seq[IVec2],
    weavingLooms: seq[IVec2],
    center: IVec2
  ] =
  ## Extract tiles for placing a structure
  result.walls = @[]
  result.floors = @[]
  result.assemblers = @[]
  result.forges = @[]
  result.armories = @[]
  result.clayOvens = @[]
  result.weavingLooms = @[]

  result.center = topLeft + structure.centerPos

  for y, row in structure.layout:
    for x, cell in row:
      let pos = ivec2(topLeft.x + x.int32, topLeft.y + y.int32)
      case cell
      of '#': result.walls.add(pos)
      of '.': result.floors.add(pos)
      of 'a': result.assemblers.add(pos)
      of 'F': result.forges.add(pos)
      of 'A': result.armories.add(pos)
      of 'C': result.clayOvens.add(pos)
      of 'W': result.weavingLooms.add(pos)
      else: discard
