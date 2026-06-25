from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_NIM_VERSION = os.environ.get("TRIBAL_VILLAGE_NIM_VERSION", "2.2.10")
DEFAULT_NIMBY_VERSION = os.environ.get("TRIBAL_VILLAGE_NIMBY_VERSION", "0.1.27")


def _target_library_name() -> str:
    system = platform.system()
    if system == "Darwin":
        return "libtribal_village.dylib"
    if system == "Windows":
        return "libtribal_village.dll"
    return "libtribal_village.so"


def _collect_source_files(project_root: Path) -> list[Path]:
    nim_sources = list(project_root.rglob("*.nim"))
    return nim_sources + [
        project_root / "tribal_village.nim",
        project_root / "tribal_village.nimble",
        project_root / "nimby.lock",
    ]


def _collect_wasm_source_files(project_root: Path) -> list[Path]:
    data_files = [path for path in (project_root / "data").rglob("*") if path.is_file()]
    return _collect_source_files(project_root) + [
        project_root / "scripts" / "shell_minimal.html",
        *data_files,
    ]


def _latest_mtime(paths: Iterable[Path]) -> Optional[float]:
    mtimes = [path.stat().st_mtime for path in paths if path.exists()]
    if not mtimes:
        return None
    return max(mtimes)


def _build_library(project_root: Path) -> Path:
    _ensure_nim_toolchain()
    _install_nim_deps(project_root)

    ext = Path(_target_library_name()).suffix
    cmd = [
        "nim",
        "c",
        "--app:lib",
        "--mm:arc",
        "--opt:speed",
        "-d:danger",
        f"--out:libtribal_village{ext}",
        "src/tribal_village_interface.nim",
    ]
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)

    if result.returncode != 0:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        raise RuntimeError(
            f"Failed to build Nim library (exit {result.returncode}). stdout: {stdout} stderr: {stderr}"
        )

    built_lib = project_root / _target_library_name()
    if built_lib.exists():
        return built_lib

    raise RuntimeError(f"Build completed but {built_lib.name} not found.")


def ensure_nim_library_current(verbose: bool = True) -> Path:
    """Rebuild libtribal_village if missing or stale."""

    package_dir = Path(__file__).resolve().parent
    project_root = package_dir.parent
    target_name = _target_library_name()
    target_path = package_dir / target_name

    source_files = _collect_source_files(project_root)
    latest_source_mtime = _latest_mtime(source_files)
    lib_mtime: Optional[float] = (
        target_path.stat().st_mtime if target_path.exists() else None
    )

    needs_rebuild = lib_mtime is None or (
        latest_source_mtime is not None and lib_mtime < latest_source_mtime
    )

    if not needs_rebuild:
        return target_path

    if verbose:
        print("Building Tribal Village Nim library to keep bindings current...")

    built_lib = _build_library(project_root)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_lib, target_path)

    if verbose:
        print(f"Copied {built_lib} to {target_path}")

    return target_path


def _build_wasm_bundle(project_root: Path) -> Path:
    _ensure_nim_toolchain()
    _install_nim_deps(project_root)

    if shutil.which("emcc") is None:
        raise RuntimeError(
            "emcc not found. Install Emscripten to build Tribal Village WASM."
        )

    output_html = project_root / "build" / "web" / "tribal_village.html"
    output_html.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "nim",
        "c",
        "--app:gui",
        "--threads:off",
        "--gc:arc",
        "--exceptions:goto",
        "--define:noSignalHandler",
        "--os:linux",
        "--cpu:wasm32",
        "--cc:clang",
        "--clang.exe:emcc",
        "--clang.linkerexe:emcc",
        "--nimcache:build/web/nimcache",
        "--listCmd",
        "-d:release",
        "-d:emscripten",
        "-d:nimNoDevRandom",
        "-d:nimNoGetRandom",
        "-d:nimNoSysrand",
        f"--out:{output_html}",
        "--passL:--shell-file=scripts/shell_minimal.html",
        "--passL:--embed-file data",
        "--passL:-sUSE_GLFW=3",
        "--passL:-sUSE_WEBGL2=1",
        "--passL:-sASYNCIFY",
        "--passL:-sALLOW_MEMORY_GROWTH",
        "--passL:-sINITIAL_MEMORY=512MB",
        "--passL:-sFULL_ES3=1",
        "--passL:-sERROR_ON_UNDEFINED_SYMBOLS=0",
        "tribal_village.nim",
    ]
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
    if result.returncode != 0:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        raise RuntimeError(
            f"Failed to build Tribal Village WASM (exit {result.returncode}). stdout: {stdout} stderr: {stderr}"
        )

    _remove_stale_wasm_bundle_outputs(project_root)
    for output in _wasm_bundle_outputs(project_root):
        if not output.exists():
            raise RuntimeError(f"WASM build completed but {output.name} not found.")
    return output_html


