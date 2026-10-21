"""Execute real native/WASM public exports; no simulator mock or golden update.

Set TRIBAL_NATIVE_PROBE, TRIBAL_WASM_PROBE, TRIBAL_NODE and TRIBAL_PARITY_OUTPUT
to explicit compiled inputs and a new retained evidence directory.
"""

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from tribal_village_env.coworld.observer import ObserverSnapshot


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_public(native, wasm):
    names = sorted(p.name for p in native.iterdir())
    assert names == sorted(p.name for p in wasm.iterdir())
    for name in names:
        a, b = native / name, wasm / name
        if a.suffix == ".json":
            assert json.loads(a.read_text()) == json.loads(b.read_text()), name
        else:
            assert a.read_bytes() == b.read_bytes(), name


@pytest.fixture(scope="module")
def binaries():
    names = [
        "TRIBAL_NATIVE_PROBE",
        "TRIBAL_WASM_PROBE",
        "TRIBAL_NODE",
        "TRIBAL_PARITY_OUTPUT",
    ]
    if any(name not in os.environ for name in names):
        pytest.skip("explicit compiled native/WASM probes and evidence path required")
    native, wasm, node, output = [Path(os.environ[name]).resolve() for name in names]
    for path in (native, wasm, wasm.with_suffix(".wasm"), node):
        assert path.is_file(), path
    output.mkdir(parents=True, exist_ok=False)
    exports = subprocess.check_output(
        [
            str(node),
            "-e",
            "const fs=require('fs');const m=new WebAssembly.Module(fs.readFileSync(process.argv[1]));"
            "console.log(JSON.stringify(WebAssembly.Module.exports(m)));",
            str(wasm.with_suffix(".wasm")),
        ],
        text=True,
    )
    (output / "wasm-exports.json").write_text(exports)
    exported = {item["name"] for item in json.loads(exports)}
    assert "tribal_village_export_world_cells" in exported
    assert "tribal_village_step_for_coworld" in exported
    assert not any(
        "training" in name or "get_obs" in name or "with_pointers" in name
        for name in exported
    )
    manifest = {
        str(p): digest(p) for p in (native, wasm, wasm.with_suffix(".wasm"), node)
    }
    (output / "binaries.json").write_text(json.dumps(manifest, indent=2))
    return [str(native)], [str(node), str(wasm)], output


def run(command, log, *, accepted=True, error=None):
    result = subprocess.run(command, capture_output=True, timeout=30)
    log.write_bytes(result.stdout + result.stderr)
    log.with_suffix(".command.json").write_text(
        json.dumps(
            {
                "command": command,
                "exit": result.returncode,
            },
            indent=2,
        )
    )
    assert (result.returncode == 0) == accepted, result.stderr.decode(errors="replace")
    if error is not None:
        assert error.encode() in result.stderr, result.stderr.decode(errors="replace")


