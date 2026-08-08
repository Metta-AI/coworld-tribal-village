#!/usr/bin/env python3
"""Pin Tribal Village GitHub source URLs in a built manifest to git HEAD."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

REPO_PREFIXES = (
    "https://github.com/Metta-AI/coworld-tribal-village/blob/main",
    "https://github.com/Metta-AI/coworld-tribal-village/tree/main",
)


def pin(value: object, sha: str) -> object:
    if isinstance(value, dict):
        return {key: pin(item, sha) for key, item in value.items()}
    if isinstance(value, list):
        return [pin(item, sha) for item in value]
    if isinstance(value, str):
        for prefix in REPO_PREFIXES:
            if value.startswith(prefix):
                kind = "blob" if "/blob/" in prefix else "tree"
                suffix = value[len(prefix) :]
                if suffix and not suffix.startswith("/"):
                    continue
                return (
                    "https://github.com/Metta-AI/coworld-tribal-village/"
                    f"{kind}/{sha}{suffix}"
                )
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if len(sha) != 40:
        raise SystemExit("git HEAD is not a full commit SHA")
    manifest = pin(json.loads(args.manifest.read_text()), sha)
    serialized = json.dumps(manifest, indent=2) + "\n"
    if (
        "/coworld-tribal-village/blob/main" in serialized
        or "/coworld-tribal-village/tree/main" in serialized
    ):
        raise SystemExit("mutable Tribal Village source URL remains in built manifest")
    args.manifest.write_text(serialized)


if __name__ == "__main__":
    main()
