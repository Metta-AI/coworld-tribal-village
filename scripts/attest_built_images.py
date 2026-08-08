#!/usr/bin/env python3
"""Record the local Docker content hash for every built runnable image."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def image_references(value: object) -> set[str]:
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found.update(image_references(item))
        return found
    if not isinstance(value, dict):
        return set()
    found = {value["image"]} if isinstance(value.get("image"), str) else set()
    for item in value.values():
        found.update(image_references(item))
    return found


def image_id(image: str) -> str:
    return subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    attestation = {
        image: image_id(image) for image in sorted(image_references(manifest))
    }
    if not attestation:
        raise SystemExit("manifest contains no runnable images")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(attestation, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
