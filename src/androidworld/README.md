## AndroidWorld → Harbor Adapter

> **Status: WIP.** Task generation and oracles exist for all 116 tasks; the emulator-dependent oracle run has NOT been executed yet (requires a Linux x86_64 host with KVM, e.g. Daytona if nested virtualization is supported). No parity experiments have been run.

## Overview

AndroidWorld ([paper](https://arxiv.org/abs/2405.14573), [repo](https://github.com/google-research/android_world)) is a dynamic benchmark of **116 tasks across 20 real Android apps** (Contacts, Markor, Simple Calendar Pro, Simple SMS, Expense/Recipe apps, Joplin, OpenTracks, Retro Music, VLC, OsmAnd, Settings, Clock, Camera, ...), run on a Pixel 6 / Android 13 (API 33) emulator. Tasks are parameterized (random names, dates, numbers) and are scored programmatically from device state (SQLite/file/settings checks) or, for question-answering tasks, by comparing the agent's answer to ground truth.

This adapter has **116 tasks = every class in upstream `TaskRegistry('android_world')`** (91 state-changing tasks + 25 information-retrieval tasks). Each Harbor task is one (task class, seed) pair using the upstream suite seed scheme (`create_suite(n_task_combinations=1, seed=30)`: `seed = sha256("30_<Name>_0") mod 2^32`), so goal text and parameters are fixed and reproducible. No tasks are excluded from generation. MiniWoB tasks (a separate upstream family) are out of scope.

Adaptation changes: the agent is a terminal/CLI agent driving the phone through `adb` (AndroidWorld's native M3A/T3A agents use its Python env API instead); instruction text adds an `adb` how-to and, for question tasks, an answer file (`/workspace/answer.txt`) replacing the in-env `answer` action.

## What is AndroidWorld?

A functional Android environment + benchmark for autonomous agents from Google Research. Reward is 1.0/0.0 from each task's `is_successful(env)` (composite tasks can give 0.5). Metric: success rate.

## Adapter Features

- Task list/params exported once from upstream (pinned commit `55ddaf5e`) into `tasks.json` by `scripts/export_tasks.py`; generation itself needs no emulator.
- One self-contained Docker image per task: Android SDK + API-33 `google_apis` x86_64 AVD + upstream `android_world` (pinned), plus a small in-container daemon (`environment/aw/daemon.py`) that boots the emulator, runs the upstream `initialize_task`, and later runs the upstream `is_successful` **in the same process** (several checkers depend on state captured at init).
- Verifier = original checker (unchanged) via `tests/test.sh` -> daemon `/score`.
- Oracle = UI-free reference solutions, see below.
- Scenario 3 Parity Agent = `T3AAgent` (`import_path: androidworld.agents:T3AAgent` under `src/androidworld/agents/`), porting upstream `T3A` prompts, accessibility-tree observation formatting, and JSON action execution over `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` with pinned dated models.
- `--split full|parity`.

## Oracle coverage (important)

Upstream ships **no oracle/reference solutions**. This adapter provides a deterministic oracle for **all 116 tasks**, in three kinds (method is recorded in each task's `task.toml` tags `oracle-<method>` / `oracle-kind-<kind>`):

| Method | Tasks | What it does |
|---|---|---|
| `computed` | 25 information-retrieval tasks | answer computed from the task's ground-truth proto and written to `/workspace/answer.txt` |
| `injection` | 76 | end state written directly (adb settings/files, app SQLite DBs, GPX files, generated media files), i.e. the result of the UI work with the UI bypassed, using the same seed-fixed params |
| `ui-script` | 15 | deterministic scripted UI/automation: clock, contacts, SMS (upstream helpers), browser games (Chrome DevTools), Markor+SMS |

Per-task method/verification table and fidelity caveats: see `NOTES.md` in the workspace notes (to be moved into this README once oracle runs are done). Offline verification (`tests/offline_harness.py`, run inside the task image): 68 state-based tasks pass the REAL upstream `initialize_task -> oracle -> is_successful` loop on a fake device, and all 25 IR answers are accepted by upstream's checker. Browser, clock, contacts, SMS and OpenApp oracles can only be verified on an emulator.

## Generated Task Structure

```
androidworld/
├── {task_id}/                    # kebab-case upstream class name, e.g. markor-create-folder
│   ├── task.toml                 # name = google-research/androidworld__{task_id}
│   ├── instruction.md            # goal + adb how-to (+ answer-file note for QA tasks)
│   ├── environment/
│   │   ├── Dockerfile            # linux/amd64, Android SDK + AVD + android_world
│   │   ├── task_spec.json        # class name, seed, pickled params, oracle kind
│   │   └── aw/                   # daemon.py, client.py, oracles.py, boot.sh, entrypoint.sh
│   ├── solution/solve.sh         # oracle (calls daemon /oracle)
│   └── tests/test.sh             # calls daemon /score, writes reward
```

## Installation / Prerequisites

- Generation: `uv` + Python 3.12 only.
- Running: **Linux x86_64 host with KVM** (Docker with `/dev/kvm`, or a Daytona sandbox with nested virtualization). Apple-silicon/arm64 hosts and hosts without KVM cannot run the emulator at usable speed. Preflight: `scripts/check_emulator_host.sh [task-dir]`.
- Resources per task: ~4 CPU, 8 GB RAM, 30 GB disk. First boot installs the benchmark apps (downloads APKs) and is slow.
- `harbor lint` reports `shared-verifier` for every task. This is intentional: the verifier must query the live emulator in the agent's container, so a separate verifier environment is impossible.

## Run Evaluation / Harness

```bash
# Oracle on the full set (needs KVM host / Daytona)
cd src/androidworld
uv run androidworld --output-dir ../../datasets/androidworld --overwrite
cd ../..
harbor run -p datasets/androidworld -a oracle        # add the Daytona environment option as needed

# Single task
harbor trial start -p datasets/androidworld/system-wifi-turn-on -a oracle

# Any agent on the full set (config in src/androidworld/run_androidworld.yaml)
harbor run -c src/androidworld/run_androidworld.yaml -a <agent> -m "<model>"
```

## Usage: Create Task Directories

```bash
cd src/androidworld
uv run androidworld --output-dir ../../datasets/androidworld
```

Flags: `--output-dir`, `--limit`, `--overwrite`, `--task-ids` (kebab id or upstream class name), `--split {full,parity}`.
`parity` = deterministic stratified subset (up to 2 tasks per app family, ordered by sha256(name), 35 tasks); a proposal pending team confirmation.
To regenerate `tasks.json` from upstream: `python scripts/export_tasks.py --aw-path <android_world checkout> --out src/androidworld/tasks.json` (needs `pip install` of upstream deps and compiled protos).

## Comparison with Original Benchmark (Parity)

Not run yet (blocked on x86_64 `/dev/kvm` host; parity plan pending Harbor team sign-off). See `parity_experiment.json`.

```bash
# Harbor side (35-task --split parity subset with Scenario 3 T3AAgent)
cd src/androidworld
uv run androidworld --split parity --output-dir ../../datasets/androidworld-parity --overwrite
cd ../..
harbor run -p datasets/androidworld-parity --agent-import-path androidworld.agents:T3AAgent -m "<provider>/<pinned-dated-model-id>"

# Original upstream side (symmetric 35-task --split parity runner)
./original_parity_runner/run_parity.sh --split parity --model "<provider>/<pinned-dated-model-id>"
```

| Agent | Model | Metric | Number of Runs | Dataset Size | Original Benchmark Performance | Harbor Adapter Performance |
|-------|-------|--------|------------------|--------------|------------------------------|----------------------------|
| TBD | TBD | success rate | TBD | TBD | TBD | TBD |

## Notes & Caveats

- Untested here: emulator boot, the daemon, and browser/clock/contacts/SMS/OpenApp oracles have not been run against a live emulator (arm64 host, no KVM). Done offline: generation, `harbor lint`, image build (amd64 under qemu), and the fake-device oracle harness.
- `RecipeDeleteMultipleRecipesWithConstraint`: upstream's seed-index-0 instance is degenerate (nothing to delete), so the exporter uses seed index 1.
- Information-retrieval answers are comma-split by upstream's checker, so ground-truth strings that contain commas may not be satisfiable by anyone (including this oracle).
- Date/time is frozen to Oct 2023 by upstream setup; tasks derived from "now" at export time (e.g. `MarkorCreateFolder` folder name) are frozen in `tasks.json`.
- App APK installation happens on first boot via upstream `setup_apps` (network required); baking a snapshot into the image would speed this up.
- Each generated task includes `environment/docker-compose.yaml` (passing `/dev/kvm` and a `/ready` `healthcheck`). If `/dev/kvm` is absent, `boot.sh` fails fast unless `ANDROIDWORLD_ALLOW_TCG=1` is set explicitly for slow multi-threaded software emulation debugging.

## Troubleshooting

- **Missing `/dev/kvm` or emulator boot timeout (`-accel off`)**: Running the x86_64 API-33 emulator without KVM hardware acceleration is too slow and typically hits boot timeouts (`boot.sh` fails fast when `/dev/kvm` is absent unless `ANDROIDWORLD_ALLOW_TCG=1` is set). Verify host capability with `scripts/check_emulator_host.sh` before running trials; use a Linux `x86_64` host with `/dev/kvm` (Docker via `environment/docker-compose.yaml` or bare-metal/VM KVM) rather than Apple Silicon or Daytona sandboxes without `/dev/kvm`.
- **First-boot APK installation failures**: `setup_apps` downloads benchmark APKs on first emulator boot, so outbound network access is required unless APKs/snapshots are pre-baked into the image. Inspect `/logs/aw/emulator.log` and `/logs/aw/daemon.log` inside the container if initialization fails.
- **`harbor lint` reports `shared-verifier`**: Expected for all AndroidWorld tasks because the verifier must query the live in-container daemon (`/opt/aw/client.py score`) against the running emulator. Run `harbor lint --ignore shared-verifier datasets/androidworld/*`.

## Citation

```bibtex
@misc{rawles2024androidworld,
  title={AndroidWorld: A Dynamic Benchmarking Environment for Autonomous Agents},
  author={Christopher Rawles and Sarah Clinckemaillie and Yifan Chang and Jonathan Waltz and Gabrielle Lau and Marybeth Fair and Alice Li and William Bishop and Wei Li and Folawiyo Campbell-Ajala and Daniel Toyama and Robert Berry and Divya Tyamagundlu and Timothy Lillicrap and Oriana Riva},
  year={2024}, eprint={2405.14573}, archivePrefix={arXiv}
}
```

## Authors & Contributions

Adapter built for Harbor-Index v2.0 (WIP). Original benchmark by the AndroidWorld authors (Google Research / DeepMind).
