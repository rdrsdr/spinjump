// Porte de spinjump/model.py: geoms do objeto e geração do MJCF a partir da configuração resolvida.
// O texto gerado é idêntico ao do Python (formatação %g reproduzida em fmtG), o que permite
// comparar os dois diretamente (tools/check_config.mjs).
import { G } from './config.js';

/** Formatação "{v:.Ng}" do Python. */
export function fmtG(v, p = 6) {
  if (v === 0) return Object.is(v, -0) ? '-0' : '0';
  if (!Number.isFinite(v)) return Number.isNaN(v) ? 'nan' : (v > 0 ? 'inf' : '-inf');
  const [mant, e] = v.toExponential(p - 1).split('e');
  const exp = Number(e);
  const strip = (s) => (s.includes('.') ? s.replace(/0+$/, '').replace(/\.$/, '') : s);
  if (exp < -4 || exp >= p) return `${strip(mant)}e${exp < 0 ? '-' : '+'}${String(Math.abs(exp)).padStart(2, '0')}`;
  return strip(v.toFixed(Math.max(0, p - 1 - exp)));
}

/** Geoms do objeto no referencial do corpo (origem nos pés/base, z para cima). */
export function objectGeoms(cfg) {
  const o = cfg.object, h = o.height_m, r = o.radius_m;
  const skin = '0.95 0.75 0.35 1';
  if (o.type === 'sandbag') {
    const rr = Math.min(r, 0.49 * h);
    return [{ name: 'bag', kind: 'capsule', p0: [0, 0, rr], p1: [0, 0, h - rr], radius: rr, rgba: '0.75 0.65 0.45 1' }];
  }
  const rt = 0.75 * r, rl = 0.40 * r, ra = 0.30 * r, rh = 0.065 * h;
  const legX = 0.45 * r, armX = rt + ra;
  return [
    { name: 'torso', kind: 'capsule', p0: [0, 0, 0.52 * h + rt * 0.3], p1: [0, 0, 0.80 * h], radius: rt, rgba: '0.2 0.45 0.85 1' },
    { name: 'head', kind: 'sphere', p0: [0, 0, h - rh], p1: null, radius: rh, rgba: skin },
    { name: 'leg_l', kind: 'capsule', p0: [legX, 0, rl], p1: [legX, 0, 0.50 * h], radius: rl, rgba: '0.25 0.25 0.3 1' },
    { name: 'leg_r', kind: 'capsule', p0: [-legX, 0, rl], p1: [-legX, 0, 0.50 * h], radius: rl, rgba: '0.25 0.25 0.3 1' },
    { name: 'arm_l', kind: 'capsule', p0: [armX, 0, 0.78 * h], p1: [armX + 0.02, 0, 0.47 * h], radius: ra, rgba: skin },
    { name: 'arm_r', kind: 'capsule', p0: [-armX, 0, 0.78 * h], p1: [-armX - 0.02, 0, 0.47 * h], radius: ra, rgba: skin },
  ];
}

function geomVolume(g) {
  const sph = 4 / 3 * Math.PI * g.radius ** 3;
  if (g.kind === 'sphere') return sph;
  const ln = Math.hypot(g.p1[0] - g.p0[0], g.p1[1] - g.p0[1], g.p1[2] - g.p0[2]);
  return Math.PI * g.radius * g.radius * ln + sph;
}

/** Maior afastamento horizontal das geoms em relação ao eixo do corpo. */
export function objectExtentRadius(cfg) {
  let ext = 0;
  for (const g of objectGeoms(cfg)) {
    for (const p of [g.p0, g.p1]) if (p) ext = Math.max(ext, Math.hypot(p[0], p[1]) + g.radius);
  }
  return ext;
}

const pairFriction = (surface, object) => Math.min(surface, object);

