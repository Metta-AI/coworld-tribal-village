"""Detached presentation snapshots of the existing public sprite protocol.

No environment, player observation, action handler or native pointer crosses this
boundary. Resource counts retain the public protocol's uint8 saturation.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ObserverSnapshot:
    tick: int
    width: int
    height: int
    cells: bytes

    @classmethod
    def from_sprite_frame(
        cls, tick: int, metadata: Mapping[str, Any], cells: bytes | bytearray
    ) -> ObserverSnapshot:
        if (
            metadata.get("kind") != "tribal-village-sprite-cells-v2"
            or metadata.get("encoding") != "uint8-arraybuffer"
            or metadata.get("stride") != 28
        ):
            raise ValueError("Expected the public sprite-cells-v2 protocol")
        width, height = metadata.get("width"), metadata.get("height")
        if any(type(n) is not int or n < 1 for n in (width, height)):
            raise ValueError("Public frame dimensions must be positive integers")
        if type(tick) is not int or tick < 0:
            raise ValueError("Public frame tick must be a nonnegative integer")
        if len(cells) != width * height * 28:
            raise ValueError("Public frame length does not match its dimensions")
        return cls(tick, width, height, bytes(cells))

    def payload(self) -> dict[str, Any]:
        """Return a serializable display copy, with no agent-input envelope."""
        return {
            "kind": "tribal-village-observer-v1",
            "tick": self.tick,
            "width": self.width,
            "height": self.height,
            "stride": 28,
            "encoding": "base64",
            "cells": base64.b64encode(self.cells).decode("ascii"),
            "cells_sha256": sha256(self.cells).hexdigest(),
        }
