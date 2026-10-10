# SpinJump — 3D rope-and-chimney physics simulator (MuJoCo)

> **Safety notice.** Results are **qualitative and exploratory**, produced by a simplified model.
> They are **never human-safety validation**. Impact thresholds (g / N) are illustrative, not
> clinical. This notice must stay visible in the web UI, the CLI output, the reports and the docs.

This README is the **project overview and handoff document**: it holds enough context to resume
work from a clean session. The full technical documentation (required by the spec to be in
Portuguese) is in [docs/DOCUMENTACAO.md](docs/DOCUMENTACAO.md); design decisions, failed attempts
and calibration studies are in [NOTES.md](NOTES.md).

---

## 1. What it is

A rigid chimney (default H = 50 m, D = 5 m) has a rope wound in a tight helix near its top. The
other end is tied to a human-mass object (rigid mannequin or sandbag) launched from the top edge.
The object falls, the rope unwinds as it swings around the chimney, it spirals down, hits the
ground and slides under friction and rope restraint. The spiral emerges from forces and
constraints only — there is no scripted trajectory.

Deliverables (all implemented):

- **Web UI** (FastAPI + WebSocket): intro/safety page with acknowledgement gate (`/`), then the
  simulator (`/app`) with live server-rendered 3D frames, telemetry, scrollable impact list,
  strongest-impact card, parameter form, presets, links to reports. English UI, **multitenant**
  (one process per visitor).
- **CLI** `python -m spinjump` (Portuguese output): `run`, `sweep`, `report`, `rope-length`,
  `selftest`, `serve`.
- **Reports** per run in `out/<run>/`: CSV, JSON, Markdown, HTML, PNG plots. No MP4/GIF/replay
  (forbidden by the spec).
- **Validation tests** (pytest) covering the 10 physics checks of the spec plus web tests.
- **Docker / Compose**, plus a **Hugging Face Spaces** packaging script.

Source of truth for requirements: [prompt.md](prompt.md) (spec) and [planning.md](planning.md)
(plan). **Never modify these two files.**

## 2. Current state (2026-10-09)

| item | state |
|---|---|
| branch `main` | `4155e2b` — first complete version, **locked coils** only; tagged `v1-locked-coils` |
| branch `feature/sliding-coils` (current) | sliding coils + bottom-to-top unwinding + numba kernels + UI fixes; **not merged into `main`** |
| tests | 52 passing (`make test`, a few minutes) |
| default model | `rope.coil_sliding: true`, `rope.helix_vertical: down` |
| local only, git-ignored | `publish.txt` (user notes) and `out/` |

Commits on the feature branch (oldest first): `be7b419` sliding coils discretised on the tower
surface · `f081f41` remove obsolete debug scripts · `b38c6f5` numba kernels, adaptive window, UI,
docs · `4a5c848` UI: restart after finish, scrollable impact list, distance to floor.

To revert to the locked-coils-only version: `git checkout main` (or `git checkout v1-locked-coils`).
Sliding coils can also be switched off at runtime (`--set rope.coil_sliding=false` or the UI
checkbox "Coils can slide on the wall").

Nothing is pending. Possible next steps are listed in §11.

## 3. Quick start

Everything runs in Docker; the host needs only Docker + Compose.

```bash
docker compose up --build -d ui        # or: make up
# http://localhost:8000      intro / safety page (tick the box to enter)
# http://localhost:8000/app  simulator (redirects to / without the acknowledgement)

make test          # all tests inside the container (minutes)
make test-fast     # config + isolated physics only
make run           # default scenario + convergence study  → out/<run>/
make sweep         # short azimuth × speed sweep
make selftest
make ui-flow       # WebSocket flow against the running "ui" container
make ui-layout     # Playwright/Chromium screenshots at 4 viewports (pulls Playwright image)
make hf-space      # assemble the Hugging Face Space repo in ../spinjump-space
make down
```

CLI through Compose: `docker compose run --rm cli <command> [options]`, e.g.

```bash
docker compose run --rm cli run --preset sandbag --set launch.speed_ms=6 --name test1
docker compose run --rm cli sweep --param launch.azimuth_deg=-60,0,90 --param launch.speed_ms=2,6 --seeds 1,2
docker compose run --rm cli rope-length --height 50
docker compose run --rm cli report out/<run> --rerun     # regenerate + determinism check
```

