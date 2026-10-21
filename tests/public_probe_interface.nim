## Restrict this experimental binary's C exports without changing the engine ABI.
## Nim dynlib pragmas otherwise retain private exports in Emscripten builds even
## when EXPORTED_FUNCTIONS names only the public observer interface.
import std/macros

macro publicProbeInterface*(): untyped =
  result = parseStmt(staticRead("../src/tribal_village_interface.nim"))
  const publicNames = [
    "tribal_village_create", "tribal_village_set_config",
    "tribal_village_reset_for_coworld", "tribal_village_step_for_coworld",
    "tribal_village_export_world_cells", "tribal_village_destroy",
    "tribal_village_get_num_agents", "tribal_village_get_map_width",
    "tribal_village_get_map_height"]
  for declaration in result:
    if declaration.kind == nnkProcDef and $declaration[0] notin publicNames:
      var kept = newNimNode(nnkPragma)
      for pragma in declaration[4]:
        if $pragma notin ["exportc", "dynlib"]:
          kept.add(pragma)
      declaration[4] = kept
