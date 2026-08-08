# Tribal Village Rules

Tribal Village runs two to eight villages at once, with six player slots per team. Tournament seating assigns one
entrant policy to all six agents in a village, so a policy must coordinate the village's full role mix.
Agents gather ore, water, wheat, and wood; craft batteries, spears, lanterns, armor, and bread; fight hostile tumors;
and support their team's survival.

Each player receives JSON action observations and sends one discrete action per tick. The visual map is the full-world
sprite-cell stream served on `/global` for live games and `/replay` for replay games. The bundled `villager`
player (a native Nim binary in `players/villager/`) runs the existing role-based scripted AI in a deterministic local
mirror and sends actions through the `/player` route.

Final scores are cumulative per-agent rewards, with team scores computed by summing each team's six agents. Healthy
planted lanterns provide ongoing team reward, so territory control is the primary durable scoring path.

Every active village adds exactly one hostile spawner. The game therefore keeps the same six-agent-to-one-spawner
pressure at every supported team count instead of overwhelming smaller matches with the eight-team threat budget.
