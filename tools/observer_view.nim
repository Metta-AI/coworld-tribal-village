## Render one detached public snapshot with Polyworld's shape batcher.
## This executable links no Tribal Village simulation or action interface.
## Arguments are the observer JSON and an output PNG path.

import std/[base64, json, os]
import chroma, opengl, pixie, vmath, windy
import polyworld/shapes

if paramCount() != 2:
  quit("usage: observer_view observer.json output.png", 2)

let snapshot = parseFile(paramStr(1))
if snapshot["kind"].getStr != "tribal-village-observer-v1" or
    snapshot["stride"].getInt != 28 or snapshot["encoding"].getStr != "base64":
  quit("unsupported observer snapshot", 2)
let
  width = snapshot["width"].getInt
  height = snapshot["height"].getInt
  cells = decode(snapshot["cells"].getStr)
if width < 1 or height < 1 or width > 4096 or height > 4096 or
    cells.len != width * height * 28:
  quit("invalid observer dimensions or payload length", 2)

let window = newWindow("Tribal Village public observer", ivec2(1000, 580),
                       visible = false, vsync = false)
window.makeContextCurrent()
loadExtensions()
echo "GL renderer: ", cast[cstring](glGetString(GL_RENDERER))
var renderer = initShapeRenderer()

proc tile(x, y: int, margin, depth: float32, color: ColorRGBX) =
  let
    left = -1'f32 + 2 * (x.float32 + margin) / width.float32
    right = -1'f32 + 2 * (x.float32 + 1 - margin) / width.float32
    top = 1'f32 - 2 * (y.float32 + margin) / height.float32
    bottom = 1'f32 - 2 * (y.float32 + 1 - margin) / height.float32
  renderer.addQuad(vec3(left, top, depth), vec3(right, top, depth),
                   vec3(right, bottom, depth), vec3(left, bottom, depth), color)

const teams = [
  rgbx(220, 80, 70, 255), rgbx(70, 130, 240, 255),
  rgbx(80, 210, 110, 255), rgbx(245, 205, 70, 255),
  rgbx(170, 90, 220, 255), rgbx(240, 150, 65, 255),
  rgbx(60, 210, 220, 255), rgbx(235, 100, 175, 255)]
for y in 0 ..< height:
  for x in 0 ..< width:
    let i = (y * width + x) * 28
    tile(x, y, 0, 0.5, rgbx(cells[i + 1].uint8, cells[i + 2].uint8,
                            cells[i + 3].uint8, 255))
    let kind = cells[i + 4].ord
    if kind != 255:
      let color =
        if kind == 0: teams[cells[i + 7].ord mod teams.len]
        elif kind == 2: rgbx(240, 210, 90, 255)
        else: rgbx(160, 170, 175, 255)
      tile(x, y, 0.12, 0, color)

glViewport(0, 0, 1000, 580)
glClearColor(0, 0, 0, 1)
glClear(GL_COLOR_BUFFER_BIT or GL_DEPTH_BUFFER_BIT)
renderer.draw(mat4())
glFinish()
let frame = newImage(1000, 580)
glReadPixels(0, 0, 1000, 580, GL_RGBA, GL_UNSIGNED_BYTE, frame.data[0].addr)
frame.flipVertical()
frame.writeFile(paramStr(2))
echo "Rendered public tick ", snapshot["tick"].getInt, " at ", width, "x", height
renderer.closeShapeRenderer()
window.close()
