"""Salto residual após impacto vertical (artefato de contato?) para vários solref/solimp."""
import sys, json, numpy as np, mujoco
sys.path.insert(0, "tests")
from conftest import lying_sandbag
from spinjump.model import lowest_geom_z
if __name__ == "__main__":
    for sets in (["contact.solref=[0.02,1.0]"], ["contact.solref=[0.004,1.0]"], ["contact.solref=[0.02,1.5]"],
                 ["contact.solref=[0.02,2.0]"], ["contact.solref=[0.02,1.0]","contact.solimp=[0.95,0.99,0.001]"],
                 ["contact.solref=[0.02,1.0]","contact.solimp=[0.9,0.95,0.05]"], ["contact.solref=[0.02,1.0]","contact.solimp=[0.99,0.99,0.001]"],
                 ["contact.solref=[0.01,1.0]"], ["contact.solref=[0.02,1.3]"]):
        out = []
        for v in (2.0, 6.0, 9.0):
            cfg, b = lying_sandbag(sets, z_clear=0.002)
            m, d = b.model, b.data
            d.qvel[2] = -v
            lift, pen, sep = 0.0, 0.0, 0
            touched, prev = False, False
            for _ in range(int(0.8 / m.opt.timestep)):
                mujoco.mj_step(m, d)
                low = lowest_geom_z(m, d, b.obj_gids)
                on = d.ncon > 0
                if on: touched = True
                if touched and not on and prev: sep += 1
                prev = on
                if touched: lift = max(lift, low); pen = min(pen, low)
            out.append((v, round(lift*1000, 2), round(pen*1000, 1), sep))
        print(json.dumps(sets), "(v, lift_mm, pen_mm, separações)", out)
