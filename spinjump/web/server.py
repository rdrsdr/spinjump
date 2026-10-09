"""Servidor web multitenant: uma sessão de simulação ao vivo por visitante.

O navegador só envia parâmetros/comandos e exibe JPEGs e telemetria. Cada sessão roda em seu
próprio processo (física com ritmo controlado + renderizador dedicado, ver ``session_proc``), de
modo que sessões simultâneas não disputam o GIL; o servidor só repassa eventos (asyncio). O fator de reprodução muda apenas quantos passos físicos são executados
por segundo de relógio, nunca o passo ou as forças. Sem logs rotineiros: erros vão para a
interface.

Identidade: o navegador manda ``{"cmd": "hello", "sid": ...}``; o ``sid`` (aleatório, guardado
na aba) permite reconectar após recarregar a página. Sessões sem visitante por mais de
``SPINJUMP_DETACH_GRACE_S`` são encerradas (artefatos gravados); sessões terminadas liberam o
renderizador após ``SPINJUMP_FINISHED_TTL_S``. No máximo ``SPINJUMP_MAX_SESSIONS`` simulações
rodam ao mesmo tempo.
"""
from __future__ import annotations

import asyncio
import collections
import multiprocessing as mp
import contextlib
import json
import os
import re
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from ..config import SimConfig, list_presets, load_config, preset_description, to_plain
from ..i18n import get_lang, t
from ..report import OUT_DIR
from ..sim import safety_notice
from .session_proc import session_main

STATIC = Path(__file__).resolve().parent / "static"
SID_RE = re.compile(r"^[0-9a-f]{32}$")


def available_cpus() -> float:
    """CPUs disponíveis ao contêiner (cota do cgroup, afinidade ou contagem do host)."""
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()[:2]
        if quota != "max":
            return max(1.0, int(quota) / int(period))
    except (OSError, ValueError):
        pass
    try:
        q = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
        p = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
        if q > 0:
            return max(1.0, q / p)
    except (OSError, ValueError):
        pass
    try:
        return float(len(os.sched_getaffinity(0)))
    except AttributeError:
        return float(os.cpu_count() or 1)