@pytest.mark.parametrize("teams,seed", [(2, 17), (2, 52), (8, 17), (8, 52)])
def test_full_public_replay_and_boundaries(binaries, teams, seed):
    native, wasm, root = binaries
    case = root / f"teams-{teams}-seed-{seed}"
    case.mkdir()
    replay = case / "replay.json"
    run(native + ["record", str(seed), str(teams), str(replay)], case / "record.log")
    for name, command in (("native", native), ("wasm", wasm)):
        run(command + ["replay", str(replay), str(case / name)], case / f"{name}.log")
    compare_public(case / "native", case / "wasm")
    assert (case / "native/64.bin").read_bytes() != (case / "native/0.bin").read_bytes()
    controls = json.loads((case / "native/controls.json").read_text())
    assert controls == {
        "config_bytes": 68,
        "width": 196,
        "height": 112,
        "stride": 28,
        "saturation": True,
        "private_exclusion": True,
        "invalid_abi": True,
        "reset": True,
        "terminal_tick": 64,
    }
    for tick in range(65):
        raw = (case / f"native/{tick}.bin").read_bytes()
        assert len(raw) == 196 * 112 * 28
        agents = [raw[i : i + 28] for i in range(0, len(raw), 28) if raw[i + 4] == 0]
        ids = [agent[6] for agent in agents]
        assert len(ids) == len(set(ids))
        assert all(
            agent[6] < teams * 6 and agent[7] == agent[6] // 6 for agent in agents
        )
        if tick == 0:
            assert sorted(ids) == list(range(teams * 6))
    trace = json.loads((case / "native/trace.json").read_text())
    assert [row["tick"] for row in trace] == list(range(1, 65))
    assert any(trace[-1]["truncations"])
    metadata = {
        "kind": "tribal-village-sprite-cells-v2",
        "encoding": "uint8-arraybuffer",
        "width": controls["width"],
        "height": controls["height"],
        "stride": 28,
    }
    snapshots = []
    for target in ("native", "wasm"):
        snapshot = ObserverSnapshot.from_sprite_frame(
            64, metadata, (case / target / "64.bin").read_bytes()
        ).payload()
        snapshots.append(snapshot)
        (case / f"{target}-observer.json").write_text(
            json.dumps(snapshot, sort_keys=True)
        )
    assert snapshots[0] == snapshots[1]
    hashes = {
        str(p.relative_to(case)): digest(p)
        for p in sorted(case.rglob("*"))
        if p.is_file()
    }
    (case / "hashes.json").write_text(json.dumps(hashes, indent=2))


def test_malformed_replays_do_not_create_public_output(binaries):
    native, wasm, root = binaries
    case = root / "malformed"
    case.mkdir()
    good = {
        "schema": "tribal-village-replay-v2",
        "initial": {"seed": 17, "team_count": 2, "max_steps": 64},
        "ticks": [{"a": base64.b64encode(bytes(12)).decode()} for _ in range(64)],
    }
    variants = []
    for field, value in (("seed", 0), ("team_count", 9), ("max_steps", 65)):
        invalid = copy.deepcopy(good)
        invalid["initial"][field] = value
        variants.append((field, invalid))
    for length in (63, 65):
        invalid = copy.deepcopy(good)
        invalid["ticks"] = (invalid["ticks"] * 2)[:length]
        variants.append((f"ticks-{length}", invalid))
    for name, actions in (
        ("short-roster", bytes(11)),
        ("long-roster", bytes(13)),
        ("invalid-action", bytes([64]) + bytes(11)),
    ):
        invalid = copy.deepcopy(good)
        invalid["ticks"][0]["a"] = base64.b64encode(actions).decode()
        variants.append((name, invalid))
    for name, payload in variants:
        path = case / f"{name}.json"
        path.write_text(json.dumps(payload))
        for target, command in (("native", native), ("wasm", wasm)):
            output = case / f"{name}-{target}"
            run(
                command + ["replay", str(path), str(output)],
                case / f"{name}-{target}.log",
                accepted=False,
                error={
                    "seed": "invalid seed",
                    "team_count": "fixture roster",
                    "max_steps": "invalid replay boundary",
                    "ticks-63": "invalid replay boundary",
                    "ticks-65": "invalid replay boundary",
                    "short-roster": "invalid action roster",
                    "long-roster": "invalid action roster",
                    "invalid-action": "invalid action code",
                }[name],
            )
            assert not output.exists()


def test_comparison_rejects_a_changed_public_identity(tmp_path):
    native, wasm = tmp_path / "native", tmp_path / "wasm"
    native.mkdir()
    wasm.mkdir()
    original = bytes([0, 1, 2, 3, 0, 0, 5, 0] + [0] * 20)
    (native / "0.bin").write_bytes(original)
    (wasm / "0.bin").write_bytes(original)
    compare_public(native, wasm)
    changed = bytearray(original)
    changed[6] = 6
    (wasm / "0.bin").write_bytes(changed)
    with pytest.raises(AssertionError, match="0.bin"):
        compare_public(native, wasm)
