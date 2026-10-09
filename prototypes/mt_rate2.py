import time
from spinjump.config import load_config
from spinjump.web import server

class Dummy:
    def push_msg(self, m): pass
    def push_frame(self, f): pass

if __name__ == "__main__":
    mgr = server.Manager(max_sessions=4)
    cl = Dummy(); cl.sid = "0" * 32; mgr.clients.add(cl)
    s = mgr.start(cl, load_config(sets=["ui.width=320", "ui.height=200", "launch.azimuth_deg=-60"]))
    for _ in range(12):
        time.sleep(0.5); print(round(s.last_t, 3), end=" ", flush=True)
    print()
    from spinjump.sim import Simulation
    sim = Simulation(load_config(sets=["launch.azimuth_deg=-60", "solver.max_time_s=3"]))
    t0 = time.perf_counter(); n = 0
    while sim.step():
        n += 1
        if n % 2000 == 0:
            print(f"t={sim.d.time:.2f} wall={time.perf_counter()-t0:.2f} ncon={sim.d.ncon}", flush=True)
    mgr.close_all()
