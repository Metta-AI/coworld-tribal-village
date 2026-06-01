"""Python package exports for Tribal Village."""

from tribal_village_env.build import ensure_nim_library_current

__all__ = ["TribalVillageEnv", "make_tribal_village_env", "ensure_nim_library_current"]


def __getattr__(name):
    if name in {"TribalVillageEnv", "make_tribal_village_env"}:
        from tribal_village_env.environment import (
            TribalVillageEnv,
            make_tribal_village_env,
        )

        return {
            "TribalVillageEnv": TribalVillageEnv,
            "make_tribal_village_env": make_tribal_village_env,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
