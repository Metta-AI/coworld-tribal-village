## Headless multi-seed evaluation harness for the built-in scripted AI.
##
## Runs full episodes with the same controller the villager player uses and
## reports per-team scores plus territory diagnostics, so AI changes can be
## A/B tested without the renderer or the Coworld server.
##
##   nim r -d:release tests/eval_builtin_ai.nim            # default seeds
##   nim r -d:release tests/eval_builtin_ai.nim 12 13 14   # explicit seeds

import std/[algorithm, os, sequtils, strformat, strutils]
import ../src/[ai, environment]

const
  Steps = 2000
  Teams = MapRoomObjectsHouses

type EpisodeResult = object
  seed: int
  teamScores: array[Teams, float32]
  lanterns: array[Teams, int]
  deaths: array[Teams, int]
  hearts: array[Teams, int]

proc runEpisode(seed: int): EpisodeResult =
  result.seed = seed
  var config = defaultEnvironmentConfig()
  config.maxSteps = Steps
  config.seed = seed
  let env = newEnvironment(config)
  env.reset()
  let controller = newController(seed)

  var prevTerminated: array[MapAgents, float32]
  for step in 0 ..< Steps:
    var actions: array[MapAgents, uint8]
    for agentId in 0 ..< MapAgents:
      actions[agentId] = controller.decideAction(env, agentId)
    controller.updateController()
    env.step(addr actions)
    for agentId in 0 ..< MapAgents:
      let agent = env.agents[agentId]
      result.teamScores[getTeamId(agentId)] += agent.reward
      agent.reward = 0
      if env.terminated[agentId] == 1.0 and prevTerminated[agentId] == 0.0:
        inc result.deaths[getTeamId(agentId)]
      prevTerminated[agentId] = env.terminated[agentId]

  for thing in env.things:
    if thing.kind == PlantedLantern and thing.lanternHealthy and
        thing.teamId >= 0 and thing.teamId < Teams:
      inc result.lanterns[thing.teamId]
    elif thing.kind == assembler:
      for agent in env.agents:
        if agent.homeassembler == thing.pos:
          result.hearts[getTeamId(agent.agentId)] = thing.hearts
          break

when isMainModule:
  var seeds: seq[int]
  for i in 1 .. paramCount():
    seeds.add parseInt(paramStr(i))
  if seeds.len == 0:
    seeds = @[11, 22, 33, 44, 55, 66, 77, 88]

  var
    allTeamScores: seq[float]
    allLanterns: seq[float]
    allDeaths: seq[float]

  echo fmt"""{"seed":>6} {"mean":>8} {"best":>8} {"worst":>8} {"lant":>6} {"death":>6} {"hearts":>7}"""
  for seed in seeds:
    let ep = runEpisode(seed)
    var scores: seq[float]
    var lanterns = 0
    var deaths = 0
    var hearts = 0
    for t in 0 ..< Teams:
      scores.add ep.teamScores[t].float
      allTeamScores.add ep.teamScores[t].float
      lanterns += ep.lanterns[t]
      deaths += ep.deaths[t]
      hearts += ep.hearts[t]
      allLanterns.add ep.lanterns[t].float
      allDeaths.add ep.deaths[t].float
    scores.sort()
    let mean = scores.foldl(a + b, 0.0) / scores.len.float
    echo fmt"{seed:>6} {mean:>8.2f} {scores[^1]:>8.2f} {scores[0]:>8.2f} {lanterns:>6} {deaths:>6} {hearts:>7}"

  let n = allTeamScores.len.float
  let meanScore = allTeamScores.foldl(a + b, 0.0) / n
  let meanLant = allLanterns.foldl(a + b, 0.0) / n
  let meanDeath = allDeaths.foldl(a + b, 0.0) / n
  echo ""
  echo fmt"team-mean score: {meanScore:.3f}   lanterns/team: {meanLant:.2f}   deaths/team: {meanDeath:.2f}   (n={allTeamScores.len} team-episodes)"
