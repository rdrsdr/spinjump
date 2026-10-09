"""Interface web (10): página inicial, fluxo ao vivo, sessões por visitante, capacidade, reconexão.

Usa o app FastAPI em processo (TestClient); cada sessão tem renderizador próprio (processo, OSMesa).
A interface web roda em inglês.
"""
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

OUT = Path(tempfile.mkdtemp(prefix="spinjump_out_"))
os.environ["SPINJUMP_OUT"] = str(OUT)

from fastapi.testclient import TestClient  # noqa: E402

from spinjump.i18n import set_lang  # noqa: E402
from spinjump.web import server  # noqa: E402

SMALL = {"ui": {"width": 320, "height": 200}}


@pytest.fixture(autouse=True)
def english():
    set_lang("en")
    yield
    set_lang("pt")
    server.mgr.close_all()
    server.mgr._stop.clear()
    server.mgr.max_sessions = server.MAX_SESSIONS


def _recv_until(ws, pred, timeout=60.0):
    t_end = time.monotonic() + timeout
    frames, msgs = 0, []
    while time.monotonic() < t_end:
        m = ws.receive()
        if m.get("bytes") is not None:
            assert m["bytes"][:2] == b"\xff\xd8"
            frames += 1
            continue
        if m.get("text") is None:
            continue
        j = json.loads(m["text"])
        msgs.append(j)
        if j["type"] == "error" and not pred(j):
            raise AssertionError(j["message"])
        if pred(j):
            return frames, msgs
    raise AssertionError("timeout")


def _hello(ws, sid=None):
    ws.send_text(json.dumps({"cmd": "hello", "sid": sid}))
    _, msgs = _recv_until(ws, lambda j: j["type"] == "hello")
    return msgs[-1]["sid"]


def _start(ws, extra=None):
    cfg = json.loads(json.dumps(SMALL))
    cfg.update(extra or {})
    ws.send_text(json.dumps({"cmd": "start", "config": cfg}))


def test_intro_page_and_gate():
    c = TestClient(server.app)
    intro = c.get("/").text
    for phrase in ("only a simulation", "not a recommendation", "Do not attempt", "Real-world dangers",
                   "Open the simulator", 'id="ack"'):
        assert phrase in intro, phrase
    app_html = c.get("/app").text
    assert 'id="frame"' in app_html and "spinjump_ack" in app_html and "About &amp; safety" in app_html
    d = c.get("/api/defaults").json()
    assert d["config"]["rope"]["model"] == "wrap_tether"
    assert "NOT a human-safety validation" in d["safety_notice"]
    assert d["server"]["max"] >= 1
    assert all(p["description"] and "ã" not in p["description"] for p in d["presets"])


def test_10_ui_flow_live_frames_pause_resume_artifacts():
    assert server.OUT_DIR == OUT
    c = TestClient(server.app)
    with c.websocket_connect("/ws") as ws:
        sid = _hello(ws)
        assert len(sid) == 32
        _start(ws, {"launch": {"mode": "impulse", "impulse_Ns": 400.0, "speed_ms": None},
                    "solver": {"max_time_s": 60.0}})
        _recv_until(ws, lambda j: j["type"] == "started")
        frames, msgs = _recv_until(ws, lambda j: j["type"] == "telemetry" and j["t"] > 3.0)
        assert frames >= 5
        tel = [m for m in msgs if m["type"] == "telemetry"]
        assert tel[-1]["phase"] in ("airborne", "launch")
        a, b = tel[1], tel[-1]
        rate = (b["t"] - a["t"]) / (b["wall_s"] - a["wall_s"])
        assert 0.9 < rate < 1.1, rate
        ws.send_text(json.dumps({"cmd": "pause"}))
        _recv_until(ws, lambda j: j["type"] == "status" and j["status"] == "paused")
        time.sleep(0.3)
        _, msgs = _recv_until(ws, lambda j: j["type"] == "telemetry", timeout=5)
        t_p0 = msgs[-1]["t"]
        time.sleep(1.0)
        ws.send_text(json.dumps({"cmd": "camera", "mode": "side"}))   # renderiza mesmo em pausa
        _, msgs = _recv_until(ws, lambda j: j["type"] == "telemetry", timeout=5)
        assert msgs[-1]["t"] == t_p0, "pause must freeze integration"
        ws.send_text(json.dumps({"cmd": "resume"}))
        _recv_until(ws, lambda j: j["type"] == "telemetry" and j["t"] > t_p0 + 0.5)
        ws.send_text(json.dumps({"cmd": "stop"}))
        _, msgs = _recv_until(ws, lambda j: j["type"] == "finished", timeout=120)
        fin = msgs[-1]
    assert fin["outcome"]["text"] and "ã" not in fin["outcome"]["text"]
    run = OUT / fin["dir_url"].removeprefix("/out/").strip("/")
    for a in ("config_resolved.yaml", "timeseries.csv", "events.json", "summary.json", "summary.md",
              "summary.html", "trajectory_3d.png", "tension.png"):
        assert (run / a).exists(), a
    html = c.get(fin["report_url"]).text
    assert "Answers" in html and 'lang="en"' in html
    assert not [p for ext in ("*.mp4", "*.gif", "*.webm") for p in OUT.rglob(ext)]


