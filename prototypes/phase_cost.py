import time
from spinjump.config import load_config
from spinjump.sim import Simulation
if __name__ == "__main__":
    s = Simulation(load_config())
    acc = {1: [0.0, 0], 2: [0.0, 0]}
    while True:
        ph = 2 if s.tr.first_ground_t is not None else 1
        t0 = time.perf_counter(); ok = s.step(); dt = time.perf_counter() - t0
        acc[ph][0] += dt; acc[ph][1] += 1
        if not ok: break
    for k, (t, n) in acc.items():
        print({1: "ar", 2: "solo"}[k], "passos", n, "us/passo", round(t / n * 1e6, 1), "CPU s/s simulado", round(t / n / s.dt, 3))
    print("ncon típico no solo:", s.d.ncon)
