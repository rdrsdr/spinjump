"""Verifica o protótipo no Chromium (Playwright): carregamento, simulação completa em velocidade
máxima, tempo real com CPU desacelerada (aproximação de celulares) e capturas de tela.

Uso: browser/tools/browser_check.sh  (sobe um servidor estático e roda este script num container)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "out/browser")
OUT.mkdir(parents=True, exist_ok=True)
report = {}


def wait_result(pg, timeout_s):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = pg.evaluate("window.__benchResult || null")
        if r:
            return r, time.time() - t0
        time.sleep(0.5)
    return None, time.time() - t0


with sync_playwright() as p:
    br = p.chromium.launch(args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
    logs = []

    def page(vw=1366, vh=860, throttle=1.0):
        pg = br.new_page(viewport={"width": vw, "height": vh})
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        if throttle > 1:
            cdp = pg.context.new_cdp_session(pg)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
        return pg

    # 1) cenário completo em velocidade máxima (desktop, sem limitação)
    for scen in ("cmp_sliding", "cmp_locked"):
        pg = page()
        t0 = time.time()
        pg.goto(f"{BASE}/?bench={scen}&speed=0")
        pg.wait_for_function("window.__benchStarted === true", timeout=60000)
        report[f"{scen}_load_s"] = round(time.time() - t0, 2)
        res, el = wait_result(pg, 600)
        report[f"{scen}_max_speed"] = dict(wall_s=round(el, 1), result=res)
        pg.screenshot(path=str(OUT / f"end_{scen}.png"))
        pg.close()

    # 2) tempo real (1×) com CPU desacelerada: taxa efetiva após alguns segundos (worker também é limitado)
    for thr in (1, 4, 6):
        pg = page(throttle=thr)
        try:
            t0 = time.time()
            pg.goto(f"{BASE}/?scenario=default&speed=1")
            pg.wait_for_selector("#start:not([disabled])", timeout=180000)
            ready = time.time() - t0
            pg.click("#start")
            time.sleep(14)
            perf = pg.evaluate("window.__lastPerf || null")
            report[f"realtime_throttle_{thr}x"] = dict(ready_s=round(ready, 1), perf=perf)
        except Exception as e:  # registra e segue
            report[f"realtime_throttle_{thr}x"] = dict(error=str(e).splitlines()[0],
                                                     state=pg.evaluate("[document.getElementById('start').disabled, document.getElementById('loading').textContent]"))
        pg.screenshot(path=str(OUT / f"live_throttle_{thr}x.png"))
        print(thr, report[f"realtime_throttle_{thr}x"], flush=True)
        pg.close()

    # 3) celular (390×844): layout
    pg = page(390, 844)
    pg.goto(f"{BASE}/?scenario=default&speed=1")
    pg.wait_for_selector("#start:not([disabled])", timeout=120000)
    pg.click("#start")
    time.sleep(6)
    report["mobile_overflow_px"] = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    pg.screenshot(path=str(OUT / "mobile.png"), full_page=True)
    pg.close()
    br.close()

report["console_errors"] = [m for m in logs if m.startswith(("error", "pageerror"))][:20]
print(json.dumps(report, indent=1, default=str))
