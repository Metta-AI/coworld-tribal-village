import vmath, terrain

export terrain.Structure


proc createHouse*(): Structure =
  result.width = 5
  result.height = 5
  result.centerPos = ivec2(2, 2)

  result.layout = @[
    @['A', '#', '.', '#', 'F'],  # Top row with Armory (top-left), Forge (top-right)
    @['#', ' ', ' ', ' ', '#'],  # Second row
    @['.', ' ', 'a', ' ', '.'],  # Center altar (respawn hearts) with E/W entrances
    @['#', ' ', ' ', ' ', '#'],  # Fourth row
    @['C', '#', '.', '#', 'W']   # Bottom row with Clay Oven (bottom-left), Weaving Loom (bottom-right)
  ]


proc createSpawner*(): Structure =
  result.width = 3
  result.height = 3
  result.centerPos = ivec2(1, 1)
