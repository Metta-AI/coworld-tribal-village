# Play Tribal Village

Run a local episode with `coworld play coworld_manifest.json` or a headless smoke with
`coworld run-episode coworld_manifest.json`. Open `/client/global` to watch the map,
`/client/player?slot=0&token=...` to inspect or control a slot, and `/client/replay` to view saved replay action logs.

Player containers should connect to the exact `COWORLD_PLAYER_WS_URL` supplied by the runner and send JSON actions
shaped as `{ "type": "action", "action": 0 }`. The packaged `default-ai-agent` player uses the same image and
WebSocket route as tournament players.

Replay mode autoplays, loops, and draws `#slot name` labels above agents. Replay artifacts store only the deterministic
initial config plus compact per-tick action deltas.

When docs, commands, runtime behavior, logs, or replays disagree, preserve the evidence and file an issue in the
Coworld repo: https://github.com/Metta-AI/coworld/issues. Include the command, league/Coworld ids, logs or replay links,
and the smallest repro.
