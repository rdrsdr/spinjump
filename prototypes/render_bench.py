"""Mede custo de renderização OSMesa, JPEG e interferência no GIL com a física."""
import time, threading, io, sys
import numpy as np, mujoco
from PIL import Image
from spinjump.config import load_config
from spinjump.sim import Simulation
W, H = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (960, 600)
s = Simulation(load_config())
import os
if os.environ.get('FAST'):
    s.m.vis.quality.offsamples = 0
    s.m.vis.quality.shadowsize = 0
r = mujoco.Renderer(s.m, H, W, max_geom=3000)
r.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0 if os.environ.get('FAST') else 1
r.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = 0
cam = mujoco.MjvCamera(); cam.lookat[:] = (0,0,25); cam.distance = 100; cam.azimuth = -60; cam.elevation = -12
r.update_scene(s.d, cam); r.render()
t0=time.perf_counter()
for i in range(20):
    r.update_scene(s.d, cam); img = r.render()
tr=(time.perf_counter()-t0)/20
t0=time.perf_counter()
for i in range(20):
    b=io.BytesIO(); Image.fromarray(img).save(b, 'JPEG', quality=80)
tj=(time.perf_counter()-t0)/20
print('size', W, H, 'render ms', round(tr*1e3,1), 'jpeg ms', round(tj*1e3,1), 'bytes', len(b.getvalue()))
def phys(n, out):
    t0=time.perf_counter()
    for _ in range(n): s.step()
    out.append(time.perf_counter()-t0)
o=[]; phys(4000,o); alone=o[0]
stop=False
def rend():
    while not stop:
        r.update_scene(s.d, cam); r.render()
th=threading.Thread(target=rend); o=[]
th.start(); phys(4000,o); stop=True; th.join()
print('physics 4000 steps alone s', round(alone,3), 'with render thread s', round(o[0],3))