Common options: `--config file.yaml` (merged over `configs/default.yaml`), `--preset NAME`,
`--set path=value` (repeatable), `--name`, `--out`.

**Development loop without rebuilding** — `dev.sh` runs any command in the dev image with the
working tree mounted at `/app`:

```bash
docker build -t spinrapel-sim:dev .          # once, or after changing requirements/Dockerfile
./dev.sh python -m pytest -q tests/test_surface_rope.py
./dev.sh python -m spinjump run --set rope.coil_sliding=false
./dev.sh python prototypes/ensemble.py
```

The production image is `spinjump:1.0.0` (built by Compose). Rebuild it (`make up`) after code
changes before testing the UI container.

## 4. Repository map

```
spinjump/                Python package
  config.py              Pydantic (strict) config: YAML merge, presets, --set overrides, "auto" values
  i18n.py                pt/en strings; process-wide language (CLI pt, web en)
  model.py               MJCF generation: tower, ground, mannequin/sandbag geoms, contact <pair>s
  rope.py                WrapTether (locked coils) + RopeParams/RopeState + distributed loads
  surface_rope.py        SurfaceRope (sliding coils: node chain on the cylinder surface)
  _chain_kernel.py       numba kernels: chain_step (implicit solve), dist_loads, warmup
  wind.py                wind profile and gusts (seeded)
  sim.py                 Simulation loop (mj_step1 → rope forces → mj_step2), snapshots, outcome
  impacts.py             contact-force impact events, grouping, OK/WARNING/DAMAGE classes
  metrics.py             summary metrics and flags (cast to plain bool/float!)
  report.py, plots.py    CSV/JSON/MD/HTML + matplotlib plots; pruning of old runs
  sweep.py               parameter/seed sweeps (multiprocessing) + heatmaps
  convergence.py         timestep/discretisation convergence study and "reliable" flags
  render.py              offscreen OSMesa renderer (SceneRenderer) + RenderWorker process
  selftest.py, cli.py    CLI entry points (__main__.py has the spawn-safe main guard)
  web/server.py          FastAPI app, Manager (capacity/reaper), SessionProxy, WS relay
  web/session_proc.py    per-visitor process: SessionCore runs the Simulation
  web/static/            intro.html/.css (safety page), index.html, app.js, style.css
configs/default.yaml     demo scenario; configs/presets/*.yaml (description + description_en)
tests/                   pytest: config, isolated physics, rope, scenario, surface rope, web
tools/                   ui_flow.py, ui_layout.py/.sh, ui_repro.py (UI checks)
prototypes/              cable-plugin prototype (rejected) + calibration/study scripts cited in NOTES
deploy/huggingface/      Space card (README.md) and make_space.sh
docs/DOCUMENTACAO.md     full documentation in Portuguese (spec-required)
NOTES.md                 decisions, failures, calibration, performance (Portuguese)
shithappens.md           launch/wind settings that make the object hit the tower (Portuguese)
Dockerfile, compose.yaml, compose.gpu.yaml (EGL/NVIDIA, untested), Makefile, dev.sh, requirements.txt
out/                     run outputs (git-ignored)
```

## 5. Architecture

**Physics split.** MuJoCo 3.15.0 integrates the object's rigid-body dynamics (free joint,
`implicitfast`, dt = 0.25 ms) and all contacts with ground and tower (explicit `<pair>` matrix,
sliding/torsional/rolling friction). **The rope is custom code**: each step it computes the rope
force and applies it through `data.xfrc_applied` between `mj_step1` and `mj_step2`. MuJoCo's
cable plugin was prototyped first as the spec required and rejected (≈3000 s CPU per simulated
second, NaN at 0.4–0.6 s, 0.5 m penetration — see NOTES §2, `prototypes/results/`).
`rope.model: chain` is forbidden by the spec and rejected by the config; `cable_plugin` is
rejected with an explanatory message. Only `wrap_tether` is valid.

**Web, multitenant.**

```
browser ──WS /ws──► server.py (uvicorn, 1 process)
                     Manager: capacity (SPINJUMP_MAX_SESSIONS), reaper, reconnect by sid
                     SessionProxy ──pipe──► session process (spawn, non-daemon, one per visitor)
                                              SessionCore → Simulation (physics)
                                              └─► RenderWorker process (OSMesa) → JPEG frames
```

