"""Processo de uma sessão de simulação (um por visitante).

Cada sessão roda em seu próprio processo: física com ritmo controlado (thread), laço de
renderização (thread que conversa com o processo de render dedicado) e leitor de comandos. Assim
várias sessões rodam em paralelo de verdade, sem disputar o GIL do servidor web.

Protocolo pelo ``Pipe`` (tuplas):
  servidor → sessão: ``{"cmd": "pause"|"resume"|"stop"|"playback"|"camera"|"rerender"|"close", ...}``
  sessão → servidor: ``("ready", info)``, ``("fatal", texto)``, ``("frame", jpeg, telemetria)``,
  ``("msg", dict)``, ``("done",)``, ``("closed",)``
"""
from __future__ import annotations

import collections
import os
import threading
import time
import traceback

MAX_LAG_S = 0.25          # atraso máximo acumulado (s de relógio) antes de reancorar o ritmo


class SessionCore:
    def __init__(self, cfg, emit):
        from ..render import CameraState, RenderWorker
        from ..sim import Simulation
        self.emit = emit
        self.sim = Simulation(cfg)
        c = self.sim.cfg
        self.cfg = c
        self.factor = c.ui.playback_factor
        self.pitch_scale = 1.0 if c.rope.coil_sliding else c.ui.helix_visual_pitch_scale
        self.render_hz = c.ui.render_hz
        self.camera = CameraState(mode=c.ui.camera, distance=max(60.0, c.tower.height_m * 1.9),
                                  lookat=[0.0, 0.0, c.tower.height_m * 0.45])
        self.paused = False
        self.stop_flag = False
        self.stop_reason: str | None = None
        self.cam_dirty = True
        self.lock = threading.Lock()
        self.latest = None            # (FrameState, telemetria)
        self.new_frame = threading.Event()
        self.wall_run = 0.0           # relógio acumulado executando (sem pausas)
        self.hist = collections.deque(maxlen=400)
        self.rate = 0.0
        self.render_ms = 0.0
        self.done = False
        self.closed = False
        self.renderer = RenderWorker(self.sim.b.xml, c.ui.width, c.ui.height, c.ui.rope_visual_radius_m,
                                     c.tower.height_m, c.ui.jpeg_quality)
        self.t_phys = threading.Thread(target=self._physics, daemon=True)
        self.t_rend = threading.Thread(target=self._render_loop, daemon=True)

    def started_info(self) -> dict:
        s = self.sim
        return {"type": "started", "name": self.cfg.name, "layout": {
            "turns0": round(s.layout["turns0"], 3), "wound0_m": round(s.layout["wound0"], 2),
            "free0_m": round(s.layout["free0"], 3), "rope_length_m": float(self.cfg.rope.length_m),
            "rope_length_source": s.notes.get("rope_length_source")},
            "warnings": s.warnings, "helix_visual_pitch_scale": self.pitch_scale,
            "factor": self.factor, "render_hz": self.render_hz, "camera": self.camera.mode}

    def start(self):
        self._publish()
        self.t_phys.start()
        self.t_rend.start()

    # ---------------------------------------------------------------- física
    def _publish(self):
        from ..render import frame_state
        sim = self.sim
        tel = sim.snapshot()
        tel.update(wall_s=round(self.wall_run, 3), rate=round(self.rate, 3), factor=self.factor,
                   paused=self.paused, render_ms=round(self.render_ms, 1))
        fs = frame_state(sim, self.pitch_scale)
        with self.lock:
            self.latest = (fs, tel)
        self.new_frame.set()

    def _physics(self):
        from ..i18n import t
        from ..report import OUT_DIR, prune_runs, run_dir, write_artifacts
        sim = self.sim
        try:
            period = 1.0 / self.render_hz
            wall0 = time.perf_counter()
            sim0 = sim.d.time
            last = wall0
            next_pub = wall0
            while not self.stop_flag:
                now = time.perf_counter()
                if self.paused:
                    time.sleep(0.02)
                    wall0, sim0, last = time.perf_counter(), sim.d.time, time.perf_counter()
                    continue
                self.wall_run += now - last
                last = now
                target = sim0 + self.factor * (now - wall0)
                budget = now + 0.015
                running = True
                while sim.d.time < target and time.perf_counter() < budget:
                    if not sim.step():
                        running = False
                        break
                now2 = time.perf_counter()
                # atraso: não acumula dívida (sem aceleração para "recuperar"), não pula passos
                if target - sim.d.time > MAX_LAG_S * self.factor:
                    wall0, sim0 = now2, sim.d.time
                self.hist.append((now2, sim.d.time, self.wall_run))
                while len(self.hist) > 2 and self.wall_run - self.hist[0][2] > 2.0:
                    self.hist.popleft()
                _, s_old, r_old = self.hist[0]
                if self.wall_run - r_old > 0.2:
                    self.rate = (sim.d.time - s_old) / (self.wall_run - r_old)
                if now2 >= next_pub or not running:
                    self._publish()
                    next_pub = now2 + period
                if not running:
                    break
                if sim.d.time >= target:
                    time.sleep(0.001)
            if self.stop_flag and sim.status == "running":
                sim.stop(self.stop_reason or t("stopped_by_user"))
            sim.finish()
            sim.wall_clock = self.wall_run          # tempo de relógio executando (sem pausas)
            self._publish()
            self.emit("msg", {"type": "status", "status": "writing", "message": t("w.writing")})
            out = run_dir(sim.cfg.name)
            summary = write_artifacts(sim, out)
            keep = int(os.environ.get("SPINJUMP_KEEP_RUNS", "0") or 0)
            if keep > 0:
                prune_runs(keep)
            rel = out.relative_to(OUT_DIR).as_posix()
            self.emit("msg", dict(type="finished", outcome=summary["outcome"], spiral=summary["spiral"],
                                  ground_arrival=summary["ground_arrival"], ground_phase=summary["ground_phase"],
                                  rope=summary["rope"], impacts=summary["impacts"], warnings=summary["warnings"],
                                  report_url=f"/out/{rel}/summary.html", dir_url=f"/out/{rel}/",
                                  artifacts=summary["artifacts"]))
        except Exception as e:
            self.emit("msg", {"type": "error", "message": t("w.sim_fail", e=e),
                              "detail": traceback.format_exc(limit=3)})
        finally:
            self.done = True
            self.new_frame.set()
            self.emit("done")

    # ----------------------------------------------------------- renderização
    def _render_loop(self):
        from ..i18n import t
        period = 1.0 / self.render_hz
        try:
            while not self.closed:
                self.new_frame.wait(timeout=0.5)
                self.new_frame.clear()
                with self.lock:
                    item = self.latest
                if item is None:
                    continue
                fs, tel = item
                t0 = time.perf_counter()
                jpg = self.renderer.render(fs, self.camera)
                self.render_ms = (time.perf_counter() - t0) * 1000
                self.cam_dirty = False
                self.emit("frame", jpg, tel)
                if self.done and not self.new_frame.is_set():
                    break
                dt = period - (time.perf_counter() - t0)
                if dt > 0 and not self.cam_dirty:
                    time.sleep(dt * 0.5)
        except Exception as e:
            if not self.closed:
                self.emit("msg", {"type": "error", "message": t("w.render_fail", e=e)})

    def rerender(self):
        from ..i18n import t
        if self.closed:
            return
        self.cam_dirty = True
        if self.done:
            with self.lock:
                item = self.latest
            if item:
                try:
                    self.emit("frame", self.renderer.render(item[0], self.camera), item[1])
                except Exception as e:
                    self.emit("msg", {"type": "error", "message": t("w.render_fail", e=e)})
        else:
            self.new_frame.set()

    # --------------------------------------------------------------- comandos
    def command(self, msg: dict):
        cmd = msg.get("cmd")
        if cmd == "pause":
            self.paused = True
            self.emit("msg", {"type": "status", "status": "paused"})
        elif cmd == "resume":
            self.paused = False
            self.emit("msg", {"type": "status", "status": "running"})
        elif cmd == "stop":
            self.stop_flag = True
            self.paused = False
            self.emit("msg", {"type": "status", "status": "stopping"})
        elif cmd == "playback":
            self.factor = min(4.0, max(0.1, float(msg.get("factor", 1.0))))
            self.emit("msg", {"type": "status", "status": "playback", "factor": self.factor})
        elif cmd == "camera":
            cam, H = self.camera, self.cfg.tower.height_m
            if msg.get("mode") in ("free", "side", "follow"):
                cam.mode = msg["mode"]
            if "daz" in msg:
                cam.azimuth = (cam.azimuth + float(msg["daz"])) % 360.0
            if "del" in msg:
                cam.elevation = min(-1.0, max(-89.0, cam.elevation + float(msg["del"])))
            if "zoom" in msg:
                cam.distance = min(600.0, max(3.0, cam.distance * float(msg["zoom"])))
            if "dz" in msg:
                cam.lookat[2] = min(H * 1.2, max(0.0, cam.lookat[2] + float(msg["dz"])))
            if msg.get("reset"):
                cam.azimuth, cam.elevation = -60.0, -12.0
                cam.distance = max(60.0, H * 1.9)
                cam.lookat = [0.0, 0.0, H * 0.45]
            self.rerender()
        elif cmd == "rerender":
            self.rerender()

    def close(self, reason: str | None = None):
        self.stop_reason = reason
        self.stop_flag = True
        self.paused = False
        if self.t_phys.is_alive():
            self.t_phys.join(timeout=60)
        self.closed = True
        self.new_frame.set()
        self.renderer.close()


def session_main(conn, plain: dict, lang: str):
    """Ponto de entrada do processo da sessão."""
    from ..config import SimConfig
    from ..i18n import set_lang, t
    set_lang(lang)
    send_lock = threading.Lock()

    def emit(*item):
        with send_lock:
            try:
                conn.send(item)
            except (OSError, EOFError, BrokenPipeError):
                pass

    try:
        core = SessionCore(SimConfig.model_validate(plain), emit)
    except Exception as e:
        emit("fatal", t("w.cant_start", e=e))
        return
    emit("ready", core.started_info())
    core.start()
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            msg = {"cmd": "close"}
        if msg.get("cmd") == "close":
            core.close(msg.get("reason"))
            break
        core.command(msg)
    emit("closed")