def _env_num(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


# cada sessão usa ~1,5 núcleo (física + render); padrão = metade das CPUs disponíveis
MAX_SESSIONS = int(_env_num("SPINJUMP_MAX_SESSIONS", max(1, int(available_cpus() // 2))))
DETACH_GRACE_S = _env_num("SPINJUMP_DETACH_GRACE_S", 60.0)
FINISHED_TTL_S = _env_num("SPINJUMP_FINISHED_TTL_S", 600.0)
MAX_KEPT_SESSIONS = max(MAX_SESSIONS * 3, MAX_SESSIONS + 2)   # inclui terminadas (renderizador ocioso)
MAX_SIM_TIME_S = _env_num("SPINJUMP_MAX_SIM_TIME_S", 0.0)       # 0 = sem teto (instâncias públicas: ex. 180)


class Busy(Exception):
    pass


class Client:
    def __init__(self, ws: WebSocket, loop: asyncio.AbstractEventLoop):
        self.ws = ws
        self.loop = loop
        self.sid: str | None = None
        self.frame: bytes | None = None
        self.msgs: collections.deque = collections.deque(maxlen=200)
        self.wake = asyncio.Event()

    def push_frame(self, data: bytes):
        self.frame = data
        self.loop.call_soon_threadsafe(self.wake.set)

    def push_msg(self, msg: dict):
        self.msgs.append(msg)
        self.loop.call_soon_threadsafe(self.wake.set)


class SessionProxy:
    """Lado do servidor de uma sessão: processo próprio (física + render) e repasse aos clientes."""

    def __init__(self, sid: str, cfg: SimConfig, mgr: "Manager"):
        self.sid = sid
        self.mgr = mgr
        self.name = cfg.name
        self.clients: set[Client] = set()
        self.detached_since: float | None = None
        self.finished_at: float | None = None
        self.done = False
        self.closed = False
        self.paused = False
        self.factor = cfg.ui.playback_factor
        self.helix_scale = 1.0 if cfg.rope.coil_sliding else cfg.ui.helix_visual_pitch_scale
        self.result: dict | None = None
        self.started: dict | None = None
        self.last_tel: dict | None = None
        ctx = mp.get_context("spawn")
        self.conn, child = ctx.Pipe()
        # não-daemon: precisa criar o processo de render; se o servidor cair, o pipe fecha e a sessão sai
        self.proc = ctx.Process(target=session_main, args=(child, to_plain(cfg), get_lang()), daemon=False)
        self.proc.start()
        child.close()
        if not self.conn.poll(120):
            self._kill()
            raise RuntimeError("session process did not start")
        kind, *payload = self.conn.recv()
        if kind != "ready":
            self._kill()
            raise ValueError(payload[0] if payload else "session failed")
        self.started = payload[0]
        self._send_lock = threading.Lock()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    @property
    def last_t(self) -> float:
        return float(self.last_tel["t"]) if self.last_tel else 0.0

    def _kill(self):
        if self.proc.is_alive():
            self.proc.kill()
        self.proc.join(timeout=5)

    def broadcast(self, msg: dict):
        for c in list(self.clients):
            c.push_msg(msg)

    def _read(self):
        while True:
            try:
                kind, *payload = self.conn.recv()
            except (EOFError, OSError):
                break
            if kind == "frame":
                jpg, tel = payload
                self.last_tel = tel
                for c in list(self.clients):
                    c.push_frame(jpg)
                    c.push_msg({"type": "telemetry", **tel})
            elif kind == "msg":
                m = payload[0]
                if m.get("type") == "finished":
                    self.result = m
                elif m.get("type") == "status" and m.get("status") in ("paused", "running"):
                    self.paused = m["status"] == "paused"
                elif m.get("type") == "status" and m.get("status") == "playback":
                    self.factor = m["factor"]
                self.broadcast(m)
            elif kind == "done":
                self.done = True
                self.finished_at = time.monotonic()
                self.mgr.notify_load()
            elif kind == "closed":
                break
        self.done = True
        if self.finished_at is None:
            self.finished_at = time.monotonic()

    def send(self, msg: dict):
        if self.closed:
            return
        with self._send_lock:
            try:
                self.conn.send(msg)
            except (OSError, BrokenPipeError):
                pass

    def rerender(self):
        self.send({"cmd": "rerender"})

    def close(self, reason: str | None = None):
        if self.closed:
            return
        self.send({"cmd": "close", "reason": reason})
        self.closed = True
        self.proc.join(timeout=90)          # a sessão grava os artefatos antes de sair
        self.reader.join(timeout=5)
        self._kill()


class Manager:
    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self.max_sessions = max_sessions
        self.clients: set[Client] = set()
        self.sessions: dict[str, SessionProxy] = {}
        self.pending = 0
        self.lock = threading.Lock()
        self._reaper: threading.Thread | None = None
        self._stop = threading.Event()

    # ----------------------------------------------------------------- carga
    def running(self) -> int:
        return sum(1 for s in self.sessions.values() if not s.done) + self.pending

    def load(self) -> dict:
        return {"type": "server", "active": self.running(), "max": self.max_sessions}

    def notify_load(self):
        msg = self.load()
        for c in list(self.clients):
            c.push_msg(msg)

    # --------------------------------------------------------------- clientes
    def attach(self, cl: Client, sid: str | None) -> str:
        sid = sid if isinstance(sid, str) and SID_RE.match(sid) else uuid.uuid4().hex
        cl.sid = sid
        self.clients.add(cl)
        with self.lock:
            s = self.sessions.get(sid)
        if s is not None and not s.closed:
            s.clients.add(cl)
            s.detached_since = None
        return sid

    def detach(self, cl: Client):
        self.clients.discard(cl)
        with self.lock:
            s = self.sessions.get(cl.sid) if cl.sid else None
        if s is not None:
            s.clients.discard(cl)
            if not s.clients:
                s.detached_since = time.monotonic()

    def session_of(self, cl: Client) -> SessionProxy | None:
        with self.lock:
            s = self.sessions.get(cl.sid) if cl.sid else None
        return s if s is not None and not s.closed else None

    # --------------------------------------------------------------- sessões
    def start(self, cl: Client, cfg: SimConfig) -> SessionProxy:
        sid = cl.sid
        with self.lock:
            old = self.sessions.pop(sid, None)
        if old is not None:
            old.close()
        with self.lock:
            if self.running() >= self.max_sessions:
                raise Busy(t("w.busy", n=self.running(), max=self.max_sessions))
            self.pending += 1
        try:
            s = SessionProxy(sid, cfg, self)
        finally:
            with self.lock:
                self.pending -= 1
        s.clients = {c for c in self.clients if c.sid == sid}
        with self.lock:
            self.sessions[sid] = s
        s.broadcast(s.started)
        self.notify_load()
        self._evict_finished()
        return s

    def _evict_finished(self):
        """Limita sessões guardadas (cada uma mantém um processo de render ocioso)."""
        with self.lock:
            done = sorted((s for s in self.sessions.values() if s.done),
                          key=lambda s: (bool(s.clients), s.finished_at or 0.0))
            extra = len(self.sessions) - MAX_KEPT_SESSIONS
            victims = done[:max(0, extra)]
            for s in victims:
                self.sessions.pop(s.sid, None)
        for s in victims:
            s.close()

    def reap(self):
        now = time.monotonic()
        victims = []
        with self.lock:
            for sid, s in list(self.sessions.items()):
                gone = not s.clients and s.detached_since is not None and now - s.detached_since > DETACH_GRACE_S
                stale = s.done and s.finished_at is not None and now - s.finished_at > FINISHED_TTL_S \
                    and not s.clients
                if gone or stale:
                    victims.append(self.sessions.pop(sid))
        for s in victims:
            s.close(t("stopped_disconnected"))
        if victims:
            self.notify_load()

    def start_reaper(self, interval: float = 5.0):
        if self._reaper is not None:
            return

        def loop():
            while not self._stop.wait(interval):
                try:
                    self.reap()
                except Exception:   # nunca derruba o servidor
                    pass
        self._reaper = threading.Thread(target=loop, daemon=True)
        self._reaper.start()

    def close_all(self):
        self._stop.set()
        with self.lock:
            sessions, self.sessions = list(self.sessions.values()), {}
        for s in sessions:
            s.close()


mgr = Manager()


@contextlib.asynccontextmanager
async def _lifespan(_app):
    mgr.start_reaper()
    yield
    mgr.close_all()


app = FastAPI(title="SpinJump", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
OUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/out", StaticFiles(directory=OUT_DIR, html=True), name="out")


@app.get("/")
def intro():
    """Página inicial: o que é, o que não é, riscos; o simulador fica em /app."""
    return FileResponse(STATIC / "intro.html")


@app.get("/app")
def simulator():
    return FileResponse(STATIC / "index.html")


@app.get("/api/defaults")
def defaults():
    presets = [{"name": n, "description": preset_description(n)} for n in list_presets()]
    return JSONResponse({"config": to_plain(load_config()), "presets": presets,
                         "safety_notice": safety_notice(), "server": mgr.load()})


@app.get("/api/preset/{name}")
def preset(name: str):
    try:
        return JSONResponse({"config": to_plain(load_config(preset=name)),
                             "description": preset_description(name)})
    except (FileNotFoundError, ValidationError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)


def _validation_text(e: Exception) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors())
    return str(e)


async def _sender(cl: Client):
    while True:
        await cl.wake.wait()
        cl.wake.clear()
        while cl.msgs:
            await cl.ws.send_text(json.dumps(cl.msgs.popleft(), ensure_ascii=False))
        if cl.frame is not None:
            f, cl.frame = cl.frame, None
            await cl.ws.send_bytes(f)


def _hello(cl: Client, sid: str | None):
    sid = mgr.attach(cl, sid)
    load = mgr.load()
    cl.push_msg({"type": "hello", "sid": sid, "active": load["active"], "max": load["max"]})
    s = mgr.session_of(cl)
    if s is not None:
        cl.push_msg({"type": "status", "status": "attached", "name": s.name, "finished": s.done,
                     "paused": s.paused, "factor": s.factor, "helix_visual_pitch_scale": s.helix_scale})
        if s.result:
            cl.push_msg(s.result)
        s.rerender()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    cl = Client(ws, asyncio.get_running_loop())
    sender = asyncio.create_task(_sender(cl))
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("cmd") == "hello" or cl.sid is None:
                _hello(cl, msg.get("sid") if msg.get("cmd") == "hello" else None)
                if msg.get("cmd") == "hello":
                    continue
            await _handle(msg, cl)
    except WebSocketDisconnect:
        pass
    finally:
        mgr.detach(cl)
        sender.cancel()


async def _handle(msg: dict, cl: Client):
    cmd = msg.get("cmd")
    loop = asyncio.get_running_loop()
    if cmd == "start":
        try:
            cfg = load_config(preset=msg.get("preset") or None, extra=msg.get("config") or {})
        except (ValidationError, ValueError, KeyError, FileNotFoundError) as e:
            cl.push_msg({"type": "error", "message": t("w.bad_config", e=_validation_text(e))})
            return
        if MAX_SIM_TIME_S > 0 and cfg.solver.max_time_s > MAX_SIM_TIME_S:
            cfg.solver.max_time_s = MAX_SIM_TIME_S
        try:
            await loop.run_in_executor(None, mgr.start, cl, cfg)
        except Busy as e:
            cl.push_msg({"type": "error", "code": "busy", "message": str(e)})
        except Exception as e:
            cl.push_msg({"type": "error", "message": t("w.cant_start", e=_validation_text(e))})
        return
    s = mgr.session_of(cl)
    if s is None:
        cl.push_msg({"type": "error", "message": t("w.no_session")})
        return
    if cmd in ("pause", "resume", "stop", "playback", "camera"):
        s.send(msg)


def serve(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port, access_log=False, log_level="error", ws="websockets-sansio")
