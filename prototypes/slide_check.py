import math, numpy as np, mujoco, json, sys
from spinjump.config import load_config
from spinjump.model import build, lowest_geom_z
for sets in (["contact.solref=[0.004,1.0]"], ["contact.solref=[0.02,1.0]"], ["contact.solref=[0.004,1.0]","ground.friction_rolling=0.02","ground.friction_torsional=0.02"]):
    cfg = load_config(sets=sets)
    mu = min(cfg.ground.friction_slide, cfg.object.geom_friction)
    xml = f"""<mujoco><option timestep="{cfg.solver.timestep_s}" integrator="implicitfast" cone="elliptic"/>
    <worldbody><geom name="ground" type="plane" size="50 50 1"/>
    <body name="b" pos="0 0 0.1005"><freejoint/><geom name="box" type="box" size="0.3 0.2 0.1" mass="80"/></body></worldbody>
    <contact><pair geom1="box" geom2="ground" condim="6" friction="{mu} {mu} {cfg.ground.friction_torsional} {cfg.ground.friction_rolling} {cfg.ground.friction_rolling}" solref="{' '.join(map(str,cfg.contact.solref))}" solimp="{' '.join(map(str,cfg.contact.solimp))}"/></contact></mujoco>"""
    m = mujoco.MjModel.from_xml_string(xml.replace('<geom name="ground"','<geom contype="0" conaffinity="0" name="ground"').replace('<geom name="box"','<geom contype="0" conaffinity="0" name="box"'))
    d = mujoco.MjData(m)
    for _ in range(2000): mujoco.mj_step(m, d)  # assentar
    x0 = d.qpos[:2].copy(); v0 = 5.0; d.qvel[0] = v0
    while True:
        mujoco.mj_step(m, d)
        if np.linalg.norm(d.qvel[:3]) < 1e-3 or d.time > 10: break
    dist = float(np.linalg.norm(d.qpos[:2]-x0)); exp = v0**2/(2*mu*9.81)
    # saco deslizando ao longo do eixo
    cfg2 = load_config(sets=sets+["object.type=sandbag"])
    q = (math.cos(math.pi/4), 0, math.sin(math.pi/4), 0)
    b = build(cfg2, np.array([0,0,0.5]), q, with_tower=False); m2, d2 = b.model, b.data
    d2.qpos[2] -= lowest_geom_z(m2, d2, b.obj_gids) - 0.0005; mujoco.mj_forward(m2, d2)
    for _ in range(2000): mujoco.mj_step(m2, d2)
    x0 = d2.qpos[:2].copy(); d2.qvel[0] = v0
    while True:
        mujoco.mj_step(m2, d2)
        if np.linalg.norm(d2.qvel[:3]) < 1e-3 or d2.time > 12: break
    dist2 = float(np.linalg.norm(d2.qpos[:2]-x0))
    print(json.dumps(dict(sets=sets, box=round(dist,4), sandbag_axial=round(dist2,4), expected=round(exp,4), err_box=round(dist/exp-1,4), err_bag=round(dist2/exp-1,4))))
