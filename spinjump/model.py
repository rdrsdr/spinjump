"""Geração programática do modelo MJCF a partir da configuração validada.

Matriz de colisões (todas as geoms têm contype=conaffinity=0; os pares são
declarados explicitamente em ``<contact><pair>``):

=================  ======  ======  =======  =====
                   solo    torre   objeto   corda
=================  ======  ======  =======  =====
objeto (geoms)     sim     sim     não(1)   não(2)
corda              não(3)  geom.(4) não(2)  não(5)
=================  ======  ======  =======  =====

(1) geoms do mesmo corpo rígido; (2) a corda é presa num ponto do objeto e não
se modela contato lateral corda-objeto; (3) o trecho livre parte do alto e só
toca o solo na ponta presa ao objeto; (4) a corda nunca penetra a torre por
construção: a parte enrolada está sobre o raio ``D/2 + d/2`` e o trecho livre
sai tangente ao cilindro; (5) passo da hélice >= diâmetro.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import mujoco
import numpy as np

from .config import G, SimConfig


@dataclass
class GeomSpec:
    name: str
    kind: str            # capsule | sphere
    p0: tuple            # extremidade 1 (capsule) ou centro (sphere), no referencial do corpo
    p1: tuple | None
    radius: float
    rgba: str

    def volume(self) -> float:
        r = self.radius
        sph = 4.0 / 3.0 * math.pi * r ** 3
        if self.kind == "sphere":
            return sph
        ln = float(np.linalg.norm(np.subtract(self.p1, self.p0)))
        return math.pi * r * r * ln + sph


def object_geoms(cfg: SimConfig) -> list[GeomSpec]:
    """Geoms do objeto no referencial do corpo (origem nos pés/base, eixo z para cima)."""
    o = cfg.object
    h, r = o.height_m, o.radius_m
    skin = "0.95 0.75 0.35 1"
    if o.type == "sandbag":
        rr = min(r, 0.49 * h)
        return [GeomSpec("bag", "capsule", (0, 0, rr), (0, 0, h - rr), rr, "0.75 0.65 0.45 1")]
    # manequim: proporções antropométricas aproximadas (corpo rígido único)
    rt = 0.75 * r        # tronco
    rl = 0.40 * r        # pernas
    ra = 0.30 * r        # braços
    rh = 0.065 * h       # cabeça
    leg_x = 0.45 * r
    arm_x = rt + ra
    gs = [
        GeomSpec("torso", "capsule", (0, 0, 0.52 * h + rt * 0.3), (0, 0, 0.80 * h), rt, "0.2 0.45 0.85 1"),
        GeomSpec("head", "sphere", (0, 0, h - rh), None, rh, skin),
        GeomSpec("leg_l", "capsule", (leg_x, 0, rl), (leg_x, 0, 0.50 * h), rl, "0.25 0.25 0.3 1"),
        GeomSpec("leg_r", "capsule", (-leg_x, 0, rl), (-leg_x, 0, 0.50 * h), rl, "0.25 0.25 0.3 1"),
        GeomSpec("arm_l", "capsule", (arm_x, 0, 0.78 * h), (arm_x + 0.02, 0, 0.47 * h), ra, skin),
        GeomSpec("arm_r", "capsule", (-arm_x, 0, 0.78 * h), (-arm_x - 0.02, 0, 0.47 * h), ra, skin),
    ]
    return gs


def object_extent_radius(cfg: SimConfig) -> float:
    """Maior afastamento horizontal das geoms do objeto em relação ao eixo do corpo."""
    ext = 0.0
    for gsp in object_geoms(cfg):
        for pnt in (gsp.p0, gsp.p1):
            if pnt is None:
                continue
            ext = max(ext, math.hypot(pnt[0], pnt[1]) + gsp.radius)
    return ext


def pair_friction(surface_mu: float, object_mu: float) -> float:
    """Atrito do par: o menor dos dois coeficientes (superfície mais escorregadia domina)."""
    return min(surface_mu, object_mu)


def build_xml(cfg: SimConfig, obj_pos: np.ndarray, obj_quat=(1, 0, 0, 0),
              with_tower: bool = True) -> str:
    t, gr, ct, sv = cfg.tower, cfg.ground, cfg.contact, cfg.solver
    R, H = t.diameter_m / 2, t.height_m
    geoms = object_geoms(cfg)
    vol = sum(gs.volume() for gs in geoms)
    dens = cfg.object.mass_kg / vol
    a_h = cfg.object.attach_height_fraction * cfg.object.height_m
    solref = " ".join(f"{v:g}" for v in ct.solref)
    solimp = " ".join(f"{v:g}" for v in ct.solimp)
    half = gr.size_m / 2
    mu_g = pair_friction(gr.friction_slide, cfg.object.geom_friction)
    mu_w = pair_friction(t.wall_friction, cfg.object.geom_friction)
    gxml = []
    for gs in geoms:
        if gs.kind == "sphere":
            gxml.append(f'<geom name="obj_{gs.name}" type="sphere" pos="{gs.p0[0]:g} {gs.p0[1]:g} {gs.p0[2]:g}" '
                        f'size="{gs.radius:g}" density="{dens:.6g}" rgba="{gs.rgba}"/>')
        else:
            ft = " ".join(f"{v:.6g}" for v in (*gs.p0, *gs.p1))
            gxml.append(f'<geom name="obj_{gs.name}" type="capsule" fromto="{ft}" size="{gs.radius:g}" '
                        f'density="{dens:.6g}" rgba="{gs.rgba}"/>')
    pairs = []
    for gs in geoms:
        pairs.append(f'<pair geom1="obj_{gs.name}" geom2="ground" condim="6" '
                     f'friction="{mu_g:g} {mu_g:g} {gr.friction_torsional:g} {gr.friction_rolling:g} {gr.friction_rolling:g}" '
                     f'solref="{solref}" solimp="{solimp}"/>')
        if with_tower:
            pairs.append(f'<pair geom1="obj_{gs.name}" geom2="tower" condim="3" '
                         f'friction="{mu_w:g} {mu_w:g} 0.005 0.0001 0.0001" solref="{solref}" solimp="{solimp}"/>')
    tower_xml = (f'<geom name="tower" type="cylinder" pos="0 0 {H / 2:g}" size="{R:g} {H / 2:g}" '
                 f'rgba="0.62 0.52 0.45 1" material="brick"/>') if with_tower else ""
    q = " ".join(f"{v:.9g}" for v in obj_quat)
    xml = f"""<mujoco model="spinjump">
  <compiler angle="radian" inertiafromgeom="true" autolimits="true"/>
  <option timestep="{sv.timestep_s:g}" integrator="{sv.integrator}" iterations="{sv.iterations}"
          cone="{ct.cone}" impratio="{ct.impratio:g}" gravity="0 0 {-G:g}" density="0" viscosity="0"/>
  <size memory="64M"/>
  <visual>
    <global offwidth="{cfg.ui.width}" offheight="{cfg.ui.height}" azimuth="-60" elevation="-15"/>
    <quality shadowsize="2048" offsamples="4"/>
    <headlight ambient="0.35 0.35 0.38" diffuse="0.55 0.55 0.55" specular="0.1 0.1 0.1"/>
    <map znear="0.01" zfar="5000"/>
  </visual>
  <asset>
    <texture name="sky" type="skybox" builtin="gradient" rgb1="0.55 0.7 0.9" rgb2="0.95 0.97 1" width="256" height="256"/>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.42 0.45 0.40" rgb2="0.38 0.41 0.36" width="512" height="512"/>
    <material name="ground" texture="grid" texrepeat="{gr.size_m / 10:g} {gr.size_m / 10:g}" reflectance="0"/>
    <texture name="brick" type="cube" builtin="flat" rgb1="0.62 0.50 0.42" rgb2="0.5 0.4 0.33" mark="random" random="0.15" markrgb="0.45 0.36 0.3" width="128" height="128"/>
    <material name="brick" texture="brick" reflectance="0"/>
  </asset>
  <worldbody>
    <light name="sun" directional="true" pos="0 0 100" dir="-0.4 0.3 -1" diffuse="0.7 0.7 0.65" castshadow="true"/>
    <geom name="ground" type="plane" size="{half:g} {half:g} 1" material="ground" contype="0" conaffinity="0"/>
    {tower_xml}
    <body name="object" pos="{obj_pos[0]:.9g} {obj_pos[1]:.9g} {obj_pos[2]:.9g}" quat="{q}">
      <freejoint name="object"/>
      {' '.join(gxml)}
      <site name="attach" pos="0 0 {a_h:g}" size="0.03" rgba="1 0.9 0 1"/>
    </body>
  </worldbody>
  <default/>
  <contact>
    {' '.join(pairs)}
  </contact>
