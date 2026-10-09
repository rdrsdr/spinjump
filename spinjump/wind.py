"""Vento horizontal: média (com perfil vertical opcional) + rajadas Ornstein–Uhlenbeck.

Rajada g(t) ∈ R² (horizontal), discretização exata do processo OU:
    g[n+1] = g[n]·exp(-Δt/τ) + σ·sqrt(1 - exp(-2Δt/τ))·ξ,   ξ ~ N(0, I)
com σ = ``gust_std_ms`` (desvio estacionário por componente) e τ =
``correlation_time_s``. O gerador é semeado com ``wind.seed``; a rajada é
uniforme no espaço (simplificação). Perfil médio: U(z) = U·(z/z_ref)^α.
"""
from __future__ import annotations

import math

import numpy as np

from .config import SimConfig


class Wind:
    def __init__(self, cfg: SimConfig, dt: float):
        w = cfg.wind
        self.enabled = bool(w.enabled)
        self.U = float(w.speed_mean_ms)
        ang = math.radians(w.direction_deg)
        self.dir = np.array([math.cos(ang), math.sin(ang), 0.0])
        self.sigma = float(w.gust_std_ms)
        self.tau = float(w.correlation_time_s)
        self.alpha = float(w.shear_exponent)
        self.zref = float(w.reference_height_m)
        self.rng = np.random.default_rng(int(w.seed))
        self.dt = dt
        self.a = math.exp(-dt / self.tau)
        self.b = self.sigma * math.sqrt(max(0.0, 1.0 - self.a * self.a))
        # estado inicial amostrado da distribuição estacionária
        g0 = self.sigma * self.rng.standard_normal(2) if self.enabled else np.zeros(2)
        self.g = (float(g0[0]), float(g0[1]))

    def advance(self):
        if self.enabled and self.sigma > 0:
            xi = self.rng.standard_normal(2)
            self.g = (self.a * self.g[0] + self.b * xi[0], self.a * self.g[1] + self.b * xi[1])

    def _profile(self, z):
        if self.alpha == 0.0:
            return np.ones_like(np.asarray(z, dtype=float))
        zz = np.maximum(np.asarray(z, dtype=float), 0.5)
        return (zz / self.zref) ** self.alpha

    def at(self, z: float) -> tuple:
        if not self.enabled:
            return (0.0, 0.0, 0.0)
        u = self.U if self.alpha == 0.0 else self.U * (max(z, 0.5) / self.zref) ** self.alpha
        return (u * self.dir[0] + self.g[0], u * self.dir[1] + self.g[1], 0.0)

    def at_many(self, z: np.ndarray) -> np.ndarray:
        z = np.asarray(z, dtype=float)
        if not self.enabled:
            return np.zeros((z.size, 3))
        if self.alpha == 0.0:
            out = np.empty((z.size, 3))
            out[:, 0] = self.U * self.dir[0] + self.g[0]
            out[:, 1] = self.U * self.dir[1] + self.g[1]
            out[:, 2] = 0.0
            return out
        prof = self._profile(z)
        out = np.empty((z.size, 3))
        out[:, 0] = self.U * prof * self.dir[0] + self.g[0]
        out[:, 1] = self.U * prof * self.dir[1] + self.g[1]
        out[:, 2] = 0.0
        return out
