"""Taxa de cada sessão com 1 e 2 sessões simultâneas no mesmo processo (diagnóstico multitenant)."""
import time
from spinjump.config import load_config
from spinjump.web import server


class Dummy:
    def push_msg(self, m): pass
    def push_frame(self, f): pass


def run(n, secs=6.0):
    mgr = server.Manager(max_sessions=4)
    ss = []
    for i in range(n):
        cl = Dummy(); cl.sid = f"{i:032x}"
        mgr.clients.add(cl)
        ss.append(mgr.start(cl, load_config(sets=["ui.width=320", "ui.height=200"])))
    time.sleep(4.0)
    t0 = [s.last_t for s in ss]; w0 = time.perf_counter()
    time.sleep(secs)
    dt = time.perf_counter() - w0
    print(n, "sessões:", [round((s.last_t - a) / dt, 2) for s, a in zip(ss, t0)])
    mgr.close_all()


if __name__ == "__main__":
    run(1); run(2); run(3)
