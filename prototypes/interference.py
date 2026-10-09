"""Física isolada vs. física com um processo de render concorrente vs. com thread ociosa."""
import time, multiprocessing as mp, threading, sys
from spinjump.config import load_config
from spinjump.sim import Simulation

def renderer_loop(stop):
    from spinjump.render import SceneRenderer, frame_state, CameraState, encode_jpeg
    s = Simulation(load_config())
    sr = SceneRenderer(s.b.xml, 960, 600, 0.04, 50)
    fs = frame_state(s, 12)
    while not stop.is_set():
        encode_jpeg(sr.render(fs, CameraState()), 80)

def bench(label):
    s = Simulation(load_config(sets=['solver.max_time_s=4']))
    t0 = time.perf_counter(); s.run(); dt = time.perf_counter() - t0
    print(label, 'us/step', round(dt / s.step_count * 1e6, 1), flush=True)

if __name__ == "__main__":
    bench("isolada")
    ctx = mp.get_context("spawn"); stop = ctx.Event()
    p = ctx.Process(target=renderer_loop, args=(stop,)); p.start(); time.sleep(3)
    bench("com processo renderizando")
    stop.set(); p.join()
    flag = [True]
    def spin():
        while flag[0]:
            time.sleep(0.001)
    th = threading.Thread(target=spin); th.start()
    bench("com thread acordando a cada 1 ms")
    flag[0] = False; th.join()
