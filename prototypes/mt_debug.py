import json, time, os, tempfile, threading
os.environ["SPINJUMP_OUT"] = tempfile.mkdtemp()
from fastapi.testclient import TestClient
from spinjump.web import server

def hello(ws):
    ws.send_text(json.dumps({"cmd": "hello"}))
    while True:
        m = ws.receive()
        if m.get("text") and json.loads(m["text"])["type"] == "hello":
            return json.loads(m["text"])["sid"]

if __name__ == "__main__":
    c = TestClient(server.app)
    with c.websocket_connect("/ws") as wa, c.websocket_connect("/ws") as wb:
        sa, sb = hello(wa), hello(wb)
        for w, n in ((wa, "a"), (wb, "b")):
            w.send_text(json.dumps({"cmd": "start", "config": {"name": n, "ui": {"width": 320, "height": 200}}}))
        time.sleep(4)
        A, B = server.mgr.sessions.get(sa), server.mgr.sessions.get(sb)
        print("sem ler:", A and A.last_t, B and B.last_t)
        stop = False
        def drain(w):
            while not stop:
                try: w.receive()
                except Exception: break
        th = [threading.Thread(target=drain, args=(w,), daemon=True) for w in (wa, wb)]
        [x.start() for x in th]
        t0 = (A.last_t, B.last_t); time.sleep(3)
        print("lendo 3 s:", round(A.last_t - t0[0], 2), round(B.last_t - t0[1], 2))
        stop = True
        server.mgr.close_all()
