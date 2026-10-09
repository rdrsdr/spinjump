"""Modelo de corda com espiras deslizantes: a parte encostada na torre é discretizada sobre a
superfície do cilindro (opção "B"; ``rope.coil_sliding: true``).

Formulação
----------
* A corda entre a âncora e o ponto de saída D é uma cadeia de nós materiais (espaçamento
  ``element_length_m`` sem deformação) **presos à superfície** do cilindro de raio
  ``rc = D/2 + d/2``. Cada nó tem 2 graus de liberdade nas coordenadas planificadas
  ``x = rc·φ`` (ao redor) e ``z`` (altura). Não há colisão 3D: o nó não pode atravessar a parede
  por construção.
* Elasticidade axial unilateral por restrições de distância complacentes (XPBD,
  compliance ``Δσ/EA``): estável com nós leves e rigidez alta; a corda não resiste à compressão.
* Atrito de Coulomb com a parede (``rope.wall_friction``) aplicado no nível de posição, com força
  normal vinda da tração e da curvatura sobre o cilindro, ``N = T̄·Δσ·cos²β / rc`` (β = ângulo da
  corda com a horizontal). Daí sai o cabrestante dinâmico (exp(μθ)) e o escorregamento das espiras.
* Pré-tensão de enrolamento ``rope.winding_pretension_N``: sem ela não há força normal e as espiras
  cairiam pelo próprio peso.
* Contato corda–corda entre voltas vizinhas (uma volta não atravessa a outra na vertical).
* Gravidade sobre os nós. Arrasto do ar sobre a parte encostada é desprezado.
* O ponto de saída D continua definido pela tangência horizontal a partir do ponto de fixação A.
  Ao desenrolar, material passa da cadeia para o vão livre; ao enrolar, novos nós são assentados
  na direção do vão (geodésica na planificação) e passam a sentir atrito.
* O vão livre D→A é o mesmo do modelo ``wrap_tether`` (elástico unilateral, cargas
  distribuídas). Sua tração puxa a cadeia em D (força ``T·ê`` no plano tangente).
* Só os nós dentro de ``rope.coil_window_turns`` voltas a partir de D se movem; os mais distantes
  ficam parados. A justificativa é a queda exponencial da tração ao longo do enrolamento
  (cabrestante); o efeito é verificado por sensibilidade.

A perda na dobra de saída (quando o atrito segura a espira e o vão sai inclinado) continua sendo
contabilizada, agora com a direção real da corda na superfície; quando o atrito não segura, a corda
escorrega e a energia vai para o atrito.
"""
from __future__ import annotations

import math

import numpy as np

from ._chain_kernel import chain_step

from .rope import TWO_PI, RopeParams, RopeState, WrapTether


