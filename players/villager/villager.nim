## Villager - the bundled Tribal Village scripted-AI tournament player.
##
## Connects to the Coworld `/player` WebSocket, rebuilds the episode in a
## deterministic local mirror seeded by the first observation, and replays the
## built-in role-based Nim AI (src/ai.nim) for its slot - the same policy that
## drives agents in the local desktop game.
##
## Run against a local server:
##   COWORLD_PLAYER_WS_URL='ws://127.0.0.1:8080/player?slot=0&token=...' \
##   nim r players/villager/villager.nim

import std/[json, options, os]
import whisky
import ../../src/[ai, environment]

const
  InitialConnectWindowMs = 60_000
  ReconnectWindowMs = 8_000
  ReconnectAttemptMs = 1_000

type
  Mirror = ref object
    env: Environment
    controller: Controller
    lastTick: int
    lastAction: int

proc newMirror(firstMessage: JsonNode): Mirror =
  ## Builds the deterministic episode mirror the same way the game server
  ## builds its environment: custom config, reset, then a fresh controller.
  let
    gameConfig = firstMessage{"game_config"}
    seed =
      if gameConfig != nil: gameConfig{"seed"}.getInt(1)
      else: 1
    maxSteps = firstMessage{"max_steps"}.getInt(0)
  var config = defaultEnvironmentConfig()
  if maxSteps > 0:
    config.maxSteps = maxSteps
  if seed > 0:
    config.seed = seed
  result = Mirror(
    env: newEnvironment(config),
    controller: newController(if seed > 0: seed else: 1),
    lastTick: -1
  )
  result.env.reset()

proc builtinActions(mirror: Mirror): array[MapAgents, uint8] =
  ## Computes the full 48-agent action vector from the built-in AI.
  for agentId in 0 ..< MapAgents:
    result[agentId] = mirror.controller.decideAction(mirror.env, agentId)
  mirror.controller.updateController()

proc chooseAction(mirror: Mirror, slot, tick: int): int =
  ## Catches the mirror up to the server tick and picks this slot's action.
  ## The server re-sends the current tick on every (re)connect, so duplicate
  ## observations must not advance the mirror.
  if tick <= mirror.lastTick:
    return mirror.lastAction
  while mirror.env.currentStep < tick:
    var actions = mirror.builtinActions()
    mirror.env.step(addr actions)
  var actions = mirror.builtinActions()
  result =
    if slot >= 0 and slot < MapAgents: actions[slot].int
    else: 0
  mirror.env.step(addr actions)
  mirror.lastTick = tick
  mirror.lastAction = result

proc playEpisode(
  url: string,
  mirror: var Mirror,
  connected: var bool
): bool =
  ## Runs the message loop on one connection. Returns true when the episode
  ## reports it is done.
  let ws = newWebSocket(url)
  echo "connected to ", url
  connected = true
  while true:
    let received = ws.receiveMessage()
    if received.isNone:
      continue
    let message = received.get
    if message.kind != TextMessage:
      continue
    let node = parseJson(message.data)
    if node{"done"}.getBool(false) or node{"type"}.getStr() == "final":
      return true
    if node{"type"}.getStr() != "observation":
      continue
    if mirror == nil:
      mirror = newMirror(node)
    let action = mirror.chooseAction(
      node{"slot"}.getInt(0),
      node{"tick"}.getInt(0)
    )
    ws.send($ %*{"type": "action", "action": action})

proc runPlayer() =
  ## Connects with retry windows like the Crewrift notsus player: tournament
  ## player containers can start before the game server accepts connections.
  let url = getEnv("COWORLD_PLAYER_WS_URL")
  if url.len == 0:
    quit("COWORLD_PLAYER_WS_URL is required", 1)
  var
    mirror: Mirror = nil
    everConnected = false
    waitedMs = 0
  while true:
    var connectedThisAttempt = false
    try:
      if playEpisode(url, mirror, connectedThisAttempt):
        echo "episode finished"
        return
    except CatchableError as e:
      echo "connection error: ", e.msg
    if connectedThisAttempt:
      everConnected = true
      waitedMs = 0
    let windowMs =
      if everConnected: ReconnectWindowMs
      else: InitialConnectWindowMs
    if waitedMs >= windowMs:
      quit("cannot connect after " & $(windowMs div 1000) & "s; exiting", 1)
    sleep(ReconnectAttemptMs)
    waitedMs += ReconnectAttemptMs

when isMainModule:
  runPlayer()
