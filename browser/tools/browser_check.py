"""Verifica a versão no navegador no Chromium (Playwright): página de aviso e acesso ao simulador,
formulário (preset, valor inválido, prévia), simulação completa em velocidade máxima com relatório,
tempo real 1× (carga de CPU da física e da página), layout de celular e capturas de tela.

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


def main_thread_busy(cdp):
    m = {x["name"]: x["value"] for x in cdp.send("Performance.getMetrics")["metrics"]}
    return m["TaskDuration"], m["Timestamp"]


with sync_playwright() as p:
    br = p.chromium.launch(args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
    logs = []

    def page(vw=1440, vh=900):
        pg = br.new_page(viewport={"width": vw, "height": vh})
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        return pg

    # 1) aviso: o simulador sem confirmação volta para a página inicial; com confirmação, abre
    pg = page()
    pg.goto(f"{BASE}/sim.html")
    pg.wait_for_url(lambda u: not u.endswith("sim.html"), timeout=10000)
    report["gate_redirects_to_intro"] = pg.url
    pg.screenshot(path=str(OUT / "intro.png"), full_page=True)
    report["enter_disabled_before_ack"] = pg.is_disabled("#enter")
    pg.check("#ack")
    pg.click("#enter")
    pg.wait_for_selector("#start:not([disabled])", timeout=120000)
    report["sim_opens_after_ack"] = pg.url

    # 2) formulário: preset muda a prévia; valor inválido mostra erro e bloqueia Start
    pg.select_option("#preset", "sandbag")
    pg.wait_for_function("document.getElementById('preset-desc').textContent.includes('60.0 kg')", timeout=20000)
    report["preset_preview"] = pg.text_content("#preset-desc")
    pg.click("text=Tower")
    pg.fill("input[name='tower.height_m']", "0.5")
    pg.wait_for_selector("#errors:not([hidden])", timeout=10000)
    report["invalid_error"] = pg.text_content("#errors")
    report["start_disabled_when_invalid"] = pg.is_disabled("#start")
    pg.fill("input[name='tower.height_m']", "40")
    pg.wait_for_selector("#start:not([disabled])", timeout=20000)
    report["tower_40_preview"] = pg.text_content("#preset-desc")
    pg.screenshot(path=str(OUT / "form.png"))
    pg.close()

    # 3) execução completa em velocidade máxima + relatório
    for name, q in (("sliding", "set=wind.gust_std_ms=0"), ("locked", "set=wind.gust_std_ms=0&set=rope.coil_sliding=false")):
        pg = page()
        t0 = time.time()
        pg.goto(f"{BASE}/sim.html?ack=1&{q}&autostart=1&speed=0")
        pg.wait_for_function("window.__benchStarted === true", timeout=120000)
        load_s = time.time() - t0
        res, el = wait_result(pg, 900)
        rep = pg.evaluate("window.__report ? Object.fromEntries(Object.entries(window.__report).map(([k, v]) => [k, v.length])) : null")
        report[f"{name}_max_speed"] = dict(load_s=round(load_s, 2), wall_s=round(el, 1), result=res, report_files=rep)
        pg.screenshot(path=str(OUT / f"end_{name}.png"))
        if rep:
            html = pg.evaluate("window.__report['summary.html']")
            rp = page(1100, 900)
            rp.set_content(html)
            report[f"{name}_report_svgs"] = rp.locator("svg").count()
            rp.screenshot(path=str(OUT / f"report_{name}.png"), full_page=True)
            rp.close()
        pg.close()

    # 4) tempo real 1×: taxa, carga da física (worker) e tempo ocupado da página principal
    for name, q in (("sliding", ""), ("locked", "&set=rope.coil_sliding=false")):
        pg = page()
        cdp = pg.context.new_cdp_session(pg)
        cdp.send("Performance.enable")
        pg.goto(f"{BASE}/sim.html?ack=1{q}&speed=1")
        pg.wait_for_selector("#start:not([disabled])", timeout=120000)
        pg.click("#start")
        time.sleep(4)
        b0, t0 = main_thread_busy(cdp)
        time.sleep(10)
        b1, t1 = main_thread_busy(cdp)
        perf = pg.evaluate("window.__lastPerf || null")
        report[f"realtime_{name}"] = dict(perf=perf, main_thread_busy=round((b1 - b0) / (t1 - t0), 3))
        pg.screenshot(path=str(OUT / f"live_{name}.png"))
        print(name, report[f"realtime_{name}"], flush=True)
        pg.close()

    # 5) celular (390×844): layout
    pg = page(390, 844)
    pg.goto(f"{BASE}/sim.html?ack=1&speed=1")
    pg.wait_for_selector("#start:not([disabled])", timeout=120000)
    pg.click("#start")
    time.sleep(6)
    report["mobile_overflow_px"] = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    pg.screenshot(path=str(OUT / "mobile.png"), full_page=True)
    pg.goto(f"{BASE}/")
    report["mobile_intro_overflow_px"] = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    pg.close()
    br.close()

report["console_errors"] = [m for m in logs if m.startswith(("error", "pageerror"))][:20]
print(json.dumps(report, indent=1, default=str))
