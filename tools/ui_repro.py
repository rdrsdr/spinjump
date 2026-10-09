"""Reproduz: fim da simulação → resultado/impactos → novo Start sem recarregar a página."""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path("out/ui_check"); OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": 1366, "height": 900})
    logs = []
    pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
    pg.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
    pg.add_init_script("sessionStorage.setItem('spinjump_ack','1');")
    pg.goto(BASE + "/app")
    pg.wait_for_selector("#form fieldset")
    pg.fill('input[name="ui.playback_factor"]', "4")
    pg.click("#btn-start")
    for i in range(24):
        time.sleep(5)
        st = pg.evaluate("[document.getElementById('t-sim').textContent, document.getElementById('phase').textContent, document.getElementById('rate').textContent, document.getElementById('result').hidden, document.getElementById('messages').innerText.slice(0,200)]")
        print(i * 5, st, flush=True)
        if not st[3]:
            break
    time.sleep(2)
    pg.evaluate("document.querySelector('.tele-panel').scrollTop = 1e6")
    res = {"events_count_label": pg.inner_text("#ev-count"), "floor_label": pg.inner_text("#tele"),"result": pg.inner_text("#result"), "events": pg.inner_text("#events"),
           "buttons": pg.evaluate("[...document.querySelectorAll('.controls button')].map(b => b.textContent + (b.disabled ? ':off' : ':on'))")}
    pg.screenshot(path=str(OUT / "repro_finished.png"))
    pg.click("#btn-start")
    time.sleep(8)
    res["after_restart_messages"] = pg.inner_text("#messages")
    res["result_hidden_after_restart"] = pg.evaluate("document.getElementById('result').hidden")
    res["t_sim"] = pg.inner_text("#t-sim")
    res["phase_after_restart"] = pg.inner_text("#phase")
    res["events_scroll"] = pg.evaluate("(() => { const e = document.getElementById('events'); return [e.scrollHeight, e.clientHeight, getComputedStyle(e).overflowY]; })()")
    pg.screenshot(path=str(OUT / "repro_restart.png"))
    res["console"] = logs[-10:]
    print(json.dumps(res, indent=1, ensure_ascii=False))
    br.close()
