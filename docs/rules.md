# Tribal Village Rules

Tribal Village has 48 player slots. Each slot controls one agent in an eight-team village, with six agents per team.
Agents gather ore, water, wheat, and wood; craft batteries, spears, lanterns, armor, and bread; fight hostile tumors;
and support their team's survival.

Each player receives a rendered RGB view window and sends one discrete action per tick. The bundled
`default-ai-agent` player runs the existing Nim role-based scripted AI in a deterministic local mirror and still sends
actions through the `/player` route.

Final scores are cumulative per-agent rewards, with team scores computed by summing each team's six agents.
