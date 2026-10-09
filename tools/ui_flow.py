"""Teste de fluxo da interface via WebSocket: formulário → simulação → quadros ao vivo →
pausa/retomada → fator de reprodução → artefatos. Mede a taxa 1× por relógio.

Uso: python tools/ui_flow.py [http://host:8000] [--full]
"""
import asyncio
import json
import sys
import time
import urllib.request

import websockets

BASE = next((a for a in sys.argv[1:] if a.startswith("http")), "http://localhost:8000")
FULL = "--full" in sys.argv


async def main():
    res = {}
    d = json.loads(urllib.request.urlopen(BASE + "/api/defaults").read())
    assert d["config"]["rope"]["model"] == "wrap_tether"
    async with websockets.connect(BASE.replace("http", "ws") + "/ws", max_size=None) as ws:
        frames, tel = 0, []
        overrides = {"launch": {"mode": "impulse", "impulse_Ns": 320.0, "speed_ms": None, "azimuth_deg": 90.0},
                     "ui": {"playback_factor": 1.0}}
        await ws.send(json.dumps({"cmd": "start", "config": overrides}))

        async def collect(seconds):
            nonlocal frames
            t_end = time.monotonic() + seconds
            got = []
            while time.monotonic() < t_end:
                try:
                    m = await asyncio.wait_for(ws.recv(), timeout=max(0.05, t_end - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                if isinstance(m, bytes):
                    frames += 1
                    if m[:2] != b"\xff\xd8":
                        raise AssertionError("quadro não é JPEG")
                else:
                    j = json.loads(m)
                    got.append(j)
                    if j["type"] == "error":
                        raise AssertionError(j["message"])
            return got

        msgs = await collect(3.0)
        started = [m for m in msgs if m["type"] == "started"]
        assert started, "simulação não iniciou"
        f0 = frames
        w0 = time.monotonic()
        msgs = await collect(6.0)
        tl = [m for m in msgs if m["type"] == "telemetry"]
        fps = (frames - f0) / (time.monotonic() - w0)
        # taxa medida por relógio externo: Δt simulado / Δt de relógio
        a, b = tl[1], tl[-1]
        res["fps"] = round(fps, 2)
        res["rate_server_reported"] = b["rate"]
        res["sim_seconds_in_window"] = round(b["t"] - a["t"], 3)
        res["wall_seconds_in_window"] = round(b["wall_s"] - a["wall_s"], 3)
        res["rate_1x_by_server_clock"] = round((b["t"] - a["t"]) / (b["wall_s"] - a["wall_s"]), 3)
        # pausa
        await ws.send(json.dumps({"cmd": "pause"}))
        await collect(0.5)
        msgs = await collect(2.0)
        tp = [m["t"] for m in msgs if m["type"] == "telemetry"]
        res["paused_sim_time_advance"] = round(max(tp) - min(tp), 6) if tp else 0.0
        # retomada + 2×
        await ws.send(json.dumps({"cmd": "resume"}))
        await ws.send(json.dumps({"cmd": "playback", "factor": 2.0}))
        await collect(1.0)
        t_wall0 = time.monotonic()
        msgs = await collect(4.0)
        tl = [m for m in msgs if m["type"] == "telemetry"]
        res["rate_2x_by_server_clock"] = round((tl[-1]["t"] - tl[0]["t"]) / (tl[-1]["wall_s"] - tl[0]["wall_s"]), 3)
        res["rate_2x_by_client_clock"] = round((tl[-1]["t"] - tl[0]["t"]) / (time.monotonic() - t_wall0), 3)
        # câmeras
        for mode in ("side", "follow", "free"):
            await ws.send(json.dumps({"cmd": "camera", "mode": mode}))
            await collect(0.4)
        if FULL:
            await ws.send(json.dumps({"cmd": "playback", "factor": 4.0}))
        else:
            await ws.send(json.dumps({"cmd": "stop"}))
        fin = None
        t_lim = time.monotonic() + (120 if FULL else 60)
        while time.monotonic() < t_lim and fin is None:
            for m in await collect(1.0):
                if m["type"] == "finished":
                    fin = m
        assert fin, "não recebeu 'finished'"
        res["outcome"] = fin["outcome"]["code"]
        res["report_url"] = fin["report_url"]
        html = urllib.request.urlopen(BASE + fin["report_url"]).read().decode()
        res["report_ok"] = ("Notice" in html or "Aviso" in html) and ("Answers" in html or "Respostas" in html)
        res["artifacts"] = fin["artifacts"]
        res["frames_total"] = frames
    print(json.dumps(res, indent=1, ensure_ascii=False))
    ok = (res["paused_sim_time_advance"] == 0.0 and res["report_ok"] and res["fps"] > 3
          and not any(a.endswith((".mp4", ".gif")) for a in res["artifacts"]))
    print("FLUXO UI:", "OK" if ok else "FALHOU")
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