class SurfaceRope(WrapTether):
    model_name = "surface"

    def __init__(self, p: RopeParams, dt: float, pretension: float, window_turns: float, iterations: int,
                 update_every: int = 4, mass_scale: float = 1.0):
        super().__init__(p)
        self.mass_scale = max(1.0, float(mass_scale))
        self._kout = np.zeros(5)
        self.update_every = max(1, int(update_every))
        self._tick = -1
        self._chain_E = 0.0
        self._T_anchor = pretension
        self.h = dt
        self.T0 = max(0.0, pretension)
        self.window_turns = window_turns
        self.n_iter = max(1, int(iterations))
        self.ds = p.element_length
        self.m = max(p.lin_density, 1e-3) * self.ds          # massa por nó (mínimo para estabilidade)
        self.N = int(math.ceil(p.length / self.ds)) + 3
        self.x = np.zeros(self.N)
        self.z = np.zeros(self.N)
        self.vx = np.zeros(self.N)
        self.vz = np.zeros(self.N)
        self.z_init = np.zeros(self.N)
        self.k = 0                 # nó material imediatamente antes de D (ativos: 0..k+1)
        self.w = 0.0               # fração de D no segmento (k, k+1)
        self.sw = p.handedness     # sentido do enrolamento atual (+1 ccw, -1 cw)
        self.sig_D = 0.0           # coordenada material de D (m, sem deformação)
        self.straight = False      # sem corda encostada (parte reta da âncora)
        self.lay = np.array([1.0, 0.0])
        self._span_prev: tuple | None = None   # (E_el, trabalho do objeto, trabalho da ponta, amortecimento)
        self._dk = np.zeros(2)                  # deslocamento do último nó encostado na atualização
        self.e_numeric = 0.0                    # energia criada numericamente no vão (deveria ser ~0)
        self.e_fric_total = 0.0
        # janela de nós móveis: no mínimo as voltas para a tração cair 100× por cabrestante, ln(100)/(2πμ)
        self.window_turns = max(window_turns, math.log(100.0) / (TWO_PI * max(p.mu_wall, 0.05)))
        self.window_nodes = max(4, int(math.ceil(self.window_turns * TWO_PI * p.kappa / self.ds)))
        # inércia dos nós encostados: escalonada (quase-estático) e com piso ω·h ≤ 2 para a rigidez axial
        h_c = dt * self.update_every
        self.m_inertial = max(self.m * self.mass_scale, (p.EA / self.ds) * h_c * h_c / 4.0)

    # ----------------------------------------------------------------- layout
    def initial_layout(self, rho_A: float, theta_A: float) -> dict:
        p, ds = self.p, self.ds
        rc = p.rc
        if rho_A <= rc:
            raise ValueError("ponto de fixação inicial dentro do raio da corda")
        l_h = math.sqrt(rho_A ** 2 - rc ** 2)
        wound_mat = p.length - l_h
        if wound_mat <= ds:
            from .i18n import t
            raise ValueError(t("err.rope_too_short_start", L=p.length, lh=l_h))
        eps0 = self.T0 / p.EA
        wound_geo = wound_mat * (1.0 + eps0)
        u0 = wound_geo / p.kappa
        h = p.handedness
        beta = math.acos(rc / rho_A)
        self.phi_a = theta_A - h * beta - h * u0
        self.sw = h
        # nós ao longo da hélice: material i·ds ocupa arco i·ds·(1+ε0)
        k = int(math.floor(wound_mat / ds))
        n_act = min(self.N, k + 2)
        i = np.arange(n_act)
        u = i * ds * (1.0 + eps0) / p.kappa
        self.x[:n_act] = p.rc * (self.phi_a + h * u)
        self.z[:n_act] = p.z_anchor + p.vertical * p.pitch * u / TWO_PI
        self.z_init[:] = 0.0
        self.z_init[:n_act] = self.z[:n_act]
        self.k = k
        self.sig_D = wound_mat
        self.w = (wound_mat - k * ds) / ds
        D = self._D_point()
        A = np.array([rho_A * math.cos(theta_A), rho_A * math.sin(theta_A), D[2]])
        self.s.u_s = u0
        return dict(u0=u0, wound0=wound_mat, turns0=u0 / TWO_PI, free0=l_h, D0=D, A0=A,
                    phi_anchor=self.phi_a, helix_height=u0 / TWO_PI * p.pitch)

    def _D_point(self) -> np.ndarray:
        rc = self.p.rc
        k, w = self.k, self.w
        if self.straight:
            return self.stored_point(0.0)
        xD = self.x[k] + w * (self.x[k + 1] - self.x[k])
        zD = self.z[k] + w * (self.z[k + 1] - self.z[k])
        phi = xD / rc
        return np.array([rc * math.cos(phi), rc * math.sin(phi), zD])

    # ----------------------------------------------------------- saída / tangência
    def _activate(self, j: int, xj: float, zj: float, g: float) -> float:
        self.x[j], self.z[j] = xj, zj
        self.vx[j] = self.vz[j] = 0.0
        self.z_init[j] = zj
        L = math.hypot(xj - self.x[j - 1], zj - self.z[j - 1])
        st = max(L - self.ds, 0.0)
        return -(self.m * g * zj + 0.5 * self.p.EA / self.ds * st * st)   # energia que entra (fluxo negativo)

    def _deactivate(self, j: int, g: float) -> float:
        """Nó j deixa a parede: sai da contabilidade da cadeia com sua energia potencial e a
        elástica do segmento (j-1, j)."""
        L = math.hypot(self.x[j] - self.x[j - 1], self.z[j] - self.z[j - 1]) if j >= 1 else self.ds
        st = max(L - self.ds, 0.0)
        e = (0.5 * self.m_inertial * (self.vx[j] ** 2 + self.vz[j] ** 2) + self.m * g * self.z[j]
             + 0.5 * self.p.EA / self.ds * st * st)
        self.vx[j] = self.vz[j] = 0.0
        return e

    def _update_departure(self, xD_target: float, g: float) -> float:
        """Move D ao longo da cadeia até a coordenada de tangência; devolve a energia mecânica
        que sai da contabilidade da cadeia (nós liberados) menos a que entra (nós assentados)."""
        sw, ds = self.sw, self.ds
        x = self.x
        flux = 0.0
        # descasca: D recua para trás do nó k → a ponta k+1 sai da parede e o nó k vira a ponta
        while self.k >= 1 and sw * xD_target < sw * x[self.k]:
            flux += self._deactivate(self.k + 1, g)
            self.k -= 1
        # enrola: D avança além da ponta → assenta-se um novo nó na direção do vão
        while sw * xD_target > sw * x[self.k + 1] and self.k + 2 < self.N:
            self.k += 1
            j = self.k + 1
            flux += self._activate(j, x[self.k] + ds * self.lay[0], self.z[self.k] + ds * self.lay[1], g)
        dx = x[self.k + 1] - x[self.k]
        if abs(dx) < 1e-12:
            w = 0.0
        else:
            w = (xD_target - x[self.k]) / dx
        self.w = min(1.0, max(0.0, w))
        self.sig_D = (self.k + self.w) * ds
        return flux

    # --------------------------------------------------------------- dinâmica
    def update(self, A: np.ndarray, vA: np.ndarray, wind=None, air_density: float = 0.0,
               g: float = 9.81) -> RopeState:
        p, s, h = self.p, self.s, self.h
        rc = p.rc
        if not self._initialized:
            self.reset(A)
        theta_u = self._track_theta(A)
        rho = math.hypot(A[0], A[1])
        rho_c = max(rho, rc * (1 + 1e-9))
        beta = math.acos(rc / rho_c)
        flux = 0.0
        sig_prev = self.sig_D
        # alvo de tangência no sentido do enrolamento atual
        xD_target = rc * (theta_u - self.sw * beta)
        if not self.straight:
            flux += self._update_departure(xD_target, g)
            if self.k == 0 and self.sw * xD_target <= self.sw * self.x[0]:
                # totalmente desenrolada: corda parte reta da âncora
                flux += self._deactivate(1, g)
                self.straight = True
                self.sig_D = 0.0
        if self.straight:
            # volta a enrolar em qualquer sentido a partir da âncora, se a geometria exigir
            x0 = self.x[0]
            for sgn in (self.sw, -self.sw):
                xt = rc * (theta_u - sgn * beta)
                if sgn * (xt - x0) > 0.0:
                    self.sw = sgn
                    self.straight = False
                    self.k = 0
                    self.lay = np.array([float(sgn), 0.0])
                    flux += self._activate(1, x0 + sgn * self.ds, self.z[0], g)
                    flux += self._update_departure(xt, g)
                    break
        D = self._D_point()
        rx_, ry_, rz_ = A[0] - D[0], A[1] - D[1], A[2] - D[2]
        l_free = math.sqrt(rx_ * rx_ + ry_ * ry_ + rz_ * rz_)
        r = np.array((rx_, ry_, rz_))
        e = r / l_free if l_free > 1e-9 else np.array([0.0, 0.0, -1.0])
        l_rest = max(p.length - self.sig_D, 1e-3)
        delta = l_free - l_rest
        k_ax = p.EA / l_rest
        c_ax = 2.0 * p.zeta * math.sqrt(k_ax * p.m_eff)
        elastic_free = 0.5 * k_ax * delta * delta if delta > 0.0 else 0.0
        # direção do vão no plano tangente em D (componente radial nula pela tangência)
        cphi, sphi = D[0] / rc, D[1] / rc
        ex_s = -e[0] * sphi + e[1] * cphi
        ez_s = float(e[2])
        nrm = math.hypot(ex_s, ez_s)
        if nrm > 1e-9:
            self.lay[0], self.lay[1] = ex_s / nrm, ez_s / nrm
        # direção da corda na superfície em D e perda na dobra ao descascar
        kk = self.k
        tx_, tz_ = self.x[kk + 1] - self.x[kk], self.z[kk + 1] - self.z[kk]
        tn = math.hypot(tx_, tz_)
        if self.straight or tn <= 1e-12:
            cos_k = 1.0
        else:
            cos_k = (tx_ * self.lay[0] + tz_ * self.lay[1]) / tn
        release = max(0.0, sig_prev - self.sig_D) / h
        # δ̇ = e·v_A + σ̇_D·(1 − cos θ), com σ̇_D geométrico (tangência): ẋ_D = rc·(θ̇ − s·β̇) e
        # dσ/dx da corda em D; os saltos da atualização da corda encostada não entram
        if rho > 1e-9 and not self.straight:
            theta_dot = (A[0] * vA[1] - A[1] * vA[0]) / rho ** 2
            rho_dot = (A[0] * vA[0] + A[1] * vA[1]) / rho
            l_h = math.sqrt(max(rho_c * rho_c - rc * rc, 1e-18))
            beta_dot = rc * rho_dot / (rho_c * l_h)
            xD_dot = rc * (theta_dot - self.sw * beta_dot)
            dxds = (self.x[self.k + 1] - self.x[self.k]) / self.ds
            sig_dot = xD_dot / dxds if abs(dxds) > 1e-6 else 0.0
        else:
            sig_dot = 0.0
        delta_dot = float(e @ vA) + sig_dot * (1.0 - cos_k)
        T = max(0.0, k_ax * delta + c_ax * delta_dot) if delta > 0.0 else 0.0
        # perda na saída pelo balanço do vão (elemento sem massa): trabalho recebido no passo anterior
        # (objeto + ponta da corda encostada) − variação da energia elástica − amortecimento
        p_peel = 0.0
        p_damp = 0.0
        if self._span_prev is not None:
            e_prev, w_obj, w_chain, f_damp, delta_prev = self._span_prev
            # amortecimento: força do amortecedor × alongamento que de fato ocorreu no passo
            d_damp = f_damp * (max(delta, 0.0) - max(delta_prev, 0.0))
            p_damp = d_damp / h
            loss = w_obj + w_chain - (elastic_free - e_prev) - d_damp
            if loss >= 0.0:
                p_peel = loss / h
            else:
                self.e_numeric += -loss
        # corda encostada (quase-estática) com a força do vão aplicada em D
        e_fric, chain_E, T_anchor = self._step_chain(T * ex_s, T * ez_s, g)
        # trabalho da ponta da corda encostada sobre o vão: deslocamento real de D na atualização
        dD = self._D_point() - D
        f_damp = (T - k_ax * delta) if delta > 0.0 else 0.0
        self._span_prev = (elastic_free, T * float(e @ vA) * h, -T * float(e @ dD), f_damp, delta)
        self.e_fric_total += e_fric
        free_mass = p.lin_density * l_rest
        dist = self._dist_loads(l_free, free_mass, D[2], r[2], (e[0], e[1], e[2]), vA, wind, air_density, g)
        F = -T * e
        u_s = abs(self.x[self.k] + self.w * (self.x[self.k + 1] - self.x[self.k]) - self.x[0]) / rc \
            if not self.straight else 0.0
        s.u_s, s.psi, s.psi_g, s.regime = u_s, self.sw * u_s, 0.0, (0 if self.straight else self.sw)
        s.peeling = release > 0.0
        s.theta_u = theta_u
        s.P1, s.D, s.A, s.e = D, D, A.copy(), e
        s.l_free, s.l_geo, s.l_geom, s.l_rest = l_free, 0.0, l_free, l_rest
        s.stored_len = s.wound_len = self.sig_D
        s.delta, s.delta_dot = delta, delta_dot
        s.tension = T
        s.tension_anchor = T_anchor
        s.dist_load_on_obj = dist
        s.force_on_obj = F + dist
        s.slack = delta <= 0.0
        s.above_top = A[2] > p.tower_height
        s.fully_wound = l_rest <= 1e-3
        s.elastic_energy = elastic_free
        s.chain_energy = chain_E
        s.p_damp, s.p_peel = p_damp, p_peel
        s.kink_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos_k))))
        s.e_fric, s.e_massflux = e_fric, flux
        s.coil_drop = self.coil_drop()
        s.k, s.c = k_ax, c_ax
        return s

    def _step_chain(self, fx_end: float, fz_end: float, g: float):
        """Passo implícito da corda encostada (kernel compilado em ``_chain_kernel.chain_step``):
        Euler implícito linearizado, matriz bloco-tridiagonal resolvida diretamente, atrito de
        Coulomb por impulso, contato entre voltas. Executado a cada ``update_every`` passos físicos
        com ``h = update_every·dt``. Devolve (atrito dissipado J, energia da cadeia J, T_âncora N)."""
        kend = self.k + 1                       # nós dinâmicos 1..k+1 (D entre k e k+1)
        if self.straight:
            return 0.0, 0.0, math.hypot(fx_end, fz_end)
        self._tick += 1
        if self._tick % self.update_every:
            return 0.0, self._chain_E, self._T_anchor
        p = self.p
        h = self.h * self.update_every
        j0 = max(1, kend - self.window_nodes)
        out = self._kout
        chain_step(self.x, self.z, self.vx, self.vz, j0 - 1, kend, self.ds, p.EA, p.zeta,
                   self.m_inertial, self.m, g, h, fx_end, fz_end,
                   p.EA / max(p.length - self.sig_D, 1e-3), p.mu_wall, p.rc, p.vertical, p.rope_d,
                   float(self.sw), float(self.w), out)
        self._dk[0], self._dk[1] = out[3], out[4]
        self._chain_E = float(out[1])
        self._T_anchor = float(out[2])
        return float(out[0]), self._chain_E, self._T_anchor

    # ------------------------------------------------------------- métricas
    def coil_drop(self) -> float:
        """Maior deslocamento vertical (m) de um nó encostado em relação à posição em que foi assentado."""
        kend = self.k
        if self.straight or kend < 1:
            return 0.0
        dz = self.z_init[1:kend + 1] - self.z[1:kend + 1]
        return float(np.max(np.abs(dz))) if dz.size else 0.0

    @property
    def wound_turns(self) -> float:
        return self.s.u_s / TWO_PI

    # ---------------------------------------------------------- visualização
    def stored_polyline(self, pitch_scale: float = 1.0, pts_per_turn: int = 72) -> np.ndarray:
        """Corda encostada, na geometria real (sem ampliação de passo)."""
        if self.straight:
            return np.zeros((0, 3))
        rc = self.p.rc
        kend = self.k
        per_turn = TWO_PI * self.p.kappa / self.ds
        stride = max(1, int(round(per_turn / max(pts_per_turn, 1))))
        idx = np.arange(0, kend + 1, stride)
        if idx[-1] != kend:
            idx = np.append(idx, kend)
        phi = self.x[idx] / rc
        pts = np.stack([rc * np.cos(phi), rc * np.sin(phi), self.z[idx]], axis=1)
        return np.vstack([pts, self._D_point()[None, :]])

    def geodesic_polyline(self, pts_per_turn: int = 72) -> np.ndarray:
        return np.zeros((0, 3))
