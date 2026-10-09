"""Verificação de layout no navegador (Playwright/Chromium, fora do produto).

Abre a página inicial (sobre e segurança), confirma o aviso, entra no simulador, inicia uma
simulação, espera quadros ao vivo, salva capturas e verifica que nenhum elemento visível sobrepõe
a imagem da cena. Os demais viewports reutilizam a mesma sessão (mesmo sid).
Uso: python tools/ui_layout.py http://host:8000 saida/
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "out/ui_check")
OUT.mkdir(parents=True, exist_ok=True)
VIEWPORTS = [(1366, 768), (1920, 1080), (1024, 768), (390, 844)]

OVERLAP_JS = """
() => {
  const img = document.getElementById('frame');
  const r = img.getBoundingClientRect();
  const bad = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (el === img || el.contains(img) || img.contains(el)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;
    if (el.offsetParent === null && cs.position !== 'fixed') continue;
    const b = el.getBoundingClientRect();
    if (b.width === 0 || b.height === 0) continue;
    const ix = Math.min(r.right, b.right) - Math.max(r.left, b.left);
    const iy = Math.min(r.bottom, b.bottom) - Math.max(r.top, b.top);
    if (ix > 1 && iy > 1) bad.push(el.tagName + '#' + el.id + '.' + el.className);
  }
  return {img: [r.left, r.top, r.width, r.height], overlaps: bad,
          hscroll: document.documentElement.scrollWidth > window.innerWidth + 1};
}
"""

res = {}
with sync_playwright() as p:
    br = p.chromium.launch()
    sid = None
    for i, (w, h) in enumerate(VIEWPORTS):
        pg = br.new_page(viewport={"width": w, "height": h})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        if i == 0:
            pg.goto(BASE + "/")
            pg.wait_for_selector("#ack")
            pg.screenshot(path=str(OUT / f"intro_{w}x{h}.png"), full_page=True)
            assert pg.is_disabled("#enter"), "botão deve começar desabilitado"
            pg.check("#ack")
            pg.click("#enter")
            pg.wait_for_url("**/app*")
        else:
            pg.add_init_script(f"sessionStorage.setItem('spinjump_ack','1');sessionStorage.setItem('spinjump_sid','{sid}');")
            pg.goto(BASE + "/app")
        pg.wait_for_selector("#form fieldset")
        if i == 0:
            pg.select_option('select[name="launch.mode"]', "impulse")
            pg.fill('input[name="launch.impulse_Ns"]', "400")
            pg.click("#btn-start")
        pg.wait_for_function("document.getElementById('frame').naturalWidth > 0", timeout=60000)
        if i == 0:
            sid = pg.evaluate("sessionStorage.getItem('spinjump_sid')")
        t0 = pg.eval_on_selector("#t-sim", "e => e.textContent")
        time.sleep(4)
        t1 = pg.eval_on_selector("#t-sim", "e => e.textContent")
        info = pg.evaluate(OVERLAP_JS)
        info["t_sim_advanced"] = [t0, t1]
        info["js_errors"] = errors
        info["rate_text"] = pg.eval_on_selector("#rate", "e => e.textContent")
        info["server_load"] = pg.eval_on_selector("#server-load", "e => e.textContent")
        pg.screenshot(path=str(OUT / f"ui_{w}x{h}.png"), full_page=False)
        if i == 0:
            pg.click("#btn-pause")
            time.sleep(1.5)
            a = pg.eval_on_selector("#t-sim", "e => e.textContent")
            time.sleep(1.5)
            b = pg.eval_on_selector("#t-sim", "e => e.textContent")
            info["paused_t"] = [a, b]
            pg.click("#btn-resume")
            time.sleep(1.5)
            info["resumed_t"] = pg.eval_on_selector("#t-sim", "e => e.textContent")
            for cam in ("side", "follow", "free"):
                pg.click(f'button[data-cam="{cam}"]')
                time.sleep(1.2)
                pg.screenshot(path=str(OUT / f"ui_cam_{cam}.png"))
        res[f"{w}x{h}"] = info
        pg.close()
    # sem confirmação, /app volta para a página inicial
    pg = br.new_page()
    pg.goto(BASE + "/app")
    pg.wait_for_url(BASE + "/")
    res["gate_redirects_to_intro"] = True
    pg.close()
    br.close()
print(json.dumps(res, indent=1, ensure_ascii=False))
ok = all(not v["overlaps"] and not v["js_errors"] and not v["hscroll"] for k, v in res.items() if isinstance(v, dict))
print("LAYOUT:", "OK" if ok else "PROBLEMAS")
