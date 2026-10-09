import time, sys
from concurrent.futures import ProcessPoolExecutor
from spinjump.config import load_config
from spinjump.sim import Simulation
def one(sets):
    s = Simulation(load_config(sets=sets + ["solver.max_time_s=6"]))
    t0 = time.perf_counter(); s.run(); return round((time.perf_counter() - t0) / s.step_count * 1e6)
if __name__ == "__main__":
    for model in ("true", "false"):
        for n in (1, 2, 4):
            with ProcessPoolExecutor(n) as ex:
                r = list(ex.map(one, [[f"rope.coil_sliding={model}"]] * n))
            print(f"deslizante={model} {n} processos: µs/passo {r}", flush=True)
