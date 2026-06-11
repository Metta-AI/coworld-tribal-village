# Repository Guidelines

## Project Structure & Module Organization

- Core Nim: `tribal_village.nim` (entry), `src/` for modules like `environment.nim`, `ai.nim`, `renderer.nim`,
  `tribal_village_interface.nim`.
- Python wrapper: `tribal_village_env/` with `environment.py` loading the shared library.
- Assets/data: `data/`.
- Packaging/build: `tribal_village.nimble` (for deps/locking), `pyproject.toml`, `setup.py`, `MANIFEST.in`.

## Build, Test, and Development Commands

- Install Nim deps: `nimby sync -g nimby.lock`
- Run standalone game: `nim r -d:release tribal_village.nim`
- Build shared lib for Python: `nimble buildLib`, or rely on `tribal_village_env/build.py`
  (`ensure_nim_library_current`), which rebuilds when Nim sources change and copies the library to
  `tribal_village_env/libtribal_village.{so,dylib,dll}`. The CLI and `pip install -e .` run it automatically.
- Quick Python smoke test: `python -c "from tribal_village_env import TribalVillageEnv; TribalVillageEnv()"`
- Editable install: `pip install -e .`

## Coding Style & Naming Conventions

- Nim: 2-space indent; modules `snake_case.nim`; procs/vars `lowerCamelCase`; types/consts `PascalCase`; export with
  trailing `*`. Prefer small, focused procs; avoid global state.
- Python: PEP 8 + type hints; modules `snake_case.py`; classes `PascalCase`; functions `snake_case`.
- Formatting: run `nimpretty src` for Nim. Use `black` for Python if available.

## Testing Guidelines

- Coworld runtime smoke test: `python tests/smoke_coworld_runtime.py` (exercises the server, builtin-AI player,
  and replay paths end to end; silent with exit code 0 on success).
- Manual smoke checks before PRs:
  - Nim: run `nim r tribal_village.nim` and verify basic interaction.
  - Python: instantiate `TribalVillageEnv()` and run a few `step`s.
- If adding Python tests, place under `tests/` as `test_*.py` (pytest style) or standalone `smoke_*.py` scripts.

## Commit & Pull Request Guidelines

- Commits: short, imperative subject (≤72 chars), optional scope, meaningful body when changing behavior or performance.
- PRs: include purpose, key changes, perf/behavior notes, and reproduction steps. Link issues. Add screenshots for UI
  changes or brief metrics for performance work.
- Keep diffs surgical; avoid unrelated refactors.

## Security & Configuration Tips

- The Python wrapper loads `tribal_village_env/libtribal_village.{so,dylib,dll}`; ensure the library exists and
  matches your platform (`tribal_village_env/build.py` rebuilds it when Nim sources change).
- Requires Nim 2.2.10+ and OpenGL for rendering. Python: 3.12.x with `numpy`; install the `pufferlib` extra for
  `TribalVillageEnv` and the `coworld` extra for the local server.
