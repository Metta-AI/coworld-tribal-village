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
DEFAULT_WINDOW_RADIUS = 5


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
    server image. Coworld players receive rendered sprite windows and can choose
    their own training stack outside the game container.
    """

    def __init__(
        self,
        *,
        max_steps: int,
        render_scale: int = 1,
        window_radius: int = DEFAULT_WINDOW_RADIUS,
        config: dict[str, Any] | None = None,
    ) -> None:
        ensure_nim_library_current(verbose=False)
        self.max_steps = int(max_steps)
        self.render_scale = max(1, int(render_scale))
        self.window_radius = max(1, int(window_radius))
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
        self._rgb_frame = np.zeros(
            (
                self.map_height * self.render_scale,
                self.map_width * self.render_scale,
                3,
            ),
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
            ("tribal_village_reset_builtin_ai", [ctypes.c_int32], ctypes.c_int32),
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
                "tribal_village_render_rgb",
                [
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_int32,
                    ctypes.c_int32,
                ],
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
        ok = self.lib.tribal_village_reset_builtin_ai(ctypes.c_int32(max(1, seed)))
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

    def render_frame(self) -> np.ndarray:
        ok = self.lib.tribal_village_render_rgb(
            self.env_ptr,
            self._rgb_frame.ctypes.data_as(ctypes.c_void_p),
            int(self._rgb_frame.shape[1]),
            int(self._rgb_frame.shape[0]),
        )
        if ok != 1:
            raise RuntimeError("Failed to render Nim RGB frame")
        return self._rgb_frame

    def frame_payload(self) -> dict[str, Any]:
        frame = self.render_frame()
        return {
            "kind": "rgb",
            "width": int(frame.shape[1]),
            "height": int(frame.shape[0]),
            "data": frame.reshape(-1).tolist(),
        }

    def agent_position(self, slot: int) -> tuple[int, int]:
        x = int(self.lib.tribal_village_get_agent_x(self.env_ptr, int(slot)))
        y = int(self.lib.tribal_village_get_agent_y(self.env_ptr, int(slot)))
        return x, y

    def player_view(self, slot: int) -> dict[str, Any]:
        frame = self.render_frame()
        center_x, center_y = self.agent_position(slot)
        tile_size = self.render_scale
        tiles = self.window_radius * 2 + 1
        width = tiles * tile_size
        height = tiles * tile_size
        out = np.zeros((height, width, 3), dtype=np.uint8)
        src_x0 = (center_x - self.window_radius) * tile_size
        src_y0 = (center_y - self.window_radius) * tile_size

        for y in range(height):
            src_y = src_y0 + y
            if src_y < 0 or src_y >= frame.shape[0]:
                continue
            for x in range(width):
                src_x = src_x0 + x
                if src_x < 0 or src_x >= frame.shape[1]:
                    continue
                out[y, x] = frame[src_y, src_x]

        return {
            "kind": "rgb_window",
            "width": width,
            "height": height,
            "tile_width": tiles,
            "tile_height": tiles,
            "tile_size": tile_size,
            "radius": self.window_radius,
            "center": {"x": center_x, "y": center_y},
            "data": out.reshape(-1).tolist(),
        }

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