def test_multitenant_independent_sessions_and_capacity():
    server.mgr.max_sessions = 2
    c = TestClient(server.app)
    with c.websocket_connect("/ws") as wa, c.websocket_connect("/ws") as wb, c.websocket_connect("/ws") as wc:
        sa, sb, sc = _hello(wa), _hello(wb), _hello(wc)
        assert len({sa, sb, sc}) == 3
        _start(wa, {"name": "visitor_a"})
        _recv_until(wa, lambda j: j["type"] == "started" and j["name"] == "visitor_a")
        _start(wb, {"name": "visitor_b", "launch": {"azimuth_deg": -60.0}})
        _recv_until(wb, lambda j: j["type"] == "started" and j["name"] == "visitor_b")
        assert server.mgr.running() == 2
        # terceira sessão: servidor cheio
        _start(wc)
        _, msgs = _recv_until(wc, lambda j: j["type"] == "error")
        assert msgs[-1].get("code") == "busy" and "server busy" in msgs[-1]["message"]
        # pausar A não afeta B
        wa.send_text(json.dumps({"cmd": "pause"}))
        _recv_until(wa, lambda j: j["type"] == "status" and j["status"] == "paused")
        time.sleep(0.3)
        A, B = server.mgr.sessions[sa], server.mgr.sessions[sb]
        t_lim = time.monotonic() + 20
        while B.last_t < 0.3 and time.monotonic() < t_lim:     # espera B emitir quadros
            time.sleep(0.05)
        ta, tb = A.last_t, B.last_t
        time.sleep(1.5)
        assert A.last_t == ta
        assert B.last_t > tb + 0.9, (tb, B.last_t)          # B segue em ~1× enquanto A está pausada
        assert A.name == "visitor_a" and B.name == "visitor_b"
        assert A.proc.pid != B.proc.pid                      # processos separados (sem disputa de GIL)
        # cada visitante só está ligado à própria sessão
        assert server.mgr.sessions[sa].clients and server.mgr.sessions[sb].clients
        assert not (server.mgr.sessions[sa].clients & server.mgr.sessions[sb].clients)


def test_reconnect_with_same_sid_reattaches():
    c = TestClient(server.app)
    with c.websocket_connect("/ws") as ws:
        sid = _hello(ws)
        _start(ws)
        _recv_until(ws, lambda j: j["type"] == "telemetry" and j["t"] > 0.5)
    assert server.mgr.sessions[sid].detached_since is not None
    with c.websocket_connect("/ws") as ws2:
        assert _hello(ws2, sid) == sid
        _, msgs = _recv_until(ws2, lambda j: j["type"] == "status" and j["status"] == "attached")
        frames, _ = _recv_until(ws2, lambda j: j["type"] == "telemetry")
    assert server.mgr.sessions[sid].last_t > 0.5


def test_abandoned_session_is_reaped(monkeypatch):
    monkeypatch.setattr(server, "DETACH_GRACE_S", 0.0)
    c = TestClient(server.app)
    with c.websocket_connect("/ws") as ws:
        sid = _hello(ws)
        _start(ws)
        _recv_until(ws, lambda j: j["type"] == "started")
    time.sleep(0.1)
    server.mgr.reap()
    assert sid not in server.mgr.sessions


def test_10_invalid_config_reports_error_in_english():
    c = TestClient(server.app)
    with c.websocket_connect("/ws") as ws:
        _hello(ws)
        ws.send_text(json.dumps({"cmd": "start", "config": {"rope": {"model": "chain"}}}))
        _, msgs = _recv_until(ws, lambda j: j["type"] == "error")
        assert msgs[-1]["message"].startswith("invalid configuration") and "chain" in msgs[-1]["message"]


def test_prune_runs_keeps_most_recent(tmp_path):
    from spinjump.report import prune_runs
    names = ["20261001-100000_a", "20261002-100000_b", "20261003-100000_c", "outra_pasta"]
    for n in names:
        (tmp_path / n).mkdir()
    assert prune_runs(2, tmp_path) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["20261002-100000_b", "20261003-100000_c", "outra_pasta"]
    assert prune_runs(0, tmp_path) == 0
