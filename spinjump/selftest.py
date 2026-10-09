"""Autoverificação rápida (< 1 min): ambiente, contrato de configuração, física básica e render."""
from __future__ import annotations

import math
import os
import time

import mujoco
import numpy as np

from .config import G, list_presets, load_config, resolve
from .model import build
from .sim import Simulation


def run_selftest(render: bool = True) -> bool:
    results: list[tuple[str, bool, str]] = []

    def check(name, fn):
        t0 = time.perf_counter()
        try:
            ok, info = fn()
        except Exception as e:  # noqa: BLE001
            ok, info = False, f"exceção: {e!r}"
        results.append((name, ok, f"{info} [{time.perf_counter() - t0:.1f}s]"))

    def cfg_contract():
        cfg = load_config(sets=["launch.mode=impulse", "launch.impulse_Ns=400"])
        rc, notes = resolve(cfg)
        bad = []
        for m in ("chain", "cable_plugin"):
            try:
                load_config(sets=[f"rope.model={m}"])
                bad.append(m)
            except ValueError:
                pass
        for p in list_presets():
            load_config(preset=p)
        ok = abs(notes["launch"]["speed_ms"] - 5.0) < 1e-12 and not bad
        return ok, f"impulso 400 N·s → Δv {notes['launch']['speed_ms']:.2f} m/s; modelos recusados ok; {len(list_presets())} presets válidos"

    def free_fall():
        cfg = load_config(sets=["solver.timestep_s=0.00025"])
        b = build(cfg, np.array([0.0, 0.0, 100.0]), with_tower=False)
        m, d = b.model, b.data
        z0 = d.xipos[b.body_id][2]
        n = int(round(1.0 / m.opt.timestep))
        for _ in range(n):
            mujoco.mj_step(m, d)
        t = d.time
        z = d.xipos[b.body_id][2]
        err = abs((z0 - z) - 0.5 * G * t * t) / (0.5 * G * t * t)
        return err < 0.005, f"erro relativo de queda {err:.2e} em t={t:.2f}s"

    def rope_bookkeeping():
        s = Simulation(load_config(sets=["solver.max_time_s=2"]))
        lay = s.layout
        closure = abs(lay["wound0"] + lay["free0"] - s.rp.length)
        s.run()
        rs = s.rope.s
        closure2 = abs(rs.stored_len + rs.l_rest - s.rp.length)
        unwound = lay["turns0"] - rs.u_s / (2 * math.pi)
        ok = closure < 1e-9 and closure2 < 1e-9 and unwound > 0 and s.outcome != "NUMERICAL_FAILURE"
        return ok, (f"L fecha (erro {max(closure, closure2):.1e} m); em 2 s liberou {unwound:.3f} voltas; "
                    f"custo {s.wall_clock / 2:.2f} s CPU/s simulado")

    def render_frame():
        from .render import SceneRenderer, encode_jpeg, frame_state, CameraState
        s = Simulation(load_config(sets=["solver.max_time_s=0.5"])).run()
        sr = SceneRenderer(s.b.xml, 320, 200, 0.04, s.cfg.tower.height_m)
        img = sr.render(frame_state(s, 12.0), CameraState())
        jpg = encode_jpeg(img, 80)
        return (img.shape == (200, 320, 3) and img.std() > 1 and len(jpg) > 1000,
                f"MUJOCO_GL={os.environ.get('MUJOCO_GL', '?')}, quadro {img.shape}, JPEG {len(jpg)} bytes")

    def no_video():
        from .report import OUT_DIR
        bad = [str(p) for ext in ("*.mp4", "*.gif", "*.webm", "*.avi") for p in OUT_DIR.rglob(ext)]
        return not bad, "nenhum vídeo/GIF em out/" if not bad else f"encontrados: {bad[:3]}"

    check("contrato de configuração", cfg_contract)
    check("queda livre (< 0,5%)", free_fall)
    check("contabilidade da corda e desenrolamento", rope_bookkeeping)
    if render:
        check("renderização offscreen", render_frame)
    check("sem vídeo/replay", no_video)
    width = max(len(n) for n, _, _ in results)
    for name, ok, info in results:
        print(f"{'PASSOU' if ok else 'FALHOU':7s} {name:<{width}}  {info}")
    allok = all(ok for _, ok, _ in results)
    print(f"selftest: {'OK' if allok else 'FALHAS'} (MuJoCo {mujoco.__version__})")
    return allok
