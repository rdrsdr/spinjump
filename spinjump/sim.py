"""Motor da simulação: passo físico fixo, telemetria e desfecho.

O passo físico (``step``) não depende da renderização nem do ritmo de
reprodução: quem chama decide quantos passos executar por intervalo de relógio.
A cada passo: ``mj_step1`` (cinemática/colisão) → forças da corda, arrasto,
lançamento → ``mj_step2`` (dinâmica/integração) → impactos e métricas.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import mujoco
import numpy as np

from .config import G, SimConfig, launch_impulse, resolve
from .impacts import ImpactTracker
from .model import Built, build, object_extent_radius, object_geoms
from .rope import RopeParams, WrapTether
from .surface_rope import SurfaceRope

from .wind import Wind
from .i18n import t as _t

TELEMETRY_FIELDS = [
    "t", "x", "y", "z", "vx", "vy", "vz", "speed", "omega", "lowest_z", "attach_z",
    "theta_turns", "rho", "wall_dist",
    "wound_turns", "stored_turns", "geodesic_turns", "wound_len", "stored_len", "free_len",
    "rest_len", "path_len", "elongation", "slack", "tension", "tension_anchor", "kink_deg",
    "Dx", "Dy", "Dz", "P1z", "ground_fn", "tower_fn", "wind_x", "wind_y",
    "ke", "pe", "rope_pe", "e_total", "w_drag", "w_rope_damp", "w_peel", "w_wind_in", "phase",
    "coil_drop", "w_coil_fric",
]
PHASES = {0: "launch", 1: "airborne", 2: "ground", 3: "rest"}   # códigos; rótulos via i18n
OUTCOMES = ("AT_REST_CLEAN", "HIT_STRUCTURE", "REWOUND", "TIMEOUT", "NUMERICAL_FAILURE")
def safety_notice() -> str:
    return _t("safety")


SAFETY_NOTICE = _t("safety")   # compatibilidade (idioma do processo na importação)


@dataclass
class Tracker:
    first_ground_t: float | None = None
    first_ground_speed: float | None = None
    first_ground_vn: float | None = None
    first_ground_vt: float | None = None
    first_ground_pos: list | None = None
    first_ground_theta: float | None = None
    first_ground_wound_turns: float | None = None
    first_ground_stored_turns: float | None = None
    first_tower_t: float | None = None
    first_tower_speed: float | None = None
    first_tower_vn: float | None = None
    t_max: float = 0.0
    t_max_time: float = 0.0
    t_max_air: float = 0.0
    t_max_ground: float = 0.0
    t_anchor_max: float = 0.0
    slack_time: float = 0.0
    slack_time_air: float = 0.0
    slack_time_ground: float = 0.0
    slack_episodes: int = 0
    slack_max: float = 0.0
    was_slack: bool = False
    wound_min_turns: float = 1e9
    rewind_max_turns: float = 0.0
    stored_min_turns: float = 1e9
    wall_dist_min: float = 1e9
    wall_dist_min_t: float = 0.0
    slide_path: float = 0.0
    ground_hops: int = 0
    max_lift_after_ground: float = 0.0
    ground_contact_prev: bool = False
    last_ground_lost_t: float | None = None
    rest_hold: float = 0.0
    rest_t: float | None = None
    strain_max_ground: float = 0.0
    reach_excess_max: float = -1e9
    above_top_time: float = 0.0
    coil_slip_risk_time: float = 0.0
    coil_slip_ratio_max: float = 0.0
    load_warn: bool = False
    load_break: bool = False
    energy0: float = 0.0
    w_drag: float = 0.0          # trabalho do arrasto sobre o objeto (ar relativo)
    w_wind_in: float = 0.0       # parcela desse trabalho devida ao vento (pode injetar energia)
    w_rope_dist: float = 0.0     # trabalho das cargas distribuídas da corda sobre o objeto
    w_rope_damp: float = 0.0     # energia dissipada no amortecimento axial
    w_peel: float = 0.0          # energia dissipada na dobra ao descascar a hélice
    w_coil_fric: float = 0.0     # energia dissipada por atrito corda–parede (espiras deslizantes)
    w_chain_out: float = 0.0     # energia que saiu da corda encostada por transferência de material
    coil_drop_max: float = 0.0   # maior deslocamento vertical de um trecho encostado (m)
    w_launch: float = 0.0        # trabalho da força de lançamento (modo com duração)
    e_flight_residual_max: float = 0.0


class Simulation:
    #: somente para ensaios contrafactuais (testes): corda solta após o 1º toque no solo
    release_rope_at_ground: bool = False

    def __init__(self, cfg: SimConfig, resolved: bool = False):
        if resolved:
            self.cfg, self.notes = cfg, {}
        else:
            self.cfg, self.notes = resolve(cfg)
        c = self.cfg
        self.dt = c.solver.timestep_s
        R = c.tower.diameter_m / 2
        self.R = R
        H = c.tower.height_m
        self.extent = object_extent_radius(c)
        a_h = c.object.attach_height_fraction * c.object.height_m
        self.rp = RopeParams(
            R_wall=R, rope_d=c.rope.diameter_m,
            pitch=c.rope.winding_pitch_factor * c.rope.diameter_m,
            handedness=1 if c.rope.winding_handedness == "ccw" else -1,
            z_anchor=H - c.rope.anchor_below_top_m, length=float(c.rope.length_m),
            EA=float(c.rope.axial_EA_N), zeta=c.rope.axial_damping_ratio,
            lin_density=c.rope.linear_density_kg_m, mu_wall=c.rope.wall_friction,
            cd_normal=c.rope.wind_drag_Cd_normal, cd_tangent=c.rope.wind_drag_Cd_tangent,
            element_length=c.rope.element_length_m, m_eff=c.object.mass_kg, tower_height=H,
            vertical=1 if c.rope.helix_vertical == "up" else -1)
        if c.rope.coil_sliding:
            self.rope = SurfaceRope(self.rp, self.dt, c.rope.winding_pretension_N, c.rope.coil_window_turns,
                                    c.rope.coil_iterations, c.rope.coil_update_every_steps,
                                    c.rope.coil_mass_scale)
        else:
            self.rope = WrapTether(self.rp)
        rho_A = R + c.object.start_clearance_m + self.extent
        self.layout = self.rope.initial_layout(rho_A, 0.0)
        A0 = self.layout["A0"]
        room = c.rope.anchor_below_top_m if c.rope.helix_vertical == "up" else self.rp.z_anchor
        if self.layout["helix_height"] + 1e-9 > room:
            raise ValueError(_t("err.helix_too_tall", turns=self.layout["turns0"], height=self.layout["helix_height"]))
        self.warnings: list[str] = []
        # alcance do solo com a corda totalmente desenrolada (geometria real)
        L_min = math.hypot(self.rp.z_anchor - c.object.radius_m, max(R + c.object.radius_m - self.rp.rc, 0.0))
        if self.rp.length < L_min:
            self.warnings.append(_t("warn.short_rope", L=self.rp.length, Lmin=L_min))
        # estabilidade da lei elástica explícita: ω·dt com o menor vão (inicial)
        omega = math.sqrt(self.rp.EA / (max(self.layout["free0"], 0.05) * c.object.mass_kg))
        if omega * self.dt > 0.2:
            self.warnings.append(_t("warn.stiff", w=omega * self.dt))
        if c.launch.elevation_deg > 60:
            self.warnings.append(_t("warn.elevation"))
        body_pos = A0 - np.array([0.0, 0.0, a_h])
        self.b: Built = build(c, body_pos)
        self.m, self.d = self.b.model, self.b.data
        self.m.opt.enableflags |= mujoco.mjtEnableBit.mjENBL_ENERGY
        self.mass = self.b.mass
        self.wind = Wind(c, self.dt)
        self.impacts = ImpactTracker(c, self.m, self.b.obj_gids, self.b.ground_gid, self.b.tower_gid,
                                     self.mass, self.dt)
        self.air_rho = c.air.density_kg_m3 if c.air.enabled else 0.0
        self._cda = c.object.drag_CdA_m2
        self._edge = max(self.extent, c.object.height_m / 2)
        # lançamento: direção no referencial do vão livre inicial
        D0 = self.layout["D0"]
        u_t = (A0 - D0)
        u_t[2] = 0.0
        u_t /= np.linalg.norm(u_t)
        n_D = np.array([D0[0], D0[1], 0.0])
        n_D /= np.linalg.norm(n_D)
        az = math.radians(c.launch.azimuth_deg)
        el = math.radians(c.launch.elevation_deg)
        v_h = math.cos(az) * u_t + math.sin(az) * n_D
        self.launch_dir = math.cos(el) * v_h + math.sin(el) * np.array([0.0, 0.0, 1.0])
        self.launch_J = launch_impulse(c)
        self.launch_T = c.launch.duration_ms / 1000.0
        self.launch_frame = dict(u_free=u_t.tolist(), n_unwind=n_D.tolist(),
                                 direction=self.launch_dir.tolist())
        if self.launch_T <= 0.0 and self.launch_J > 0.0:
            self.d.qvel[0:3] += self.launch_J / self.mass * self.launch_dir
        mujoco.mj_forward(self.m, self.d)
        self.rope.reset(self.d.site_xpos[self.b.site_id])
        self.theta0 = self.rope.s.theta_u
        self.step_count = 0
        self.sample_every = max(1, int(round(1.0 / (c.solver.output_hz * self.dt))))
        self.samples: list[tuple] = []
        self.tr = Tracker()
        self.status = "running"
        self.outcome: str | None = None
        self.failure: str | None = None
        self._vel6 = np.zeros(6)
        self._sv6 = np.zeros(6)
        self._phase = 0
        self.wall_clock = 0.0
        self.geom_local = [(np.array(gs.p0, float), np.array(gs.p1 if gs.p1 is not None else gs.p0, float),
                            gs.radius) for gs in object_geoms(c)]
        self._update_rope_only()
        self.tr.energy0 = self._energy()
        self._sample()

    # --------------------------------------------------------------- auxiliares
    def _body_velocity(self):
        mujoco.mj_objectVelocity(self.m, self.d, mujoco.mjtObj.mjOBJ_BODY, self.b.body_id, self._vel6, 0)
        return self._vel6[3:].copy(), self._vel6[:3].copy()

    def _site_velocity(self):
        mujoco.mj_objectVelocity(self.m, self.d, mujoco.mjtObj.mjOBJ_SITE, self.b.site_id, self._sv6, 0)
        return self._sv6[3:].copy()

    def _update_rope_only(self):
        A = self.d.site_xpos[self.b.site_id].copy()
        self.rope.update(A, self._site_velocity(), self.wind.at_many, self.air_rho, G)

    def _energy(self) -> float:
        rs = self.rope.s
        return float(self.d.energy[0] + self.d.energy[1] + rs.elastic_energy + rs.chain_energy)

    def _world_segments(self):
        bid = self.b.body_id
        xp = self.d.xpos[bid]
        xm = self.d.xmat[bid].reshape(3, 3)
        for p0l, p1l, r in self.geom_local:
            yield xp + xm @ p0l, xp + xm @ p1l, r

    def wall_distance(self) -> float:
        """Menor distância horizontal entre a superfície do objeto e a parede (segmentos)."""
        best = 1e9
        for p0, p1, r in self._world_segments():
            a, b = p0[:2], p1[:2] - p0[:2]
            bb = float(b @ b)
            t = 0.0 if bb < 1e-12 else min(1.0, max(0.0, -float(a @ b) / bb))
            q = a + t * b
            best = min(best, math.hypot(q[0], q[1]) - self.R - r)
        return best

    def lowest_point(self) -> float:
        low = 1e9
        for p0, p1, r in self._world_segments():
            low = min(low, p0[2] - r, p1[2] - r)
        return float(low)

    def object_turns(self) -> float:
        """Voltas do objeto em torno do eixo da torre desde o início (+ = sentido de desenrolar)."""
        return -self.rp.handedness * (self.rope.s.theta_u - self.theta0) / (2 * math.pi)

    # ------------------------------------------------------------------ passo
    def step(self) -> bool:
        """Executa um passo físico. Devolve False quando a simulação terminou."""
        if self.status != "running":
            return False
        m, d, c, dt = self.m, self.d, self.cfg, self.dt
        t_pre = d.time
        mujoco.mj_step1(m, d)
        bid = self.b.body_id
        com = d.xipos[bid].copy()
        v_com, w_com = self._body_velocity()
        A = d.site_xpos[self.b.site_id].copy()
        vA = self._site_velocity()
        rs = self.rope.update(A, vA, self.wind.at_many if self.air_rho > 0 else None, self.air_rho, G)
        Fr = rs.force_on_obj
        if self.release_rope_at_ground and self.tr.first_ground_t is not None:
            Fr = np.zeros(3)
            rs.p_damp = rs.p_peel = 0.0
            rs.dist_load_on_obj = Fr
        F = Fr.copy()
        rx, ry, rz = A[0] - com[0], A[1] - com[1], A[2] - com[2]
        torque = (ry * Fr[2] - rz * Fr[1], rz * Fr[0] - rx * Fr[2], rx * Fr[1] - ry * Fr[0])
        tr = self.tr
        dl = rs.dist_load_on_obj
        tr.w_rope_dist += (dl[0] * vA[0] + dl[1] * vA[1] + dl[2] * vA[2]) * dt
        tr.w_rope_damp += rs.p_damp * dt
        tr.w_peel += rs.p_peel * dt
        tr.w_coil_fric += rs.e_fric
        tr.w_chain_out += rs.e_massflux
        if self.air_rho > 0.0 and self._cda > 0.0:
            w = self.wind.at(com[2])
            vrx, vry, vrz = v_com[0] - w[0], v_com[1] - w[1], v_com[2] - w[2]
            q = -0.5 * self.air_rho * self._cda * math.sqrt(vrx * vrx + vry * vry + vrz * vrz)
            fdx, fdy, fdz = q * vrx, q * vry, q * vrz
            F[0] += fdx
            F[1] += fdy
            F[2] += fdz
            tr.w_drag += (fdx * v_com[0] + fdy * v_com[1] + fdz * v_com[2]) * dt
            tr.w_wind_in += (fdx * w[0] + fdy * w[1]) * dt
        if self.launch_T > 0.0 and t_pre < self.launch_T - 1e-12:
            fl = self.launch_J / self.launch_T * self.launch_dir
            F += fl
            tr.w_launch += float(fl @ v_com) * dt
        d.xfrc_applied[bid, :3] = F
        d.xfrc_applied[bid, 3:] = torque
        self.wind.advance()
        mujoco.mj_step2(m, d)
        self.step_count += 1
        qv = d.qvel
        if (d.warning[mujoco.mjtWarning.mjWARN_BADQACC].number > 0
                or not (qv[0] * qv[0] + qv[1] * qv[1] + qv[2] * qv[2] < 250000.0)
                or not math.isfinite(d.qpos[0] + d.qpos[1] + d.qpos[2])):
            self.status = "finished"
            self.outcome = "NUMERICAL_FAILURE"
            self.failure = _t("fail.numerical", t=t_pre)
            return False
        self.impacts.step(d, t_pre, v_com)
        self._track(t_pre, com, v_com, w_com, rs)
        if self.step_count % self.sample_every == 0:
            self._sample()
        return self.status == "running"

    def _track(self, t, com, v, w, rs):
        tr, c, dt = self.tr, self.cfg, self.dt
        g_on = self.impacts.in_contact("ground")
        t_on = self.impacts.in_contact("tower")
        if rs.tension > tr.t_max:
            tr.t_max, tr.t_max_time = rs.tension, t
        if tr.first_ground_t is None:
            tr.t_max_air = max(tr.t_max_air, rs.tension)
        else:
            tr.t_max_ground = max(tr.t_max_ground, rs.tension)
        tr.t_anchor_max = max(tr.t_anchor_max, rs.tension_anchor)
        if rs.tension >= c.rope.breaking_load_N:
            tr.load_break = True
        if rs.tension >= c.rope.load_warn_fraction * c.rope.breaking_load_N:
            tr.load_warn = True
        if rs.slack:
            tr.slack_time += dt
            tr.slack_max = max(tr.slack_max, -rs.delta)
            if not tr.was_slack:
                tr.slack_episodes += 1
            if tr.first_ground_t is None:
                tr.slack_time_air += dt
            else:
                tr.slack_time_ground += dt
        tr.was_slack = rs.slack
        wt = self.rope.wound_turns
        tr.wound_min_turns = min(tr.wound_min_turns, wt)
        tr.rewind_max_turns = max(tr.rewind_max_turns, wt - tr.wound_min_turns)
        tr.stored_min_turns = min(tr.stored_min_turns, rs.u_s / (2 * math.pi))
        if rs.above_top:
            tr.above_top_time += dt
        # risco de escorregamento das espiras: componente vertical da tração em P1 vs.
        # capacidade de atrito da hélice armazenada T·(1 - exp(-μ u_s))
        if rs.coil_drop > tr.coil_drop_max:
            tr.coil_drop_max = rs.coil_drop
        if self.rope.model_name == "locked" and rs.tension > 0.0 and rs.u_s > 0.0 and abs(rs.psi_g) < 1e-9:
            cap = 1.0 - math.exp(-self.rp.mu_wall * rs.u_s)
            ratio = abs(rs.e[2]) / max(cap, 1e-9)
            tr.coil_slip_ratio_max = max(tr.coil_slip_ratio_max, ratio)
            if ratio > 1.0:
                tr.coil_slip_risk_time += dt
        speed = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        if g_on and tr.first_ground_t is None:
            tr.first_ground_t = t
            tr.first_ground_speed = speed
            tr.first_ground_vn = float(-v[2])
            tr.first_ground_vt = float(math.hypot(v[0], v[1]))
            tr.first_ground_pos = [float(x) for x in com]
            tr.first_ground_theta = self.object_turns()
            tr.first_ground_wound_turns = wt
            tr.first_ground_stored_turns = rs.u_s / (2 * math.pi)
        if tr.first_ground_t is None and tr.first_tower_t is None:
            # resíduo do balanço de energia em voo livre de contato
            e_obj = float(self.d.energy[0] + self.d.energy[1])
            pred = (tr.energy0 + tr.w_drag + tr.w_rope_dist + tr.w_launch - tr.w_rope_damp - tr.w_peel
                    - tr.w_coil_fric - tr.w_chain_out - rs.elastic_energy - rs.chain_energy)
            tr.e_flight_residual_max = max(tr.e_flight_residual_max, abs(e_obj - pred))
        if t_on and tr.first_tower_t is None:
            tr.first_tower_t = t
            tr.first_tower_speed = speed
            rho = math.hypot(com[0], com[1])
            tr.first_tower_vn = float(-(v[0] * com[0] + v[1] * com[1]) / max(rho, 1e-9))
            if c.solver.stop_on_structure_hit and tr.first_tower_vn >= c.impact.structure_hit_speed_ms:
                self.status = "finished"
                self.outcome = "HIT_STRUCTURE"
        if tr.first_ground_t is not None:
            tr.slide_path += math.hypot(v[0], v[1]) * dt
            if not g_on and tr.ground_contact_prev:
                tr.last_ground_lost_t = t
            if g_on and not tr.ground_contact_prev and tr.last_ground_lost_t is not None:
                if t - tr.last_ground_lost_t > c.impact.merge_gap_ms / 1000.0:
                    tr.ground_hops += 1
            if not g_on:
                tr.max_lift_after_ground = max(tr.max_lift_after_ground, self.lowest_point())
            if g_on and rs.tension > 0:
                tr.strain_max_ground = max(tr.strain_max_ground, rs.delta / rs.l_rest)
                # alcance: caminho P1→A não pode exceder L_rep·(1 + T/EA) (lei elástica)
                allowed = rs.l_rest * (1.0 + rs.tension / self.rp.EA)
                tr.reach_excess_max = max(tr.reach_excess_max, rs.l_geom - allowed)
        tr.ground_contact_prev = g_on
        omega_edge = math.sqrt(w[0] * w[0] + w[1] * w[1] + w[2] * w[2]) * self._edge
        if g_on:
            self._phase = 2
            if speed < c.solver.rest_speed_ms and omega_edge < c.solver.rest_speed_ms:
                tr.rest_hold += dt
            else:
                tr.rest_hold = 0.0
            if tr.rest_hold >= c.solver.rest_hold_s and self.status == "running":
                self._phase = 3
                tr.rest_t = t
                self.status = "finished"
        else:
            tr.rest_hold = 0.0
            self._phase = 1 if t > 0 else 0
        if self.status == "running" and self.d.time >= c.solver.max_time_s - 1e-12:
            self.status = "finished"          # desfecho decidido em _classify (precedência)

    def _sample(self):
        d, rs, tr = self.d, self.rope.s, self.tr
        bid = self.b.body_id
        com = d.xipos[bid]
        v, wv = self._body_velocity()
        wd = self.wall_distance()
        if wd < tr.wall_dist_min:
            tr.wall_dist_min, tr.wall_dist_min_t = wd, d.time
        w = self.wind.at(com[2])
        ke, pe = float(d.energy[1]), float(d.energy[0])
        two_pi = 2 * math.pi
        row = (d.time, com[0], com[1], com[2], v[0], v[1], v[2], float(np.linalg.norm(v)),
               float(np.linalg.norm(wv)), self.lowest_point(), rs.A[2],
               self.object_turns(), math.hypot(com[0], com[1]), wd,
               self.rope.wound_turns, rs.u_s / two_pi, abs(rs.psi_g) / two_pi, rs.wound_len, rs.stored_len,
               rs.l_free, rs.l_rest, rs.l_geom, max(rs.delta, 0.0), max(-rs.delta, 0.0),
               rs.tension, rs.tension_anchor, rs.kink_deg, rs.D[0], rs.D[1], rs.D[2], rs.P1[2],
               self.impacts.current_fn["ground"], self.impacts.current_fn["tower"], w[0], w[1],
               ke, pe, rs.elastic_energy,
               ke + pe + rs.elastic_energy + rs.chain_energy + tr.w_chain_out,   # total contábil
               tr.w_drag, tr.w_rope_damp, tr.w_peel,
               tr.w_wind_in, self._phase, rs.coil_drop, tr.w_coil_fric)
        self.samples.append(row)

    # ------------------------------------------------------------------- API
    def run(self, max_wall_s: float | None = None) -> "Simulation":
        t0 = time.perf_counter()
        while self.step():
            if max_wall_s is not None and time.perf_counter() - t0 > max_wall_s:
                break
        self.wall_clock += time.perf_counter() - t0
        self.finish()
        return self

    def stop(self, reason: str | None = None):
        reason = reason or _t("stopped_by_user")
        if self.status == "running":
            self.status = "finished"
            self.failure = reason

    def finish(self):
        if self.status == "running":
            self.status = "finished"
        if self.samples and self.samples[-1][0] < self.d.time - 1e-9:
            self._sample()
        self.impacts.finish()
        if self.outcome is None:
            self.outcome = self._classify()

    def _classify(self) -> str:
        """Precedência: NUMERICAL_FAILURE > HIT_STRUCTURE > REWOUND > TIMEOUT > AT_REST_CLEAN."""
        if self.structure_hits():
            return "HIT_STRUCTURE"
        if self.tr.rewind_max_turns >= self.cfg.solver.rewind_threshold_turns:
            return "REWOUND"
        if self._phase == 3:
            return "AT_REST_CLEAN"
        return "TIMEOUT"

    def structure_hits(self) -> list[dict]:
        thr = self.cfg.impact.structure_hit_speed_ms
        return [e for e in self.impacts.events if e["surface"] == "tower" and e["v_normal_in_ms"] >= thr]

    def snapshot(self) -> dict:
        """Estado instantâneo para a UI (telemetria ao vivo)."""
        d, rs, tr = self.d, self.rope.s, self.tr
        com = d.xipos[self.b.body_id]
        v, _ = self._body_velocity()
        return dict(
            t=round(d.time, 4), speed=round(float(np.linalg.norm(v)), 3), height=round(float(com[2]), 3),
            wall_dist=round(self.wall_distance(), 3), object_turns=round(self.object_turns(), 3),
            wound_turns=round(self.rope.wound_turns, 3), stored_turns=round(rs.u_s / (2 * math.pi), 3),
            wound_len=round(rs.wound_len, 3), free_len=round(rs.l_free, 3),
            rest_len=round(rs.l_rest, 3), elongation=round(max(rs.delta, 0.0), 4),
            slack=round(max(-rs.delta, 0.0), 4), slack_flag=bool(rs.slack),
            tension=round(rs.tension, 1), tension_anchor=round(rs.tension_anchor, 1),
            coil_drop=round(rs.coil_drop, 4), coil_model=self.rope.model_name,
            tension_max=round(tr.t_max, 1), phase=_t(f"phase.{self._phase}"), phase_code=PHASES[self._phase],
            ground_fn=round(self.impacts.current_fn["ground"], 1),
            tower_fn=round(self.impacts.current_fn["tower"], 1),
            events=self.impacts.live_events()[-6:], status=self.status, outcome=self.outcome,
            load_warn=tr.load_warn, failure=self.failure)