export function buildXml(cfg, objPos, objQuat = [1, 0, 0, 0], withTower = true) {
  const t = cfg.tower, gr = cfg.ground, ct = cfg.contact, sv = cfg.solver;
  const R = t.diameter_m / 2, H = t.height_m;
  const geoms = objectGeoms(cfg);
  // soma na mesma ordem do Python (sum começa em 0)
  let vol = 0;
  for (const g of geoms) vol += geomVolume(g);
  const dens = cfg.object.mass_kg / vol;
  const aH = cfg.object.attach_height_fraction * cfg.object.height_m;
  const solref = ct.solref.map((v) => fmtG(v)).join(' ');
  const solimp = ct.solimp.map((v) => fmtG(v)).join(' ');
  const half = gr.size_m / 2;
  const muG = pairFriction(gr.friction_slide, cfg.object.geom_friction);
  const muW = pairFriction(t.wall_friction, cfg.object.geom_friction);
  const gxml = geoms.map((g) => {
    if (g.kind === 'sphere') {
      return `<geom name="obj_${g.name}" type="sphere" pos="${fmtG(g.p0[0])} ${fmtG(g.p0[1])} ${fmtG(g.p0[2])}" `
        + `size="${fmtG(g.radius)}" density="${fmtG(dens, 6)}" rgba="${g.rgba}"/>`;
    }
    const ft = [...g.p0, ...g.p1].map((v) => fmtG(v, 6)).join(' ');
    return `<geom name="obj_${g.name}" type="capsule" fromto="${ft}" size="${fmtG(g.radius)}" `
      + `density="${fmtG(dens, 6)}" rgba="${g.rgba}"/>`;
  });
  const pairs = [];
  for (const g of geoms) {
    pairs.push(`<pair geom1="obj_${g.name}" geom2="ground" condim="6" `
      + `friction="${fmtG(muG)} ${fmtG(muG)} ${fmtG(gr.friction_torsional)} ${fmtG(gr.friction_rolling)} ${fmtG(gr.friction_rolling)}" `
      + `solref="${solref}" solimp="${solimp}"/>`);
    if (withTower) {
      pairs.push(`<pair geom1="obj_${g.name}" geom2="tower" condim="3" `
        + `friction="${fmtG(muW)} ${fmtG(muW)} 0.005 0.0001 0.0001" solref="${solref}" solimp="${solimp}"/>`);
    }
  }
  const towerXml = withTower ? `<geom name="tower" type="cylinder" pos="0 0 ${fmtG(H / 2)}" size="${fmtG(R)} ${fmtG(H / 2)}" `
    + `rgba="0.62 0.52 0.45 1" material="brick"/>` : '';
  const q = objQuat.map((v) => fmtG(v, 9)).join(' ');
  let xml = `<mujoco model="spinjump">
  <compiler angle="radian" inertiafromgeom="true" autolimits="true"/>
  <option timestep="${fmtG(sv.timestep_s)}" integrator="${sv.integrator}" iterations="${sv.iterations}"
          cone="${ct.cone}" impratio="${fmtG(ct.impratio)}" gravity="0 0 ${fmtG(-G)}" density="0" viscosity="0"/>
  <size memory="64M"/>
  <visual>
    <global offwidth="${cfg.ui.width}" offheight="${cfg.ui.height}" azimuth="-60" elevation="-15"/>
    <quality shadowsize="2048" offsamples="4"/>
    <headlight ambient="0.35 0.35 0.38" diffuse="0.55 0.55 0.55" specular="0.1 0.1 0.1"/>
    <map znear="0.01" zfar="5000"/>
  </visual>
  <asset>
    <texture name="sky" type="skybox" builtin="gradient" rgb1="0.55 0.7 0.9" rgb2="0.95 0.97 1" width="256" height="256"/>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.42 0.45 0.40" rgb2="0.38 0.41 0.36" width="512" height="512"/>
    <material name="ground" texture="grid" texrepeat="${fmtG(gr.size_m / 10)} ${fmtG(gr.size_m / 10)}" reflectance="0"/>
    <texture name="brick" type="cube" builtin="flat" rgb1="0.62 0.50 0.42" rgb2="0.5 0.4 0.33" mark="random" random="0.15" markrgb="0.45 0.36 0.3" width="128" height="128"/>
    <material name="brick" texture="brick" reflectance="0"/>
  </asset>
  <worldbody>
    <light name="sun" directional="true" pos="0 0 100" dir="-0.4 0.3 -1" diffuse="0.7 0.7 0.65" castshadow="true"/>
    <geom name="ground" type="plane" size="${fmtG(half)} ${fmtG(half)} 1" material="ground" contype="0" conaffinity="0"/>
    ${towerXml}
    <body name="object" pos="${fmtG(objPos[0], 9)} ${fmtG(objPos[1], 9)} ${fmtG(objPos[2], 9)}" quat="${q}">
      <freejoint name="object"/>
      ${gxml.join(' ')}
      <site name="attach" pos="0 0 ${fmtG(aH)}" size="0.03" rgba="1 0.9 0 1"/>
    </body>
  </worldbody>
  <default/>
  <contact>
    ${pairs.join(' ')}
  </contact>
</mujoco>`;
  // todas as geoms sem colisão automática; somente os pares acima
  xml = xml.replaceAll('<geom name="obj_', '<geom contype="0" conaffinity="0" name="obj_');
  xml = xml.replaceAll('<geom name="tower"', '<geom contype="0" conaffinity="0" name="tower"');
  return xml;
}
