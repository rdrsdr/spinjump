"""Protótipo de ensaio do plugin mujoco.elasticity.cable (fase 2 do planning.md).

Cenário: cilindro rígido vertical, corda em hélice de passo curto presa a uma
âncora logo abaixo do topo, trecho livre tangente até uma massa terminal de
80 kg, lançamento com velocidade no sentido de desenrolamento.

Mede: liberação de voltas (ângulo do ponto de saída), deslizamento vertical das
espiras, penetração corda-parede, tração na âncora e na massa, estabilidade
(NaN/avisos) e custo de CPU por segundo simulado.

Uso (dentro do container):
  python prototypes/cable_plugin_proto.py --height 50 --seg 0.2 --tsim 4
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import mujoco
import numpy as np


def build_xml(a) -> tuple[str, dict]:
    R = a.diameter / 2
    rc = R + a.rope_d / 2  # raio da linha de centro da corda
    pitch = a.pitch_factor * a.rope_d
    circ = 2 * math.pi * rc
    free0 = a.free0
    wound = a.length - free0
    turns = wound / circ
    z_anchor = a.height - a.anchor_below_top
    # vértices: hélice (ccw, subindo) + trecho livre tangente
    n_w = max(4, int(round(wound / a.seg)))
    verts = []
    for i in range(n_w + 1):
        s = wound * i / n_w
        phi = s / rc
        z = z_anchor + pitch * phi / (2 * math.pi)
        verts.append((rc * math.cos(phi), rc * math.sin(phi), z))
    phi_e = wound / rc
    t = np.array([-math.sin(phi_e), math.cos(phi_e), 0.0])
    p_e = np.array(verts[-1])
    n_f = max(1, int(round(free0 / a.seg)))
    for i in range(1, n_f + 1):
        verts.append(tuple(p_e + t * free0 * i / n_f))
    vstr = " ".join(f"{x:.6f} {y:.6f} {z:.6f}" for x, y, z in verts)
    tip = np.array(verts[-1])
    nverts = len(verts)
    # massa (esfera equivalente) logo após a ponta, no prolongamento tangente
    obj_pos = tip + t * a.obj_r
    # ponto de fixação e direção de lançamento (desenrolar = componente radial externa)
    n_out = np.array([math.cos(phi_e), math.sin(phi_e), 0.0])
    az = math.radians(a.azimuth)
    vdir = math.cos(az) * t + math.sin(az) * n_out
    v0 = a.speed * vdir
    rope_mass_per_len = a.lin_density
    # densidade volumétrica equivalente para a cápsula da corda
    area = math.pi * (a.rope_d / 2) ** 2
    rho = rope_mass_per_len / area
    xml = f"""
<mujoco model="cable_proto">
  <extension><plugin plugin="mujoco.elasticity.cable"/></extension>
  <compiler autolimits="true"/>
  <option timestep="{a.dt}" integrator="implicitfast" cone="{a.cone}" solver="{a.solver}" iterations="{a.iterations}" gravity="0 0 -9.81"/>
  <size memory="2G"/>
  <worldbody>
    <geom name="ground" type="plane" size="200 200 0.1" rgba=".3 .3 .3 1"/>
    <geom name="tower" type="cylinder" pos="0 0 {a.height/2}" size="{R} {a.height/2}"
          friction="{a.mu_wall} 0.005 0.0001" contype="1" conaffinity="2" rgba=".6 .5 .4 1"/>
    <composite prefix="r" type="cable" vertex="{vstr}" initial="none">
      <plugin plugin="mujoco.elasticity.cable">
        <config key="twist" value="{a.twist_G}"/>
        <config key="bend" value="{a.bend_E}"/>
        <config key="vmax" value="0"/>
      </plugin>
      <joint kind="main" damping="{a.joint_damping}" armature="{a.armature}"/>
      <geom type="capsule" size="{a.rope_d/2}" density="{rho}" contype="2" conaffinity="1"
            friction="{a.mu_wall} 0.005 0.0001" condim="3" rgba=".9 .2 .1 1"/>
    </composite>
    <body name="obj" pos="{obj_pos[0]} {obj_pos[1]} {obj_pos[2]}">
      <freejoint name="obj"/>
      <geom name="obj" type="sphere" size="{a.obj_r}" mass="{a.mass}" contype="2" conaffinity="1"/>
      <site name="att" pos="{-t[0]*a.obj_r} {-t[1]*a.obj_r} 0"/>
    </body>
  </worldbody>
  <equality>
    <connect name="tie" body1="obj" body2="rB_last" anchor="{-t[0]*a.obj_r} {-t[1]*a.obj_r} 0"/>
  </equality>
