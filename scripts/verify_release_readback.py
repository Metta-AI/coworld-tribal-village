#!/usr/bin/env python3
"""Verify that an uploaded Coworld is the exact canonical certified release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_exact_canonical(rows: Any, *, name: str, version: str) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("Coworld list response must be a JSON array")
    matches = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("name") == name
        and row.get("version") == version
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one {name}:{version} readback, found {len(matches)}"
        )
    match = matches[0]
    if match.get("canonical") is not True:
        raise ValueError(f"{name}:{version} is not canonical")
    coworld_id = match.get("id")
    if not isinstance(coworld_id, str) or not coworld_id:
        raise ValueError(f"{name}:{version} has no Coworld ID")
    return match


def _runnable_fields(
    value: object, path: tuple[str, ...] = ()
) -> dict[tuple[str, ...], dict[str, object]]:
    found: dict[tuple[str, ...], dict[str, object]] = {}
    if isinstance(value, list):
        for index, item in enumerate(value):
            found.update(_runnable_fields(item, path + (str(index),)))
    elif isinstance(value, dict):
        if isinstance(value.get("image"), str):
            found[path] = value
        for key, item in value.items():
            found.update(_runnable_fields(item, path + (key,)))
    return found


def verify_artifact_readback(
    expected_manifest: object,
    stored_manifest: object,
    built_images: object,
    image_listing: object,
) -> None:
    if not isinstance(expected_manifest, dict) or not isinstance(stored_manifest, dict):
        raise ValueError("built and stored manifests must be JSON objects")
    if not isinstance(built_images, dict):
        raise ValueError("built image attestation must be a JSON object")
    if not isinstance(image_listing, list):
        raise ValueError("Coworld image listing must be a JSON array")

    expected = _runnable_fields(expected_manifest)
    stored = _runnable_fields(stored_manifest)
    if not expected or set(expected) != set(stored):
        raise ValueError("stored manifest runnable topology differs from built manifest")

    for path, expected_runnable in expected.items():
        stored_runnable = stored[path]
        label = "/".join(path)
        if stored_runnable.get("source_url") != expected_runnable.get("source_url"):
            raise ValueError(f"stored source ref differs at {label}")
        local_image = str(expected_runnable["image"])
        expected_hash = built_images.get(local_image)
        if not isinstance(expected_hash, str) or not expected_hash:
            raise ValueError(f"no local image attestation for {local_image}")
        stored_image = stored_runnable.get("image")
        if not isinstance(stored_image, str) or "@sha256:" not in stored_image:
            raise ValueError(f"stored runnable has no immutable image at {label}")
        matches = [
            item
            for item in image_listing
            if isinstance(item, dict) and item.get("public_image_uri") == stored_image
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one uploaded image for {stored_image}, "
                f"found {len(matches)}"
            )
        details = matches[0]
        if details.get("client_hash") != expected_hash:
            raise ValueError(f"uploaded image content differs at {label}")
        if details.get("status") != "published" or not details.get("image_digest"):
            raise ValueError(f"uploaded image is not published at {label}")


def verify_release_readback(rows: Any, status: Any, *, name: str, version: str) -> str:
    match = resolve_exact_canonical(rows, name=name, version=version)
    if not isinstance(status, dict):
        raise ValueError("Coworld status response must be a JSON object")

    coworld = status.get("coworld")
    if not isinstance(coworld, dict):
        raise ValueError("Coworld status response has no coworld object")
    expected = {
        "id": match["id"],
        "name": name,
        "version": version,
    }
    actual = {key: coworld.get(key) for key in expected}
    if actual != expected:
        raise ValueError(f"status Coworld mismatch: expected {expected}, got {actual}")
    # Some deployed API/CLI combinations omit these list-only fields from the
    # status payload. When status includes the hash, require it to agree.
    status_manifest_hash = coworld.get("manifest_hash")
    if status_manifest_hash is not None and status_manifest_hash != match.get(
        "manifest_hash"
    ):
        raise ValueError("list and status manifest hashes do not match")

    episodes = status.get("hosted_smoke_episodes")
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("no hosted smoke episodes found")
    failed_episodes = [
        episode
        for episode in episodes
        if not isinstance(episode, dict)
        or episode.get("status") != "completed"
        or episode.get("error") is not None
    ]
    if failed_episodes:
        raise ValueError(f"hosted smoke is not clean: {failed_episodes}")

    certification = status.get("certification")
    if not isinstance(certification, dict):
        raise ValueError("hosted certification status is missing")
    if certification.get("coworld_id") != match["id"]:
        raise ValueError("hosted certification belongs to a different Coworld")
    if (
        certification.get("state") != "certified"
        or certification.get("certified") is not True
    ):
        raise ValueError(
            "hosted certification did not finish certified: "
            f"state={certification.get('state')!r}"
        )
    if not certification.get("contract_version"):
        raise ValueError("hosted certification has no contract version")
    transcript = certification.get("transcript_summary")
    if not isinstance(transcript, list) or not transcript:
        raise ValueError("hosted certification transcript is empty")
    nonpassing_steps = [
        step
        for step in transcript
        if not isinstance(step, dict) or step.get("status") != "pass"
    ]
    if nonpassing_steps:
        raise ValueError(
            f"hosted certification has non-passing steps: {nonpassing_steps}"
        )

    return (
        f"{name}:{version} is canonical and certified "
        f"({match['id']}, {certification['contract_version']}, "
        f"{len(episodes)} hosted smoke episodes)"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("resolve", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--list-json", type=Path, required=True)
        subparser.add_argument("--name", required=True)
        subparser.add_argument("--version", required=True)
        if command == "verify":
            subparser.add_argument("--status-json", type=Path, required=True)
            subparser.add_argument("--manifest-json", type=Path, required=True)
            subparser.add_argument("--built-images-json", type=Path, required=True)
            subparser.add_argument("--images-json", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    rows = _load_json(args.list_json)
    try:
        match = resolve_exact_canonical(rows, name=args.name, version=args.version)
        if args.command == "resolve":
            print(match["id"])
            return
        status = _load_json(args.status_json)
        coworld = status.get("coworld") if isinstance(status, dict) else None
        stored_manifest = coworld.get("manifest") if isinstance(coworld, dict) else None
        if not isinstance(stored_manifest, dict):
            raise ValueError("status readback has no stored manifest")
        verify_artifact_readback(
            _load_json(args.manifest_json),
            stored_manifest,
            _load_json(args.built_images_json),
            _load_json(args.images_json),
        )
        print(
            verify_release_readback(rows, status, name=args.name, version=args.version)
        )
    except ValueError as error:
        raise SystemExit(f"::error::{error}") from error


if __name__ == "__main__":
    main()
