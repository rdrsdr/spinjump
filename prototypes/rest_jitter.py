"""Ensaio isolado: manequim deitado deslizando sem corda; verifica se a rotação decai (tremulação de contato)."""
import sys, json, math
import numpy as np, mujoco
from concurrent.futures import ProcessPoolExecutor
from spinjump.config import load_config
from spinjump.model import build, lowest_geom_z

def one(args):
    sets, condim = args
    cfg = load_config(sets=sets)
    q = (math.cos(math.pi/4), 0, math.sin(math.pi/4), 0)  # deitado (eixo z do corpo -> x)
    b = build(cfg, np.array([0, 0, cfg.object.radius_m*0.75 + 0.002]), q, with_tower=False)
    m, d = b.model, b.data
    d.qpos[2] -= lowest_geom_z(m, d, b.obj_gids) - 0.001
    mujoco.mj_forward(m, d)
    if condim:
        m.pair_dim[:] = condim
    d.qvel[0] = 3.0; d.qvel[1] = 1.0
    out = []
    for k in range(int(12/m.opt.timestep)):
        mujoco.mj_step(m, d)
        if k % int(1/m.opt.timestep) == 0:
            out.append((round(d.time,1), round(float(np.linalg.norm(d.qvel[:3])),4), round(float(np.linalg.norm(d.qvel[3:6])),4)))
    return dict(sets=sets, condim=condim, last=out[-2:], dist=round(float(np.hypot(d.qpos[0], d.qpos[1])),3), expected=round(10/(2*min(cfg.ground.friction_slide, cfg.object.geom_friction)*9.81),3))

variants = [(json.loads(a), c) for a in sys.argv[1:] for c in (0, 3)]
with ProcessPoolExecutor(8) as ex:
    for r in ex.map(one, variants):
        print(json.dumps(r))
