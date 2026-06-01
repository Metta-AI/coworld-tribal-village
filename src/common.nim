when defined(emscripten):
  import windy/platforms/emscripten/emdefs
else:
  import std/[times]

import
  boxy, windy, vmath

type
  IRect* = object
    x*: int
    y*: int
    w*: int
    h*: int

  PanelType* = enum
    WorldMap

  Panel* = ref object
    panelType*: PanelType
    rect*: IRect
    name*: string

    pos*: Vec2
    vel*: Vec2
    zoom*: float32 = 2.0      # preferred default zoom
    zoomVel*: float32
    minZoom*: float32 = 2.0   # enforce same min as default
    maxZoom*: float32 = 8.0   # reduce maximum zoom-out
    hasMouse*: bool = false
    visible*: bool = true

  AreaLayout* = enum
    Horizontal
    Vertical

  Area* = ref object
    layout*: AreaLayout
    rect*: IRect
    areas*: seq[Area]
    panels*: seq[Panel]


  Settings* = object
    showFogOfWar* = false
    showVisualRange* = true
    showGrid* = true
    showObservations* = -1

proc nowSeconds*(): float64 =
  when defined(emscripten):
    emscripten_get_now() / 1000.0
  else:
    epochTime()

var
  window*: Window
  rootArea*: Area
  bxy*: Boxy
  frame*: int


  worldMapPanel*: Panel
  globalFooterPanel*: Panel

  settings* = Settings()

  play*: bool
  playSpeed*: float32 = 0.25    # quadruple baseline speed
  lastSimTime*: float64 = nowSeconds()

const
  DefaultPlaySpeed* = 0.0625

var
  followSelection*: bool = false
  mouseCaptured*: bool = false
  mouseCapturedPanel*: Panel = nil
  mouseDownPos*: Vec2 = vec2(0, 0)

proc logicalMousePos*(window: Window): Vec2 =
  ## Mouse position in logical coordinates (accounts for HiDPI scaling).
  window.mousePos.vec2 / window.contentScale

proc logicalMouseDelta*(window: Window): Vec2 =
  ## Mouse delta in logical coordinates (accounts for HiDPI scaling).
  window.mouseDelta.vec2 / window.contentScale

proc irect*(x, y, w, h: int): IRect =
  ## Utility function to create IRect from coordinates
  result.x = x
  result.y = y
  result.w = w
  result.h = h

proc irect*(rect: Rect): IRect =
  ## Convert floating point Rect to integer IRect
  result.x = rect.x.int
  result.y = rect.y.int
  result.w = rect.w.int
  result.h = rect.h.int

proc rect*(irect: IRect): Rect =
  ## Convert integer IRect to floating point Rect
  result.x = irect.x.float32
  result.y = irect.y.float32
  result.w = irect.w.float32
  result.h = irect.h.float32

type
  OrientationDelta* = tuple[x, y: int]
  Orientation* = enum
    N = 0  # North (Up)
    S = 1  # South (Down) 
    W = 2  # West (Left)
    E = 3  # East (Right)
    NW = 4 # Northwest (Up-Left)
    NE = 5 # Northeast (Up-Right)
    SW = 6 # Southwest (Down-Left)
    SE = 7 # Southeast (Down-Right)

const OrientationDeltas*: array[8, OrientationDelta] = [
  (x: 0, y: -1),   # N (North)
  (x: 0, y: 1),    # S (South)
  (x: -1, y: 0),   # W (West)
  (x: 1, y: 0),    # E (East)
  (x: -1, y: -1),  # NW (Northwest)
  (x: 1, y: -1),   # NE (Northeast)
  (x: -1, y: 1),   # SW (Southwest)
  (x: 1, y: 1)     # SE (Southeast)
]

const
  ActionVerbCount* = 8  # Added plant-resource action (verb 7)
  ActionArgumentCount* = 8

proc encodeAction*(verb: uint8, argument: uint8): uint8 =
  (verb.int * ActionArgumentCount + argument.int).uint8

proc decodeAction*(value: uint8): tuple[verb: uint8, argument: uint8] =
  (verb: (value.int div ActionArgumentCount).uint8, argument: (value.int mod ActionArgumentCount).uint8)

{.push inline.}
proc getOrientationDelta*(orient: Orientation): OrientationDelta =
  OrientationDeltas[ord(orient)]
{.pop.}

proc orientationToVec*(orientation: Orientation): IVec2 =
  case orientation
  of N: result = ivec2(0, -1)
  of S: result = ivec2(0, 1)
  of E: result = ivec2(1, 0)
  of W: result = ivec2(-1, 0)
  of NW: result = ivec2(-1, -1)
  of NE: result = ivec2(1, -1)
  of SW: result = ivec2(-1, 1)
  of SE: result = ivec2(1, 1)

proc ivec2*(x, y: int): IVec2 =
  result.x = x.int32
  result.y = y.int32