</mujoco>"""
    meta = dict(R=R, rc=rc, pitch=pitch, turns0=turns, wound0=wound, nverts=nverts,
                z_anchor=z_anchor, v0=v0.tolist(), rho_rope=rho)
    return xml, meta


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--height", type=float, default=50.0)
    p.add_argument("--diameter", type=float, default=5.0)
    p.add_argument("--length", type=float, default=86.6)
    p.add_argument("--free0", type=float, default=2.2)
    p.add_argument("--rope_d", type=float, default=0.012)
    p.add_argument("--lin_density", type=float, default=0.075)
    p.add_argument("--pitch_factor", type=float, default=1.05)
    p.add_argument("--anchor_below_top", type=float, default=0.3)
    p.add_argument("--seg", type=float, default=0.2)
    p.add_argument("--bend_E", type=float, default=5e7)
    p.add_argument("--twist_G", type=float, default=2e7)
    p.add_argument("--joint_damping", type=float, default=0.01)
    p.add_argument("--armature", type=float, default=0.0)
    p.add_argument("--mu_wall", type=float, default=0.4)
    p.add_argument("--mass", type=float, default=80.0)
    p.add_argument("--obj_r", type=float, default=0.25)
    p.add_argument("--speed", type=float, default=8.0)
    p.add_argument("--azimuth", type=float, default=90.0)
    p.add_argument("--dt", type=float, default=0.0005)
    p.add_argument("--tsim", type=float, default=4.0)
    p.add_argument("--out", type=str, default="prototypes/results")
    p.add_argument("--tag", type=str, default="")
    p.add_argument("--cone", type=str, default="elliptic")
    p.add_argument("--solver", type=str, default="Newton")
    p.add_argument("--iterations", type=int, default=100)
    p.add_argument("--max_steps", type=int, default=0)
    a = p.parse_args()

    xml, meta = build_xml(a)
    # o composite nomeia o último corpo com sufixo; descobrir e reescrever
    spec_try = None
    try:
        m = mujoco.MjModel.from_xml_string(xml)
    except ValueError as e:
        # descobrir nome do último corpo do cabo
        tmp = xml.replace('<equality>', '<!--').replace('</equality>', '-->')
        m0 = mujoco.MjModel.from_xml_string(tmp)
        names = [mujoco.mj_id2name(m0, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(m0.nbody)]
        last = [n for n in names if n and n.startswith("rB")][-1]
        xml = xml.replace("rB_last", last)
        m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    bnames = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(m.nbody)]
    rope_ids = [i for i, n in enumerate(bnames) if n and n.startswith("rB")]
    obj_id = bnames.index("obj")
    # velocidade inicial do objeto
    jadr = m.jnt_dofadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "obj")]
    d.qvel[jadr:jadr + 3] = meta["v0"]
    mujoco.mj_forward(m, d)
    tower_gid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "tower")
    R, rc = meta["R"], meta["rc"]

    nsteps = int(round(a.tsim / a.dt))
    if a.max_steps:
        nsteps = min(nsteps, a.max_steps)
    sample_every = max(1, int(round(0.05 / a.dt)))
    rows = []
    t0 = time.perf_counter()
    status = "ok"
    max_pen = 0.0
    eq_id = 0
    for k in range(nsteps):
        t_prev = d.time
        mujoco.mj_step(m, d)
        if not np.all(np.isfinite(d.qpos)) or d.warning[mujoco.mjtWarning.mjWARN_BADQACC].number > 0:
            status = f"numerical_failure@t={t_prev:.4f}"
            d.time = t_prev
            break
        if k % sample_every == 0:
            mujoco.mj_rnePostConstraint(m, d)
            xp = d.xpos[rope_ids]
            rad = np.hypot(xp[:, 0], xp[:, 1])
            on_wall = rad < rc + a.rope_d  # em contato (tolerância de 1 diâmetro)
            # índice do último corpo ainda em contato contínuo desde a âncora
            n_on = 0
            for flag in on_wall:
                if flag:
                    n_on += 1
                else:
                    break
            wound_len = n_on * a.seg
            ang = np.unwrap(np.arctan2(xp[:n_on, 1], xp[:n_on, 0])) if n_on > 1 else np.array([0.0])
            # penetração em contatos corda-torre
            pen = 0.0
            for c in range(d.ncon):
                con = d.contact[c]
                if con.geom1 == tower_gid or con.geom2 == tower_gid:
                    pen = min(pen, con.dist)
            max_pen = min(max_pen, pen)
            # tração na âncora = força de interação do 1º corpo móvel com o pai fixo
            f_anchor = np.linalg.norm(d.cfrc_int[rope_ids[1], 3:]) if len(rope_ids) > 1 else 0.0
            # tração no objeto = força da restrição connect
            efc = d.efc_force[d.efc_type == mujoco.mjtConstraint.mjCNSTR_EQUALITY]
            f_obj = float(np.linalg.norm(efc[:3])) if efc.size >= 3 else float("nan")
            zc = xp[:n_on, 2] if n_on else np.array([np.nan])
            op = d.xpos[obj_id]
            ov = d.cvel[obj_id]
            rows.append(dict(t=round(d.time, 4), wound_len=wound_len, n_on=n_on,
                             wound_turns=(ang[-1] - ang[0]) / (2 * math.pi) if n_on > 1 else 0.0,
                             coil_zmin=float(np.nanmin(zc)), coil_zmax=float(np.nanmax(zc)),
                             pen_min=pen, T_anchor=float(f_anchor), T_obj=f_obj,
                             obj=[float(x) for x in op], obj_rad=float(np.hypot(op[0], op[1])),
                             ncon=int(d.ncon)))
    wall = time.perf_counter() - t0
    timers = {n: float(d.timer[getattr(mujoco.mjtTimer, n)].duration) for n in
              ("mjTIMER_STEP", "mjTIMER_POS_COLLISION", "mjTIMER_CONSTRAINT", "mjTIMER_POS_MAKE",
               "mjTIMER_POS_PROJECT", "mjTIMER_ADVANCE")}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res = dict(args=vars(a), meta={k: v for k, v in meta.items()}, status=status,
               sim_time=float(d.time), wall_s=wall, cost_per_sim_s=wall / max(d.time, 1e-9),
               nbody=m.nbody, nv=m.nv, max_penetration_m=max_pen, timers=timers, ncon_last=int(d.ncon),
               nefc_last=int(d.nefc), solver_niter=int(d.solver_niter[0]), samples=rows)
    tag = a.tag or f"h{a.height:g}_seg{a.seg:g}_v{a.speed:g}_az{a.azimuth:g}"
    (out / f"cable_{tag}.json").write_text(json.dumps(res, indent=1))
    # resumo curto
    s0, s1 = rows[0], rows[-1]
    print(json.dumps(dict(tag=tag, status=status, sim=round(d.time, 3), wall=round(wall, 1),
                          cost_per_sim_s=round(res['cost_per_sim_s'], 2), nv=m.nv,
                          turns0=round(meta['turns0'], 2),
                          wound_len_start=s0['wound_len'], wound_len_end=s1['wound_len'],
                          wound_turns_end=round(s1['wound_turns'], 2),
                          coil_z_start=[round(s0['coil_zmin'], 3), round(s0['coil_zmax'], 3)],
                          coil_z_end=[round(s1['coil_zmin'], 3), round(s1['coil_zmax'], 3)],
                          max_pen_mm=round(max_pen * 1000, 2),
                          T_obj_max=round(max(r['T_obj'] for r in rows), 1),
                          T_anchor_max=round(max(r['T_anchor'] for r in rows), 1),
                          obj_end=[round(x, 2) for x in s1['obj']],
                          obj_rad_min=round(min(r['obj_rad'] for r in rows), 2),
                          ncon=int(d.ncon), nefc=int(d.nefc), niter=int(d.solver_niter[0]),
                          timers={k[8:]: round(v, 2) for k, v in timers.items()})))


if __name__ == "__main__":
    main()