- One OS process per visitor because two simulations in one process ran at 0.6× (GIL). Session
  processes are non-daemon because daemon processes cannot have children (the render worker).
- The browser keeps a session id in `sessionStorage` and reconnects to the same process after a
  page reload; detached sessions die after `SPINJUMP_DETACH_GRACE_S`.
- All WS messages go through `_encode()` with a `_jsonable` fallback for numpy scalars/arrays. A
  stray `numpy.bool_` once killed the sender task (Start dead after the run finished, no
  strongest-impact card) — keep metrics/flags as plain Python types.
- Language: `i18n.set_lang` is process-wide. CLI defaults to `pt` (`SPINJUMP_LANG`); `serve
  --lang` defaults to `en` (`SPINJUMP_WEB_LANG`). Outcome/impact **codes** stay fixed; only labels
  are translated.

**Environment variables**

| variable | default | meaning |
|---|---|---|
| `PORT` | 8000 | `serve` port (HF Spaces: 7860) |
| `SPINJUMP_PORT` | 8000 | host port in compose.yaml |
| `SPINJUMP_MAX_SESSIONS` | CPUs / 2 | concurrent visitor simulations |
| `SPINJUMP_MAX_SIM_TIME_S` | 0 (no cap) | cap on `solver.max_time_s` for web runs |
| `SPINJUMP_KEEP_RUNS` | 0 (keep all) | prune web run folders beyond N most recent |
| `SPINJUMP_DETACH_GRACE_S` | 60 | lifetime of a session with no browser attached |
| `SPINJUMP_FINISHED_TTL_S` | 600 | lifetime of a finished session |
| `SPINJUMP_OUT` | `out/` (`/app/out` in Docker) | output base directory |
| `SPINJUMP_LANG` / `SPINJUMP_WEB_LANG` | pt / en | CLI / web language |
| `LP_NUM_THREADS` | 2 | llvmpipe render threads (keep low: contends with physics) |
| `NUMBA_CACHE_DIR` | `/tmp/numba_cache` | prewarmed in the image build (world-writable) |

## 6. Physics model (summary)

All rope variants share: unilateral elastic tension `T = max(0, k·δ + c·δ̇)`, `k = EA/L_rest`,
`c = 2ζ√(k·m)`; free span is a straight segment tangent to the cylinder; rope weight and air drag
are distributed along the span by quadrature and transferred to the ends by the lever rule; wind
with seeded gusts.

**Locked coils** (`coil_sliding: false`, class `WrapTether`, ~53 µs/step). Coils never move. A
stored helix only shrinks (peels at the departure point P1), a geodesic wrap segment handles
conservative re-winding, a kink/peel loss `T(κ − e·dP1/du)|u̇|` plus an insertion term models the
energy lost where the rope leaves the coils, and the anchor sees the capstan tension `T·e^(−μu)`.
Fully convergent; this is the model on `main`.

**Sliding coils** (`coil_sliding: true`, default, class `SurfaceRope` + `_chain_kernel.py`,
~117 µs/step). The rope lying on the wall is a chain of nodes constrained to the cylinder surface
(unrolled coordinates x = r·φ, z). Each step: linearised implicit Euler with a block-tridiagonal
2×2 Thomas solve; Coulomb wall friction via an active set inside the implicit solve (stick =
zero-velocity penalty, slip = μN opposing, ≤ 8 iterations) with normal load
`N = T̄·Δs·cos²β / r`; vertical contact projection between turns; winding pretension 20 N.
Key tricks (each fixes a failed attempt listed in NOTES §11):

- **mass scaling ×50** on inertia only (weight stays real), with a floor `m ≥ (EA/ds)·h²/4` so
  `ω·h ≤ 2` — removes the stiff whip without changing quasi-static behaviour;
- **adaptive window** of active turns `max(coil_window_turns, ln(100)/(2πμ))` — beyond it tension
  has decayed below 1% by capstan, so far coils are frozen;
- departure point found by tangency; the span force is applied to nodes k and k+1 by the lever
  rule (dynamic tail);
- span energy balance gives the peel loss; damping dissipation is computed from the actual Δδ.

`helix_vertical: down` (default) unwinds from the **bottom** coil upwards; `up` unwinds from the
top coil (matches the locked model closely).

**Impacts**: contact forces from `mj_contactForce`, grouped into events (merge gap 20 ms), peak
acceleration in g, classes OK / WARNING / DAMAGE against an **illustrative 10 g** threshold.

