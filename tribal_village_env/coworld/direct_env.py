from __future__ import annotations

import ctypes
import math
import platform
from pathlib import Path
from typing import Any

import numpy as np

from tribal_village_env.build import ensure_nim_library_current

ACTION_VERB_COUNT = 8
ACTION_ARGUMENT_COUNT = 8
ACTION_SPACE_SIZE = ACTION_VERB_COUNT * ACTION_ARGUMENT_COUNT
COWORLD_SPRITE_FRAME_KIND = "tribal-village-sprite-cells-v1"
CELL_STRIDE = 24
TERRAIN_LABELS = ["empty", "water", "bridge", "wheat", "tree", "fertile"]
THING_LABELS = [
    "agent",
    "wall",
    "mine",
    "converter",
    "assembler",
    "spawner",
    "tumor",
    "armory",
    "forge",
    "clay_oven",
    "weaving_loom",
    "planted_lantern",
]
TEAM_COLORS = [
    "#e86b6b",
    "#f0a86b",
    "#f0d56b",
    "#99d680",
    "#c763e0",
    "#6ab8f0",
    "#dedede",
    "#ed8fd1",
]


class NimConfig(ctypes.Structure):
    _fields_ = [
        ("max_steps", ctypes.c_int32),
        ("seed", ctypes.c_int32),
        ("tumor_spawn_rate", ctypes.c_float),
        ("heart_reward", ctypes.c_float),
        ("ore_reward", ctypes.c_float),
        ("battery_reward", ctypes.c_float),
        ("wood_reward", ctypes.c_float),
        ("water_reward", ctypes.c_float),
        ("wheat_reward", ctypes.c_float),
        ("spear_reward", ctypes.c_float),
        ("armor_reward", ctypes.c_float),
        ("food_reward", ctypes.c_float),
        ("cloth_reward", ctypes.c_float),
        ("tumor_kill_reward", ctypes.c_float),
        ("survival_penalty", ctypes.c_float),
        ("death_penalty", ctypes.c_float),
    ]


