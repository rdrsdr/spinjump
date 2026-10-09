"""Modelo de corda ``wrap_tether``: enrolamento explícito sobre cilindro vertical.

Componentes, da âncora para o objeto (ver README, seção "Modelo da corda"):

1. **Hélice armazenada** (âncora → P1): raio ``rc = D/2 + d/2``, passo
   ``p = winding_pitch_factor·d``, ângulo enrolado ``u_s`` a partir da âncora.
   É travada por atrito na parede (não escorrega, não se alonga) e só diminui:
   quando o trecho tenso precisa sair "atrás" de P1, a corda **descasca** da
   hélice e P1 recua. Nesse instante há uma dobra em P1 entre a espira
   horizontal e o vão inclinado; a perda associada (dobra que percorre o
   material sob tração, ``T·(κ - e·dP1/du)·|u̇|``) é contabilizada como
   dissipação de atrito no ponto de saída.
2. **Trecho geodésico** (P1 → D): quando o objeto gira no sentido de enrolar,
   a corda se apoia no cilindro ao longo de uma geodésica (hélice cujo passo é
   definido pela própria geometria, como a corda de um "tetherball"). Sem
   atrito ao longo do trecho geodésico (corda tensa em equilíbrio).
3. **Vão livre** (D → A): reto, tangente ao cilindro em D; na planificação do
   cilindro, geodésica + vão formam uma única reta, logo o comprimento total é
   ``ℓ = sqrt((rc·|ψ_g| + ℓ_h)² + Δz²)`` e a força em A é ``-T·e`` (gradiente
   do caminho mínimo: conservativa).

O trecho P1→A é um único elemento elástico unilateral de comprimento de
repouso ``L - u_s·κ``: ``T = max(0, k·δ + c·δ̇)`` se δ > 0, senão ``T = 0``
(folga), com ``k = EA/L_rep`` e ``c = 2ζ·sqrt(k·m)``.

Peso e arrasto distribuídos são integrados no vão livre por quadratura
(segmentos de ``element_length_m``) e transmitidos ao objeto pela regra da
alavanca (flecha desprezada). Tração na âncora: cabrestante com atrito
mobilizado na hélice armazenada, ``T·exp(-μ·u_s)``.

A mesma instância calcula forças e a geometria desenhada.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .i18n import t as tr

TWO_PI = 2.0 * math.pi


@dataclass
class RopeParams:
    R_wall: float          # raio da parede (m)
    rope_d: float          # diâmetro da corda (m)
    pitch: float           # passo da hélice armazenada (m/volta)
    handedness: int        # +1 ccw, -1 cw (sentido da hélice armazenada a partir da âncora)
    z_anchor: float        # altura da âncora (m)
    length: float          # comprimento total de repouso L (m)
    EA: float              # rigidez axial (N)
    zeta: float            # razão de amortecimento axial
    lin_density: float     # kg/m
    mu_wall: float         # atrito corda-parede (cabrestante na hélice armazenada)
    cd_normal: float
    cd_tangent: float
    element_length: float  # m (quadratura)
    m_eff: float           # massa do objeto (para amortecimento crítico)
    tower_height: float
    vertical: int = 1      # +1: hélice sobe a partir da âncora (sai pela espira de cima);
                           # -1: desce a partir da âncora (sai pela de baixo, desenrola de baixo p/ cima)

    @property
    def rc(self) -> float:
        return self.R_wall + 0.5 * self.rope_d

    @property
    def kappa(self) -> float:
        """Comprimento de hélice armazenada por radiano."""
        return math.hypot(self.rc, self.pitch / TWO_PI)


@dataclass
class RopeState:
    u_s: float = 0.0           # ângulo da hélice armazenada (rad, >= 0)
    psi: float = 0.0           # ângulo total com sinal do ponto de saída D em relação à âncora
    psi_g: float = 0.0         # ângulo com sinal do trecho geodésico (P1 → D)
    psi_dot: float = 0.0
    theta_u: float = 0.0       # ângulo desenrolado contínuo de A em torno do eixo
    theta_raw: float = 0.0
    regime: int = 1            # +1 / -1 sentido de saída; 0 reto desde a âncora
    peeling: bool = False      # descascando a hélice armazenada neste passo
    P1: np.ndarray = field(default_factory=lambda: np.zeros(3))
    D: np.ndarray = field(default_factory=lambda: np.zeros(3))
    A: np.ndarray = field(default_factory=lambda: np.zeros(3))
    e: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0]))
    l_free: float = 0.0        # comprimento geométrico do vão livre D→A
    l_geo: float = 0.0         # comprimento geométrico do trecho geodésico P1→D
    l_geom: float = 0.0        # P1→A (geodésico + vão)
    l_rest: float = 0.0        # comprimento de repouso de P1→A
    stored_len: float = 0.0    # comprimento da hélice armazenada
    wound_len: float = 0.0     # armazenada + geodésica (em contato com a torre)
    delta: float = 0.0         # alongamento (+) / folga (-)
    delta_dot: float = 0.0
    tension: float = 0.0
    tension_anchor: float = 0.0
    force_on_obj: np.ndarray = field(default_factory=lambda: np.zeros(3))
    dist_load_on_obj: np.ndarray = field(default_factory=lambda: np.zeros(3))
    slack: bool = False
    above_top: bool = False
    fully_wound: bool = False
    elastic_energy: float = 0.0
    p_damp: float = 0.0        # potência dissipada no amortecimento axial (W)
    p_peel: float = 0.0        # potência dissipada na dobra ao descascar (W)
    kink_deg: float = 0.0      # ângulo entre a espira e o trecho que sai de P1
    k: float = 0.0
    c: float = 0.0
    # modelo de espiras deslizantes (zero no modelo travado)
    chain_energy: float = 0.0  # cinética + potencial + elástica da corda encostada (J)
    e_fric: float = 0.0        # energia dissipada por atrito corda–parede neste passo (J)
    e_massflux: float = 0.0    # energia que saiu da contabilidade da cadeia neste passo (J)
    coil_drop: float = 0.0     # maior deslocamento vertical de um trecho encostado (m)


class WrapTether:
    model_name = "locked"

    def __init__(self, p: RopeParams, phi_anchor: float = 0.0):
        self.p = p
        self.phi_a = phi_anchor
        self.s = RopeState()
        self._initialized = False
        self._qcache: dict[int, tuple] = {}
        # constantes por desempenho (o laço físico chama update a cada passo)
        self._kappa = p.kappa
        self._rc = p.rc
        self._pz = p.vertical * p.pitch / TWO_PI

    # ------------------------------------------------------------ geometria
    def stored_point(self, u: float) -> np.ndarray:
        p = self.p
        phi = self.phi_a + p.handedness * u
        return np.array([p.rc * math.cos(phi), p.rc * math.sin(phi),
                         p.z_anchor + p.vertical * p.pitch * u / TWO_PI])

    def stored_tangent(self, u: float) -> np.ndarray:
        """dP1/du (m/rad)."""
        p = self.p
        h = p.handedness
        phi = self.phi_a + h * u
        return np.array([-h * p.rc * math.sin(phi), h * p.rc * math.cos(phi), p.vertical * p.pitch / TWO_PI])

    def initial_layout(self, rho_A: float, theta_A: float) -> dict:
        """Hélice inicial com vão livre horizontal tangente até A (raio ``rho_A``)."""
        p = self.p
        rc = p.rc
        if rho_A <= rc:
            raise ValueError(tr("err.attach_inside"))
        l_h = math.sqrt(rho_A ** 2 - rc ** 2)
        wound = p.length - l_h
        if wound <= 0:
            raise ValueError(tr("err.rope_too_short_start", L=p.length, lh=l_h))
        u0 = wound / p.kappa
        beta = math.acos(rc / rho_A)
        # D0 = P1 no ângulo φ_a + s·u0; A sai tangente: θ_A = φ_D + s·β
        self.phi_a = theta_A - p.handedness * beta - p.handedness * u0
        self.s.u_s = u0
        D = self.stored_point(u0)
        A = np.array([rho_A * math.cos(theta_A), rho_A * math.sin(theta_A), D[2]])
        return dict(u0=u0, wound0=wound, turns0=u0 / TWO_PI, free0=l_h, D0=D, A0=A,
                    phi_anchor=self.phi_a, helix_height=u0 / TWO_PI * p.pitch)

    def _quad(self, n: int):
        """Pontos médios s_i = (i+½)/n da quadratura (cache por n)."""
        q = self._qcache.get(n)
        if q is None:
            sq = (np.arange(n) + 0.5) / n
            q = (sq, float(sq.sum()))
            self._qcache[n] = q
        return q

    def reset(self, A: np.ndarray):
        th = math.atan2(A[1], A[0])
        self.s.theta_raw = th
        # ramo contínuo coerente com a hélice inicial: θ_u ≈ φ_a + s·u_s + s·β
        rho = math.hypot(A[0], A[1])
        beta = math.acos(min(1.0, self.p.rc / max(rho, 1e-9)))
        target = self.phi_a + self.p.handedness * (self.s.u_s + beta)
        k = round((target - th) / TWO_PI)
        self.s.theta_u = th + k * TWO_PI
        self._initialized = True

    def _track_theta(self, A: np.ndarray) -> float:
        th = math.atan2(A[1], A[0])
        d = th - self.s.theta_raw
        d = (d + math.pi) % TWO_PI - math.pi
        self.s.theta_raw = th
        self.s.theta_u += d
        return self.s.theta_u

    # --------------------------------------------------------------- dinâmica
    def update(self, A: np.ndarray, vA: np.ndarray, wind_fn=None, air_density: float = 0.0,
               g: float = 9.81) -> RopeState:
        p, s = self.p, self.s
        h = p.handedness
        rc = self._rc
        kappa = self._kappa
        if not self._initialized:
            self.reset(A)
        theta_u = self._track_theta(A)
        rho = math.hypot(A[0], A[1])
        rho_c = max(rho, rc * (1 + 1e-9))
        beta = math.acos(rc / rho_c)
        l_h = math.sqrt(max(rho_c * rho_c - rc * rc, 0.0))
        # derivadas horizontais
        if rho > 1e-9:
            theta_dot = (A[0] * vA[1] - A[1] * vA[0]) / rho ** 2
            rho_dot = (A[0] * vA[0] + A[1] * vA[1]) / rho
        else:
            theta_dot = rho_dot = 0.0
        beta_dot = rc * rho_dot / (rho_c * l_h) if l_h > 1e-9 else 0.0
        # ângulo de saída com sinal relativo à âncora, para cada sentido
        psi_pos = theta_u - beta - self.phi_a      # saída no sentido +
        psi_neg = theta_u + beta - self.phi_a      # saída no sentido -
        # sentido "à frente" da hélice armazenada: h
        psi_h = psi_pos if h == 1 else psi_neg     # ψ se a saída continua no sentido h
        u_prev = s.u_s
        peeling = False
        if u_prev > 0.0:
            a = h * psi_h                           # avanço de D além da âncora no sentido h
            if a < u_prev:
                # D ficaria atrás de P1: descasca a hélice armazenada
                u_s = max(0.0, a)
                peeling = True
            else:
                u_s = u_prev
        else:
            u_s = 0.0
        if u_s > 0.0:
            regime = h
            psi = psi_h
        else:
            # sem hélice armazenada: corda parte da âncora em qualquer sentido
            if psi_pos > 0.0:
                regime, psi = 1, psi_pos
            elif psi_neg < 0.0:
                regime, psi = -1, psi_neg
            else:
                regime, psi = 0, 0.0
            if u_prev > 0.0 and h * psi < 0:
                pass
        psi_g = psi - h * u_s if u_s > 0.0 else psi
        # derivada de ψ
        if regime == 1:
            psi_dot = theta_dot - beta_dot
        elif regime == -1:
            psi_dot = theta_dot + beta_dot
        else:
            psi_dot = 0.0
        u_s_dot = h * psi_dot if peeling and u_s > 0.0 else 0.0
        # ponto P1 (fim da hélice armazenada) e sua tangente dP1/du — escalares por desempenho
        phi1 = self.phi_a + h * u_s
        c1, s1 = math.cos(phi1), math.sin(phi1)
        pz = self._pz
        P1x, P1y, P1z = rc * c1, rc * s1, p.z_anchor + pz * u_s
        tx, ty, tz = -h * rc * s1, h * rc * c1, pz
        # geometria planificada: P1 → (geodésica |ψ_g|) → D → (vão ℓ_h) → A
        ag = abs(psi_g)
        run_g = rc * ag
        X = run_g + l_h
        Ax, Ay, Az = float(A[0]), float(A[1]), float(A[2])
        vx, vy, vz = float(vA[0]), float(vA[1]), float(vA[2])
        dz = Az - P1z
        l_geom = math.hypot(X, dz)
        frac = run_g / X if X > 1e-12 else 0.0
        phi_D = self.phi_a + psi
        Dx, Dy, Dz = rc * math.cos(phi_D), rc * math.sin(phi_D), P1z + dz * frac
        rx, ry, rz = Ax - Dx, Ay - Dy, Az - Dz
        l_free = math.sqrt(rx * rx + ry * ry + rz * rz)
        if l_free > 1e-9:
            ex, ey, ez = rx / l_free, ry / l_free, rz / l_free
        else:
            ex, ey, ez = 0.0, 0.0, -1.0
        l_geo = l_geom - l_free
        stored = u_s * kappa
        l_rest = p.length - stored
        fully_wound = l_rest <= 1e-3
        l_rest = max(l_rest, 1e-3)
        delta = l_geom - l_rest
        # δ̇: dℓ/dt = e·v_A (A) + contribuição de P1 ao descascar; dL_rep/dt = -κ·u̇_s
        e_dot_vA = ex * vx + ey * vy + ez * vz
        proj = ex * tx + ey * ty + ez * tz
        if u_s_dot != 0.0:
            # P1 → A é reto (ψ_g = 0) ao descascar: ∂ℓ/∂P1 = -e
            l_dot = e_dot_vA - proj * u_s_dot
            p_peel_coef = max(0.0, kappa - proj)
        else:
            l_dot = e_dot_vA
            p_peel_coef = 0.0
        l_rest_dot = -kappa * u_s_dot
        delta_dot = l_dot - l_rest_dot
        k = p.EA / l_rest
        c = 2.0 * p.zeta * math.sqrt(k * p.m_eff)
        if delta > 0.0:
            T = max(0.0, k * delta + c * delta_dot)
            elastic = 0.5 * k * delta * delta
            p_damp = (T - k * delta) * delta_dot
        else:
            T = 0.0
            elastic = 0.0
            p_damp = 0.0
        p_peel = T * p_peel_coef * abs(u_s_dot)
        if delta > 0.0 and l_rest_dot > 0.0:
            # material novo (sem deformação) entra no trecho: a deformação uniforme cai e a
            # energia elástica correspondente ½·δ²·EA·L̇/L² é dissipada na inserção
            p_peel += 0.5 * k * delta * delta * l_rest_dot / l_rest
        # ângulo da dobra em P1 entre a espira e o trecho seguinte
        tn = kappa
        if ag < 1e-9:
            cosk = proj / tn
        else:
            # direção inicial da geodésica na planificação
            thx, thy = -regime * s1, regime * c1
            cosk = ((X * thx) * tx + (X * thy) * ty + dz * tz) / max(l_geom, 1e-9) / tn
        kink = math.degrees(math.acos(max(-1.0, min(1.0, cosk))))
        free_mass = p.lin_density * (l_free / max(l_geom, 1e-9)) * l_rest
        dist = self._dist_loads(l_free, free_mass, Dz, rz, (ex, ey, ez), vA, wind_fn, air_density, g)
        F = np.array((-T * ex, -T * ey, -T * ez))
        P1 = np.array((P1x, P1y, P1z))
        D = np.array((Dx, Dy, Dz))
        e = np.array((ex, ey, ez))
        s.u_s, s.psi, s.psi_g, s.psi_dot, s.regime, s.peeling = u_s, psi, psi_g, psi_dot, regime, peeling
        s.P1, s.D, s.A, s.e = P1, D, A.copy(), e
        s.l_free, s.l_geo, s.l_geom, s.l_rest = l_free, l_geo, l_geom, l_rest
        s.stored_len, s.wound_len = stored, stored + l_geo
        s.delta, s.delta_dot = delta, delta_dot
        s.tension = T
        s.tension_anchor = T * math.exp(-p.mu_wall * u_s)
        s.dist_load_on_obj = dist
        s.force_on_obj = F + dist
        s.slack = delta <= 0.0
        s.above_top = A[2] > p.tower_height
        s.fully_wound = fully_wound
        s.elastic_energy = elastic
        s.p_damp, s.p_peel, s.kink_deg = p_damp, p_peel, kink
        s.k, s.c = k, c
        return s

    def _dist_loads(self, l_free, free_mass, Dz, rz, e3, vA, wind_fn, air_density, g) -> np.ndarray:
        """Peso e arrasto distribuídos do vão livre (quadratura com ``element_length``), parcela
        transmitida ao objeto pela regra da alavanca (material parado em D, vão girando em D)."""
        p = self.p
        dist = np.zeros(3)
        if l_free <= 1e-6:
            return dist
        n = max(1, int(math.ceil(l_free / p.element_length)))
        sq, sq_sum = self._quad(n)
        dist[2] -= g * (free_mass / n) * sq_sum
        if air_density > 0.0 and (p.cd_normal > 0 or p.cd_tangent > 0):
            e = np.array(e3)
            V = np.multiply.outer(sq, vA)
            if wind_fn is not None:
                V -= wind_fn(Dz + sq * rz)
            vte = V @ e
            V -= np.multiply.outer(vte, e)            # componente normal
            q = 0.5 * air_density * p.rope_d * l_free / n
            vn_mag = np.sqrt(np.einsum("ij,ij->i", V, V))
            dist += (sq * vn_mag) @ V * (-q * p.cd_normal)
            dist += (float((sq * np.abs(vte)) @ vte) * (-q * math.pi * p.cd_tangent)) * e
        return dist

    @property
    def wound_turns(self) -> float:
        """Voltas em contato com a torre (armazenadas + geodésicas)."""
        return (self.s.u_s + abs(self.s.psi_g)) / TWO_PI

    # ---------------------------------------------------------- visualização
    def stored_polyline(self, pitch_scale: float = 1.0, pts_per_turn: int = 72) -> np.ndarray:
        """Hélice armazenada (âncora → P1). Com ``pitch_scale`` > 1 o passo é ampliado
        só para leitura, mantendo P1 na posição física (as espiras descem a partir de P1)."""
        s, p = self.s, self.p
        u_end = s.u_s
        if u_end < 1e-6:
            return np.zeros((0, 3))
        n = max(2, int(math.ceil(u_end / TWO_PI * pts_per_turn)) + 1)
        u = np.linspace(0.0, u_end, n)
        phi = self.phi_a + p.handedness * u
        z_end = p.z_anchor + p.vertical * p.pitch * u_end / TWO_PI
        z = z_end - p.vertical * (u_end - u) * p.pitch * pitch_scale / TWO_PI
        return np.stack([p.rc * np.cos(phi), p.rc * np.sin(phi), z], axis=1)

    def geodesic_polyline(self, pts_per_turn: int = 72) -> np.ndarray:
        s, p = self.s, self.p
        ag = abs(s.psi_g)
        if ag < 1e-6:
            return np.zeros((0, 3))
        n = max(2, int(math.ceil(ag / TWO_PI * pts_per_turn)) + 1)
        sgn = 1 if s.psi_g > 0 else -1
        phi0 = math.atan2(s.P1[1], s.P1[0])
        w = np.linspace(0.0, 1.0, n)
        phi = phi0 + sgn * ag * w
        z = s.P1[2] + (s.D[2] - s.P1[2]) * w
        return np.stack([p.rc * np.cos(phi), p.rc * np.sin(phi), z], axis=1)

    def free_polyline(self, n: int = 24, ground_z: float = 0.0) -> np.ndarray:
        """Vão livre: reto quando tenso; com folga, curva de comprimento igual ao
        comprimento de repouso disponível (parábola no plano vertical), recortada
        no solo — forma ilustrativa derivada do estado (sem efeito dinâmico)."""
        s = self.s
        D, A = s.D, s.A
        t = np.linspace(0.0, 1.0, n)[:, None]
        chord = A - D
        L = s.l_rest - s.l_geo
        if not s.slack or L <= s.l_free + 1e-6:
            return D[None, :] + t * chord[None, :]
        cl = float(np.linalg.norm(chord))
        down = np.array([0.0, 0.0, -1.0])
        if cl > 1e-9:
            u = chord / cl
            sag_dir = down - (down @ u) * u
            nn = np.linalg.norm(sag_dir)
            sag_dir = sag_dir / nn if nn > 1e-6 else np.array([1.0, 0.0, 0.0])
        else:
            sag_dir = down
        tt = np.linspace(0, 1, 48)[:, None]

        def arc(hh):
            pts = D[None, :] + tt * chord[None, :] + (4 * hh * tt * (1 - tt)) * sag_dir[None, :]
            return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())

        lo, hi = 0.0, max(L, 1e-3)
        for _ in range(32):
            mid = 0.5 * (lo + hi)
            if arc(mid) < L:
                lo = mid
            else:
                hi = mid
        hh = 0.5 * (lo + hi)
        pts = D[None, :] + t * chord[None, :] + (4 * hh * t * (1 - t)) * sag_dir[None, :]
        pts[:, 2] = np.maximum(pts[:, 2], ground_z + 0.5 * self.p.rope_d)
        return pts