</mujoco>"""
    # todas as geoms sem colisão automática; somente os pares acima
    xml = xml.replace('<geom name="obj_', '<geom contype="0" conaffinity="0" name="obj_')
    xml = xml.replace('<geom name="tower"', '<geom contype="0" conaffinity="0" name="tower"')
    return xml


@dataclass
class Built:
    model: mujoco.MjModel
    data: mujoco.MjData
    body_id: int
    site_id: int
    ground_gid: int
    tower_gid: int
    obj_gids: list[int]
    mass: float
    xml: str


def build(cfg: SimConfig, obj_pos: np.ndarray, obj_quat=(1, 0, 0, 0), with_tower: bool = True) -> Built:
    xml = build_xml(cfg, obj_pos, obj_quat, with_tower)
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "object")
    sid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "attach")
    gg = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "ground")
    tg = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "tower") if with_tower else -1
    og = [i for i in range(m.ngeom) if m.geom_bodyid[i] == bid]
    mujoco.mj_forward(m, d)
    return Built(m, d, bid, sid, gg, tg, og, float(m.body_mass[bid]), xml)


def lowest_geom_z(m: mujoco.MjModel, d: mujoco.MjData, gids: list[int]) -> float:
    """Altura do ponto mais baixo das geoms (esferas e cápsulas) no estado atual."""
    low = 1e9
    for g in gids:
        pos = d.geom_xpos[g]
        r = m.geom_size[g, 0]
        if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_CAPSULE:
            ax = d.geom_xmat[g].reshape(3, 3)[:, 2] * m.geom_size[g, 1]
            low = min(low, pos[2] - abs(ax[2]) - r)
        else:
            low = min(low, pos[2] - r)
    return float(low)