**Key physics findings** (details in NOTES §4–§7, §11):

- The spiral is an **attractor**: about 3 turns before the ground regardless of launch.
- With sliding coils, coils slide ≈ 11.6 m down the chimney and **wall friction (≈ 21.6 kJ)
  replaces the kink loss** as the main descent brake.
- Ground tumbling of the rigid mannequin is **chaotic**: post-landing slide distance changes by
  tens of percent with tiny launch changes, so with sliding coils it is flagged NOT RELIABLE (as
  the spec requires for non-convergent metrics).

Numerical settings and why (NOTES §4, §9): `contact.solref [0.02, 1.5]` (converged peaks, no
numerical rebound), ground rolling/torsional friction 0.02 (stops rocking jitter), dt 0.25 ms
(slide convergence).

## 7. Validation and reference numbers

Default scenario (`configs/default.yaml`: azimuth 90°, speed 4 m/s, elevation 5°):

| | sliding (default) | locked (`helix_vertical: down`) |
|---|---|---|
| outcome | AT_REST_CLEAN | AT_REST_CLEAN |
| turns before ground | 2.78 | 3.03 |
| ground arrival | 10.05 m/s at 24.6 s | 9.31 m/s at 29.5 s |
| slide after landing | 10.0 m (unreliable) | 11.9 m |
| max tension | 1825 N | 1784 N |
| CPU per simulated s | 0.50 s (117 µs/step) | ≈ 0.2 s (53 µs/step) |

Checks: free fall 0.25%; frictional slide ≤ 0.06%; impulse ≤ 0.06%; involute 8.1 mm (0.04%);
capstan formula 3.6e-4 (locked) and ≤ 2.2% measured dynamically during slip (sliding); energy
residual 0.5% locked / 2.5% sliding tolerance (0.4% measured over the full flight); convergence
≤ 4.8% (locked); coil drop 4.84–4.99 m across 10 s variants (sliding). Tables:
docs/DOCUMENTACAO.md §11 and NOTES §7, §11.

Hugging Face profile (2 vCPUs): 1 session runs at 1.0× real time, 2 sessions at 0.66–0.93×.

## 8. Deployment

- **Local / LAN**: `make up`. Quick public demo: `cloudflared tunnel --url http://localhost:8000`.
- **Hugging Face Spaces (Docker SDK — requires the paid PRO plan since mid-2026; free accounts only
  get static and Gradio/ZeroGPU Spaces)**: create a Docker Space, clone it, then
  `make hf-space SPACE_DIR=/path/to/clone`, `cd` there, `git add -A && git commit && git push`.
  The script copies code, configs, tests, tools, prototypes (without results), the Portuguese doc
  as `DOCUMENTACAO.md`, the Space card from `deploy/huggingface/README.md`, and appends to the
  Dockerfile: `PORT=7860 LP_NUM_THREADS=1 SPINJUMP_KEEP_RUNS=30 SPINJUMP_MAX_SESSIONS=2
  SPINJUMP_MAX_SIM_TIME_S=180` (and drops `VOLUME`). Reports there are ephemeral.
- **Oracle Cloud Always Free** (ARM VM) is the free always-on alternative; not set up.
- **Static, in-browser version** (GitHub Pages, MuJoCo WebAssembly): https://rdrsdr.github.io/spinjump/
  (see §12 and `browser/`).

## 9. Conventions and gotchas

- **Languages**: code comments, CLI, `docs/DOCUMENTACAO.md` and `NOTES.md` are Portuguese; web UI,
  this README and the HF Space card are English. Keep both i18n tables (`spinjump/i18n.py`) in
  sync when adding strings.
- **No routine logs** (spec): the CLI prints only a short result; uvicorn access log is off;
  compose uses `logging: driver: none`. Don't add progress prints.
- **No MP4/GIF/replay output** (spec).
- Do not name a local variable `t` where i18n `t` is used (it once crashed on the first impact);
  modules alias it as `tr` / `_t`.
- `multiprocessing` uses **spawn**: every script that starts processes needs an
  `if __name__ == "__main__":` guard.