class CoworldTribalVillageEnv:
    """Small ctypes wrapper for Coworld runtime.

    This avoids importing the PufferLib/Gymnasium training wrapper in the game
    server image. Coworld visuals use the native full-map sprite-cell export;
    Coworld players receive action observations on a separate route.
    """

    def __init__(
        self,
        *,
        max_steps: int,
        config: dict[str, Any] | None = None,
    ) -> None:
        ensure_nim_library_current(verbose=False)
        self.max_steps = int(max_steps)
        self.config = config or {}
        self.lib = ctypes.CDLL(str(_library_path()))
        self._setup_ctypes_interface()

        self.num_agents = int(self.lib.tribal_village_get_num_agents())
        self.map_width = int(self.lib.tribal_village_get_map_width())
        self.map_height = int(self.lib.tribal_village_get_map_height())
        self.actions = np.zeros(self.num_agents, dtype=np.uint8)
        self.rewards = np.zeros(self.num_agents, dtype=np.float32)
        self.terminals = np.zeros(self.num_agents, dtype=np.uint8)
        self.truncations = np.zeros(self.num_agents, dtype=np.uint8)
        self._world_cells = np.zeros(
            self.map_width * self.map_height * CELL_STRIDE,
            dtype=np.uint8,
        )
        self.env_ptr = self.lib.tribal_village_create()
        if not self.env_ptr:
            raise RuntimeError("Failed to create Nim environment")
        self._apply_config()
        self.step_count = 0

    def _setup_ctypes_interface(self) -> None:
        config_ptr = ctypes.POINTER(NimConfig)
        func_specs = [
            ("tribal_village_create", [], ctypes.c_void_p),
            (
                "tribal_village_set_config",
                [ctypes.c_void_p, config_ptr],
                ctypes.c_int32,
            ),
            (
                "tribal_village_reset_for_coworld",
                _buffers_without_actions(),
                ctypes.c_int32,
            ),
            (
                "tribal_village_step_for_coworld",
                [
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ],
                ctypes.c_int32,
            ),
            (
                "tribal_village_reset_builtin_ai",
                [ctypes.c_void_p, ctypes.c_int32],
                ctypes.c_int32,
            ),
            (
                "tribal_village_builtin_ai_actions",
                [ctypes.c_void_p, ctypes.c_void_p],
                ctypes.c_int32,
            ),
            ("tribal_village_destroy", [ctypes.c_void_p], None),
            ("tribal_village_get_num_agents", [], ctypes.c_int32),
            ("tribal_village_get_map_width", [], ctypes.c_int32),
            ("tribal_village_get_map_height", [], ctypes.c_int32),
            (
                "tribal_village_get_agent_x",
                [ctypes.c_void_p, ctypes.c_int32],
                ctypes.c_int32,
            ),
            (
                "tribal_village_get_agent_y",
                [ctypes.c_void_p, ctypes.c_int32],
                ctypes.c_int32,
            ),
            (
                "tribal_village_export_world_cells",
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32],
                ctypes.c_int32,
            ),
        ]
        for name, argtypes, restype in func_specs:
            func = getattr(self.lib, name)
            func.argtypes = argtypes
            if restype is not None:
                func.restype = restype

    def _apply_config(self) -> None:
        cfg = NimConfig(
            max_steps=self.max_steps,
            seed=int(self.config.get("seed", 0)),
            tumor_spawn_rate=self._nim_float("tumor_spawn_rate"),
            heart_reward=self._nim_float("heart_reward"),
            ore_reward=self._nim_float("ore_reward"),
            battery_reward=self._nim_float("battery_reward"),
            wood_reward=self._nim_float("wood_reward"),
            water_reward=self._nim_float("water_reward"),
            wheat_reward=self._nim_float("wheat_reward"),
            spear_reward=self._nim_float("spear_reward"),
            armor_reward=self._nim_float("armor_reward"),
            food_reward=self._nim_float("food_reward"),
            cloth_reward=self._nim_float("cloth_reward"),
            tumor_kill_reward=self._nim_float("tumor_kill_reward"),
            survival_penalty=self._nim_float("survival_penalty"),
            death_penalty=self._nim_float("death_penalty"),
        )
        ok = self.lib.tribal_village_set_config(self.env_ptr, ctypes.byref(cfg))
        if ok != 1:
            raise RuntimeError("Failed to apply Nim environment config")

    def _nim_float(self, key: str) -> float:
        value = self.config.get(key)
        if value is None:
            return math.nan
        return float(value)

    def reset(self) -> None:
        self.step_count = 0
        ok = self.lib.tribal_village_reset_for_coworld(
            self.env_ptr,
            self.rewards.ctypes.data_as(ctypes.c_void_p),
            self.terminals.ctypes.data_as(ctypes.c_void_p),
            self.truncations.ctypes.data_as(ctypes.c_void_p),
        )
        if ok != 1:
            raise RuntimeError("Failed to reset Nim environment")

    def step(self, actions: list[int]) -> None:
        self.actions.fill(0)
        for slot, action in enumerate(actions[: self.num_agents]):
            if 0 <= int(action) < ACTION_SPACE_SIZE:
                self.actions[slot] = np.uint8(action)
        ok = self.lib.tribal_village_step_for_coworld(
            self.env_ptr,
            self.actions.ctypes.data_as(ctypes.c_void_p),
            self.rewards.ctypes.data_as(ctypes.c_void_p),
            self.terminals.ctypes.data_as(ctypes.c_void_p),
            self.truncations.ctypes.data_as(ctypes.c_void_p),
        )
        if ok != 1:
            raise RuntimeError("Failed to step Nim environment")
        self.step_count += 1

    def reset_builtin_ai(self, seed: int = 1) -> None:
        ok = self.lib.tribal_village_reset_builtin_ai(
            self.env_ptr,
            ctypes.c_int32(max(1, seed)),
        )
        if ok != 1:
            raise RuntimeError("Failed to reset Nim built-in AI")

    def builtin_ai_actions(self) -> list[int]:
        ok = self.lib.tribal_village_builtin_ai_actions(
            self.env_ptr,
            self.actions.ctypes.data_as(ctypes.c_void_p),
        )
        if ok != 1:
            raise RuntimeError("Failed to compute Nim built-in AI actions")
        return [int(action) for action in self.actions.tolist()]

    def sprite_frame(self) -> tuple[dict[str, Any], bytes]:
        ok = self.lib.tribal_village_export_world_cells(
            self.env_ptr,
            self._world_cells.ctypes.data_as(ctypes.c_void_p),
            int(self._world_cells.size),
        )
        if ok != 1:
            raise RuntimeError("Failed to export Nim Coworld cell frame")
        return {
            "kind": COWORLD_SPRITE_FRAME_KIND,
            "encoding": "uint8-arraybuffer",
            "width": self.map_width,
            "height": self.map_height,
            "stride": CELL_STRIDE,
            "terrain_labels": TERRAIN_LABELS,
            "thing_labels": THING_LABELS,
            "team_colors": TEAM_COLORS,
        }, self._world_cells.tobytes()

    def agent_position(self, slot: int) -> tuple[int, int]:
        x = int(self.lib.tribal_village_get_agent_x(self.env_ptr, int(slot)))
        y = int(self.lib.tribal_village_get_agent_y(self.env_ptr, int(slot)))
        return x, y

    def close(self) -> None:
        if getattr(self, "env_ptr", None):
            self.lib.tribal_village_destroy(self.env_ptr)
            self.env_ptr = None


def _buffers_without_actions() -> list[Any]:
    return [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]


def _library_path() -> Path:
    if platform.system() == "Darwin":
        lib_name = "libtribal_village.dylib"
    elif platform.system() == "Windows":
        lib_name = "libtribal_village.dll"
    else:
        lib_name = "libtribal_village.so"

    package_dir = Path(__file__).resolve().parents[1]
    candidate_paths = [
        package_dir.parent / lib_name,
        package_dir / lib_name,
    ]
    lib_path = next((path for path in candidate_paths if path.exists()), None)
    if lib_path is None:
        searched = ", ".join(str(path) for path in candidate_paths)
        raise FileNotFoundError(f"Nim library not found. Searched: {searched}")
    return lib_path
