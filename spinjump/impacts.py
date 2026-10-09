"""Detecção e agrupamento de impactos do objeto contra solo e torre.

Um evento é um intervalo contínuo de contato entre o objeto (qualquer de suas
geoms) e uma superfície; interrupções menores que ``impact.merge_gap_ms`` e
contatos simultâneos de várias geoms do mesmo objeto pertencem ao mesmo evento.
A força normal vem de ``mj_contactForce`` (referencial do contato; componente 0
= normal), somada sobre todos os contatos objeto–superfície do passo.

Picos de força dependem de ``contact.solref``, ``contact.solimp`` e do passo de
tempo; o limiar em g é ilustrativo e não é critério de lesão validado.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import mujoco
import numpy as np

from .config import G, SimConfig
from .i18n import t as tr

SURFACES = ("ground", "tower")


@dataclass
class _Active:
    surface: str
    t_start: float
    t_last: float
    geoms: set = field(default_factory=set)
    t: list = field(default_factory=list)
    fn: list = field(default_factory=list)
    vn: list = field(default_factory=list)      # velocidade normal do CM (aproximação +)
    vt: list = field(default_factory=list)      # velocidade tangencial do CM
    pos_peak: tuple = (0.0, 0.0, 0.0)
    fn_peak_step: float = 0.0
    v_in_n: float = 0.0
    v_in_t: float = 0.0
    speed_in: float = 0.0


def classify(value: float, threshold: float, warn_fraction: float) -> str:
    if value >= threshold:
        return "DANO"
    if value >= warn_fraction * threshold:
        return "ATENÇÃO"
    return "OK"


class ImpactTracker:
    def __init__(self, cfg: SimConfig, model: mujoco.MjModel, obj_gids: list[int], ground_gid: int,
                 tower_gid: int, mass: float, dt: float):
        self.cfg = cfg
        self.m = model
        self.obj = set(obj_gids)
        self.gid = {"ground": ground_gid, "tower": tower_gid}
        self.mass = mass
        self.dt = dt
        self.merge_gap = cfg.impact.merge_gap_ms / 1000.0
        self.win = max(1, int(round(cfg.impact.filter_window_ms / 1000.0 / dt)))
        self.active: dict[str, _Active | None] = {s: None for s in SURFACES}
        self.events: list[dict] = []
        self.current_fn = {s: 0.0 for s in SURFACES}
        self.current_fvec = {s: np.zeros(3) for s in SURFACES}
        self._f6 = np.zeros(6)
        imp = cfg.impact
        if imp.damage_threshold_N is not None:
            self.metric, self.threshold = "N", float(imp.damage_threshold_N)
        else:
            self.metric, self.threshold = "g", float(imp.damage_threshold_g)

    def _gname(self, gid: int) -> str:
        return mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_GEOM, gid) or str(gid)

    def step(self, d: mujoco.MjData, t: float, v_com: np.ndarray):
        fn = {s: 0.0 for s in SURFACES}
        fvec = {s: np.zeros(3) for s in SURFACES}
        geoms = {s: set() for s in SURFACES}
        best = {s: (0.0, None) for s in SURFACES}
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = c.geom1, c.geom2
            if g1 in self.obj:
                og, other = g1, g2
            elif g2 in self.obj:
                og, other = g2, g1
            else:
                continue
            if other == self.gid["ground"]:
                s = "ground"
            elif other == self.gid["tower"]:
                s = "tower"
            else:
                continue
            mujoco.mj_contactForce(self.m, d, i, self._f6)
            f_n = float(self._f6[0])
            if f_n <= 0.0 and c.dist > 0:
                continue
            frame = c.frame.reshape(3, 3)
            fw = frame.T @ self._f6[:3]
            # orientar a força para atuar sobre o objeto
            if og == g1:
                fw = -fw
            fn[s] += max(f_n, 0.0)
            fvec[s] += fw
            geoms[s].add(self._gname(og))
            if f_n >= best[s][0]:
                best[s] = (f_n, tuple(float(x) for x in c.pos))
        for s in SURFACES:
            self.current_fn[s] = fn[s]
            self.current_fvec[s] = fvec[s]
            act = self.active[s]
            in_contact = len(geoms[s]) > 0
            if in_contact:
                pos = best[s][1] or (0.0, 0.0, 0.0)
                n = self._normal(s, pos)
                v_n = -float(v_com @ n)          # aproximação positiva
                v_t = float(np.linalg.norm(v_com - (v_com @ n) * n))
                if act is None:
                    act = _Active(s, t, t)
                    act.v_in_n, act.v_in_t = v_n, v_t
                    act.speed_in = float(np.linalg.norm(v_com))
                    self.active[s] = act
                elif t - act.t_last > self.merge_gap + 1e-12:
                    self._close(s)
                    act = _Active(s, t, t)
                    act.v_in_n, act.v_in_t = v_n, v_t
                    act.speed_in = float(np.linalg.norm(v_com))
                    self.active[s] = act
                act.t_last = t
                act.geoms |= geoms[s]
                if fn[s] >= act.fn_peak_step:
                    act.fn_peak_step = fn[s]
                    act.pos_peak = pos
            if act is not None:
                if not in_contact and t - act.t_last > self.merge_gap:
                    self._close(s)
                    continue
                pos = act.pos_peak
                n = self._normal(s, pos)
                act.t.append(t)
                act.fn.append(fn[s])
                act.vn.append(-float(v_com @ n))
                act.vt.append(float(np.linalg.norm(v_com - (v_com @ n) * n)))

    @staticmethod
    def _normal(surface: str, pos) -> np.ndarray:
        if surface == "ground":
            return np.array([0.0, 0.0, 1.0])
        rho = math.hypot(pos[0], pos[1])
        if rho < 1e-9:
            return np.array([1.0, 0.0, 0.0])
        return np.array([pos[0] / rho, pos[1] / rho, 0.0])

    def _close(self, s: str):
        act = self.active[s]
        self.active[s] = None
        if act is None or not act.t:
            return
        t = np.asarray(act.t)
        fnr = np.asarray(act.fn)
        # recorta amostras após o último contato (dentro da janela de fusão)
        keep = t <= act.t_last + 1e-12
        t, fnr = t[keep], fnr[keep]
        vn = np.asarray(act.vn)[keep]
        if fnr.size == 0:
            return
        kern = np.ones(self.win) / self.win
        fnf = np.convolve(fnr, kern, mode="same") if fnr.size >= self.win else fnr.copy()
        i_pk = int(np.argmax(fnr))
        i_pkf = int(np.argmax(fnf))
        peak_raw = float(fnr[i_pk])
        peak_f = float(fnf[i_pkf])
        # fase de impacto: do início até a força cair abaixo de 10% do pico após o pico
        after = np.nonzero(fnr[i_pk:] <= 0.1 * peak_raw)[0]
        i_end = i_pk + int(after[0]) if after.size else fnr.size - 1
        imp_phase = float(fnr[: i_end + 1].sum() * self.dt)
        imp_event = float(fnr.sum() * self.dt)
        dv_n = float(vn[0] - vn[i_end]) if vn.size else 0.0
        decel_g = peak_f / (self.mass * G)
        value = decel_g if self.metric == "g" else peak_f
        cls = classify(value, self.threshold, self.cfg.impact.warn_fraction)
        self.events.append(dict(
            surface=s, t_start=round(act.t_start, 5), t_end=round(act.t_last, 5),
            duration_s=round(act.t_last - act.t_start + self.dt, 5),
            location_m=[round(x, 4) for x in act.pos_peak],
            geoms=sorted(act.geoms),
            force_normal_peak_raw_N=round(peak_raw, 2),
            force_normal_peak_filtered_N=round(peak_f, 2),
            impulse_normal_impact_Ns=round(imp_phase, 4),
            impulse_normal_event_Ns=round(imp_event, 4),
            impact_phase_s=round(float(t[i_end] - t[0]) + self.dt, 5),
            delta_v_normal_impact_ms=round(dv_n, 4),
            decel_peak_g=round(decel_g, 3),
            v_normal_in_ms=round(act.v_in_n, 4),
            v_tangential_in_ms=round(act.v_in_t, 4),
            speed_in_ms=round(act.speed_in, 4),
            classification=cls,
            criterion=tr("criterion", metric=tr(f"criterion.{self.metric}"), thr=self.threshold, unit=self.metric,
                        wf=self.cfg.impact.warn_fraction),
        ))

    def finish(self):
        for s in SURFACES:
            if self.active[s] is not None:
                self._close(s)
        self.events.sort(key=lambda e: e["t_start"])
        return self.events

    def in_contact(self, s: str) -> bool:
        return self.current_fn[s] > 0.0

    def live_events(self) -> list[dict]:
        """Eventos fechados + resumo provisório dos ativos (para a UI)."""
        out = list(self.events)
        for s in SURFACES:
            a = self.active[s]
            if a is not None and a.fn:
                pk = max(a.fn)
                dg = pk / (self.mass * G)
                val = dg if self.metric == "g" else pk
                out.append(dict(surface=s, t_start=round(a.t_start, 4), t_end=None,
                                force_normal_peak_raw_N=round(pk, 1), decel_peak_g=round(dg, 2),
                                classification=classify(val, self.threshold, self.cfg.impact.warn_fraction),
                                active=True))
        return out