- Don't run `pkill -f <pattern>` from a shell whose own command line contains the pattern.
- The image declares `VOLUME /app/out`; `dev.sh` therefore mounts `out/` explicitly.
- CSS: `[hidden]{display:none !important}` is required because some elements set `display:flex`.
- Commits: only when the user asks; author identity is `Rodrigo Sodre <141188401+rdrsdr@users.noreply.github.com>` (repo-local
  git config; GitHub account `rdrsdr`); end
  messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## 10. History of user requests

1. Build the simulator from `prompt.md` following `planning.md` (done → `main`, tag `v1-locked-coils`).
2. How to show it to friends for free → cloudflared tunnel, HF Spaces, Oracle Always Free.
3. Prepare the Hugging Face Spaces files → `deploy/huggingface/`.
4. Rename to **SpinJump**, English UI, multitenant, intro page on the sport, that it is only a
   simulation, not a recommendation, the risks, and not to try it.
5. Q&A: MuJoCo computes the rigid-body physics; the rope is custom. Implement **option B**
   (coils sliding on the wall with friction) plus **bottom-to-top unwinding**, with a checkbox to
   disable it; version the previous code in git first → `feature/sliding-coils`.
6. UI fixes: Start works again after a run finishes; telemetry label "distance to floor (m)";
   scrollable list of all impact events; strongest-impact card restored.
7. This README (handoff); the previous Portuguese README moved to `docs/DOCUMENTACAO.md`.
8. Publish on GitHub under `rdrsdr` (history rewritten to the noreply identity; public repo
   https://github.com/rdrsdr/spinjump) and document the collision settings (`shithappens.md`).
9. Hugging Face Docker Spaces became paid → evaluate running 100% in the browser: version the
   server app (tag `v2-python-server`) and build a prototype on branch `feature/browser-prototype`
   (see §12).
10. Browser prototype feedback ("not as smooth as the Python version, uses 100% CPU, no parameters,
    no report, no safety page") → worker no longer busy-waits, frames are interpolated, and the
    config/MJCF generation, parameter form, report and intro/safety page were ported to JS.

## 11. Known limitations and possible next steps

Limitations: single rigid body (no human biomechanics); rope–wall Coulomb friction with a single μ;
coils interact only vertically; straight free span (no sag/waves); impact g values depend on
contact settings; no validation against real experiments.

Possible next steps (none requested yet):

- merge `feature/sliding-coils` into `main` once the user is happy with it, and redeploy the Space;
- make post-landing metrics more robust (ensemble statistics instead of a single run);
- articulated mannequin for landing behaviour;
- test `compose.gpu.yaml` (EGL) on a GPU host.

## 12. Browser prototype (`browser/`, branch `feature/browser-prototype`)

Goal: run SpinJump entirely in the visitor's browser as static files (GitHub Pages), using the
official MuJoCo WebAssembly build (`@mujoco/mujoco` 3.15.0). Everything is in JavaScript
(`browser/public/`): intro/safety page (`index.html`, required before `sim.html`), config validation
and resolution (`src/config.js`, fed by `public/config.json`, generated from `configs/*.yaml` and the
Pydantic ranges by `browser/tools/export_config.py`), MJCF generation (`src/model.js`,
`src/scenario.js`), rope models, wind, drag, impacts, the parameter form (same fields as the server
UI plus a free `path=value` box and a shareable link), and the report (`src/report.js`: HTML with
SVG plots plus CSV/JSON, generated on the device). Details in `browser/README.md`.

- Scenario build identical to Python for 18 reference cases (MJCF byte for byte;
  `npm run check` against `browser/reference/`, exported by `browser/tools/export_scenarios.py`).
- Dynamics vs Python (deterministic wind): locked coils identical; sliding coils within 1.2 mm in
  flight with the same metrics; rewind case hits the tower in both.
- Speed: Node 16–18 µs/step (locked) and 56 µs/step (sliding) vs Python 53/117. In real time the
  worker only uses what physics needs (headless Chromium with software 3D: locked 22% of a core,
  sliding ~73%; main thread ~7%). Real-phone measurement pending.
- Not ported: MuJoCo offscreen rendering, GIF/video, sweeps, convergence test.
- Deployed to GitHub Pages at https://rdrsdr.github.io/spinjump/ by `.github/workflows/pages.yml`
  on every push to `main` that touches `browser/` (installs npm deps, copies them to
  `public/vendor`, runs `npm run check` and a short physics run, then publishes `browser/public`).
- Wind gusts use a JS RNG, so gust sequences differ from NumPy's for the same seed.