def _wasm_bundle_outputs(project_root: Path) -> list[Path]:
    web_dir = project_root / "build" / "web"
    return [
        web_dir / "tribal_village.html",
        web_dir / "tribal_village.js",
        web_dir / "tribal_village.wasm",
    ]


def _remove_stale_wasm_bundle_outputs(project_root: Path) -> None:
    for output in [project_root / "build" / "web" / "tribal_village.data"]:
        if output.exists():
            output.unlink()


def ensure_wasm_bundle_current(verbose: bool = True) -> Path:
    """Rebuild the browser replay bundle if missing or stale."""

    package_dir = Path(__file__).resolve().parent
    project_root = package_dir.parent
    _remove_stale_wasm_bundle_outputs(project_root)
    outputs = _wasm_bundle_outputs(project_root)

    source_files = _collect_wasm_source_files(project_root)
    latest_source_mtime = _latest_mtime(source_files)
    output_mtimes = [output.stat().st_mtime for output in outputs if output.exists()]
    needs_rebuild = len(output_mtimes) != len(outputs) or (
        latest_source_mtime is not None and min(output_mtimes) < latest_source_mtime
    )

    if not needs_rebuild:
        return outputs[0]

    if verbose:
        print("Building Tribal Village Emscripten replay bundle...")

    html_path = _build_wasm_bundle(project_root)

    if verbose:
        print(f"Built {html_path}")

    return html_path


def _ensure_nim_toolchain() -> None:
    """Ensure nimby is available and installs the requested Nim version."""

    nimby_path = shutil.which("nimby")

    system = platform.system()
    arch = platform.machine().lower()
    if nimby_path is None:
        if system == "Linux":
            url = f"https://github.com/treeform/nimby/releases/download/{DEFAULT_NIMBY_VERSION}/nimby-Linux-X64"
        elif system == "Darwin":
            suffix = "ARM64" if "arm" in arch else "X64"
            url = f"https://github.com/treeform/nimby/releases/download/{DEFAULT_NIMBY_VERSION}/nimby-macOS-{suffix}"
        else:
            raise RuntimeError(f"Unsupported OS for nimby bootstrap: {system}")

        dst = Path.home() / ".nimby" / "nim" / "bin" / "nimby"
        with tempfile.TemporaryDirectory() as tmp:
            nimby_dl = Path(tmp) / "nimby"
            urllib.request.urlretrieve(url, nimby_dl)
            nimby_dl.chmod(nimby_dl.stat().st_mode | stat.S_IEXEC)
            subprocess.check_call([str(nimby_dl), "use", DEFAULT_NIM_VERSION])

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(nimby_dl, dst)

        nimby_path = str(dst)

    nim_bin_dir = Path.home() / ".nimby" / "nim" / "bin"
    os.environ["PATH"] = f"{nim_bin_dir}{os.pathsep}" + os.environ.get("PATH", "")

    if shutil.which("nim") is None:
        subprocess.check_call([nimby_path, "use", DEFAULT_NIM_VERSION])

    if shutil.which("nim") is None:
        raise RuntimeError("Failed to provision nim via nimby.")


def _install_nim_deps(project_root: Path) -> None:
    """Install Nim deps via nimby lockfile."""

    nimby = shutil.which("nimby")
    if nimby is None:
        raise RuntimeError("nimby not found after setup.")

    lockfile = project_root / "nimby.lock"
    if not lockfile.exists():
        raise RuntimeError(f"nimby.lock missing at {lockfile}")

    nim_cfg = project_root / "nim.cfg"
    if nim_cfg.exists():
        nim_cfg.unlink()

    result = subprocess.run(
        [nimby, "sync", "-g", str(lockfile)],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        raise RuntimeError(
            f"nimby sync failed (exit {result.returncode}). stdout: {stdout} stderr: {stderr}"
        )
