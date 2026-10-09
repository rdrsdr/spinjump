"""Kernel compilado (numba) do passo implícito da corda encostada (``surface_rope``).

Mesma formulação de ``SurfaceRope._step_chain``: Euler implícito linearizado com matriz
bloco-tridiagonal 2×2 (``M − h·D − h²·K``) resolvida pelo algoritmo de Thomas em blocos, atrito de
Coulomb como impulso limitado a μN·h e contato vertical entre voltas vizinhas.
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit

TWO_PI = 2.0 * math.pi
FRICTION_ITERS = 8


@njit(cache=True)
def _thomas(Dxx, Dzz, Dxz, axx, azz, axz, rx, rz, nm, dvx, dvz):
    """Resolve o sistema bloco-tridiagonal simétrico (blocos diagonais D, fora da diagonal −a[j+1])
    sem alterar as entradas."""
    Pxx = Dxx.copy()
    Pzz = Dzz.copy()
    Pxz = Dxz.copy()
    qx = rx.copy()
    qz = rz.copy()
    for j in range(1, nm):
        exx = -axx[j]
        ezz = -azz[j]
        exz = -axz[j]
        det = Pxx[j - 1] * Pzz[j - 1] - Pxz[j - 1] * Pxz[j - 1]
        ixx = Pzz[j - 1] / det
        izz = Pxx[j - 1] / det
        ixz = -Pxz[j - 1] / det
        wxx = exx * ixx + exz * ixz
        wxz = exx * ixz + exz * izz
        wzx = exz * ixx + ezz * ixz
        wzz = exz * ixz + ezz * izz
        Pxx[j] -= wxx * exx + wxz * exz
        Pxz[j] -= wxx * exz + wxz * ezz
        Pzz[j] -= wzx * exz + wzz * ezz
        qx[j] -= wxx * qx[j - 1] + wxz * qz[j - 1]
        qz[j] -= wzx * qx[j - 1] + wzz * qz[j - 1]
    for j in range(nm - 1, -1, -1):
        bx = qx[j]
        bz = qz[j]
        if j + 1 < nm:
            exx = -axx[j + 1]
            ezz = -azz[j + 1]
            exz = -axz[j + 1]
            bx -= exx * dvx[j + 1] + exz * dvz[j + 1]
            bz -= exz * dvx[j + 1] + ezz * dvz[j + 1]
        det = Pxx[j] * Pzz[j] - Pxz[j] * Pxz[j]
        dvx[j] = (Pzz[j] * bx - Pxz[j] * bz) / det
        dvz[j] = (Pxx[j] * bz - Pxz[j] * bx) / det


@njit(cache=True)
def _matvec(Dxx, Dzz, Dxz, axx, azz, axz, dvx, dvz, nm, ox, oz):
    for j in range(nm):
        ox[j] = Dxx[j] * dvx[j] + Dxz[j] * dvz[j]
        oz[j] = Dxz[j] * dvx[j] + Dzz[j] * dvz[j]
        if j + 1 < nm:
            ox[j] -= axx[j + 1] * dvx[j + 1] + axz[j + 1] * dvz[j + 1]
            oz[j] -= axz[j + 1] * dvx[j + 1] + azz[j + 1] * dvz[j + 1]
        if j >= 1:
            ox[j] -= axx[j] * dvx[j - 1] + axz[j] * dvz[j - 1]
            oz[j] -= axz[j] * dvx[j - 1] + azz[j] * dvz[j - 1]


@njit(cache=True)
def chain_step(x, z, vx, vz, b, kend, ds, EA, zeta, m, m_real, g, h, fx_end, fz_end, ks_end,
               mu, rc, vertical, rope_d, sw, w, out):
    """Atualiza x, z, vx, vz nos nós b+1..kend (b fixo). A força do vão atua no ponto de saída
    D = (1−w)·P[kend−1] + w·P[kend] e é dividida pela regra da alavanca. ``out`` recebe
    [atrito dissipado (J), energia da cadeia 0..kend (J), tração no 1º segmento (N), dDx, dDz]."""
    n = kend - b + 1            # nós no recorte (índice 0 = contorno)
    nm = n - 1
    nseg = n - 1
    EAds = EA / ds
    cseg0 = 2.0 * zeta * math.sqrt(EAds * m)
    L = np.empty(nseg)
    nx = np.empty(nseg)
    nz = np.empty(nseg)
    T = np.empty(nseg)
    axx = np.empty(nseg)
    azz = np.empty(nseg)
    axz = np.empty(nseg)
    FX = np.zeros(n)
    FZ = np.empty(n)
    for i in range(n):
        FZ[i] = -m_real * g
    for s in range(nseg):
        i = b + s
        dx = x[i + 1] - x[i]
        dz = z[i + 1] - z[i]
        Ls = math.sqrt(dx * dx + dz * dz)
        if Ls < 1e-12:
            Ls = 1e-12
        ux = dx / Ls
        uz = dz / Ls
        L[s], nx[s], nz[s] = Ls, ux, uz
        taut = 1.0 if Ls > ds else 0.0
        Ts = EAds * (Ls - ds) * taut
        T[s] = Ts
        c = cseg0 * taut
        v0x = vx[i] if s > 0 else 0.0
        v0z = vz[i] if s > 0 else 0.0
        dvn = (vx[i + 1] - v0x) * ux + (vz[i + 1] - v0z) * uz
        fs = Ts + c * dvn
        FX[s] += fs * ux
        FZ[s] += fs * uz
        FX[s + 1] -= fs * ux
        FZ[s + 1] -= fs * uz
        gk = Ts / Ls
        kxx = taut * (EAds * ux * ux + gk * (1.0 - ux * ux))
        kzz = taut * (EAds * uz * uz + gk * (1.0 - uz * uz))
        kxz = taut * (EAds - gk) * ux * uz
        axx[s] = h * c * ux * ux + h * h * kxx
        azz[s] = h * c * uz * uz + h * h * kzz
        axz[s] = h * c * ux * uz + h * h * kxz
    FX[n - 1] += w * fx_end
    FZ[n - 1] += w * fz_end
    if n >= 3:
        FX[n - 2] += (1.0 - w) * fx_end
        FZ[n - 2] += (1.0 - w) * fz_end
    else:
        FX[n - 1] += (1.0 - w) * fx_end
        FZ[n - 1] += (1.0 - w) * fz_end
    Fm = math.sqrt(fx_end * fx_end + fz_end * fz_end)
    # blocos diagonais (móveis j = 0..nm-1 ↔ recorte j+1) e fora da diagonal (j, j+1)
    Dxx = np.empty(nm)
    Dzz = np.empty(nm)
    Dxz = np.empty(nm)
    for j in range(nm):
        Dxx[j] = m + axx[j]
        Dzz[j] = m + azz[j]
        Dxz[j] = axz[j]
        if j + 1 < nseg:
            Dxx[j] += axx[j + 1]
            Dzz[j] += azz[j + 1]
            Dxz[j] += axz[j + 1]
    if Fm > 0.0:
        ux = fx_end / Fm
        uz = fz_end / Fm
        for jj, wt in ((nm - 1, w * w), (nm - 2, (1.0 - w) * (1.0 - w))):
            if jj >= 0:
                Dxx[jj] += h * h * ks_end * wt * ux * ux
                Dzz[jj] += h * h * ks_end * wt * uz * uz
                Dxz[jj] += h * h * ks_end * wt * ux * uz
    rx = np.empty(nm)
    rz = np.empty(nm)
    for j in range(nm):
        rx[j] = h * FX[j + 1]
        rz[j] = h * FZ[j + 1]
    # força normal de cada nó móvel (tração média × comprimento × cos²β / rc) e limite de atrito
    Nlim = np.empty(nm)
    for j in range(nm):
        i = b + 1 + j
        if j < nm - 1:
            Tn = 0.5 * (T[j] + T[j + 1])
            tx = x[i + 1] - x[i - 1]
            tz = z[i + 1] - z[i - 1]
        else:
            Tn = 0.5 * (T[j] + Fm)
            tx = x[i] - x[i - 1] + (fx_end / Fm * ds if Fm > 0.0 else 0.0)
            tz = z[i] - z[i - 1] + (fz_end / Fm * ds if Fm > 0.0 else 0.0)
        t2 = tx * tx + tz * tz
        cos2 = tx * tx / t2 if t2 > 1e-18 else 1.0
        Nlim[j] = mu * Tn * ds * cos2 / rc
    # atrito de Coulomb dentro da solução implícita (conjunto ativo): nós aderidos têm velocidade
    # final nula; nós escorregando recebem força μN contra o movimento; itera até estabilizar
    v0x = np.empty(nm)
    v0z = np.empty(nm)
    for j in range(nm):
        v0x[j] = vx[b + 1 + j]
        v0z[j] = vz[b + 1 + j]
    dvx = np.zeros(nm)
    dvz = np.zeros(nm)
    _thomas(Dxx, Dzz, Dxz, axx, azz, axz, rx, rz, nm, dvx, dvz)
    stick = np.zeros(nm, np.bool_)
    ffx = np.zeros(nm)
    ffz = np.zeros(nm)
    for j in range(nm):
        tvx = v0x[j] + dvx[j]
        tvz = v0z[j] + dvz[j]
        vm = math.sqrt(tvx * tvx + tvz * tvz)
        if m * vm <= Nlim[j] * h:
            stick[j] = True
        else:
            ffx[j] = -Nlim[j] * tvx / vm
            ffz[j] = -Nlim[j] * tvz / vm
    PEN = 1e9 * (m + 1.0)
    Exx = Dxx.copy()
    Ezz = Dzz.copy()
    Exz = Dxz.copy()
    qx = rx.copy()
    qz = rz.copy()
    ox = np.empty(nm)
    oz = np.empty(nm)
    for it in range(FRICTION_ITERS):
        for j in range(nm):
            if stick[j]:
                Exx[j] = Dxx[j] + PEN
                Ezz[j] = Dzz[j] + PEN
                Exz[j] = Dxz[j]
                qx[j] = -PEN * v0x[j]
                qz[j] = -PEN * v0z[j]
            else:
                Exx[j] = Dxx[j]
                Ezz[j] = Dzz[j]
                Exz[j] = Dxz[j]
                qx[j] = rx[j] + h * ffx[j]
                qz[j] = rz[j] + h * ffz[j]
        _thomas(Exx, Ezz, Exz, axx, azz, axz, qx, qz, nm, dvx, dvz)
        _matvec(Dxx, Dzz, Dxz, axx, azz, axz, dvx, dvz, nm, ox, oz)
        changed = False
        for j in range(nm):
            nvx = v0x[j] + dvx[j]
            nvz = v0z[j] + dvz[j]
            if stick[j]:
                # força que a parede precisa fornecer para manter o nó parado
                fx_req = (ox[j] - rx[j]) / h
                fz_req = (oz[j] - rz[j]) / h
                fr = math.sqrt(fx_req * fx_req + fz_req * fz_req)
                if fr > Nlim[j] * (1.0 + 1e-9):
                    stick[j] = False
                    ffx[j] = Nlim[j] * fx_req / fr
                    ffz[j] = Nlim[j] * fz_req / fr
                    changed = True
            else:
                if nvx * ffx[j] + nvz * ffz[j] >= 0.0:
                    stick[j] = True          # inverteu: o atrito para o nó
                    changed = True
                else:
                    vm = math.sqrt(nvx * nvx + nvz * nvz)
                    ffx[j] = -Nlim[j] * nvx / vm
                    ffz[j] = -Nlim[j] * nvz / vm
        if not changed:
            break
    e_fric = 0.0
    kd = kend - 1 if kend - 1 > b else kend
    xD0 = (1.0 - w) * x[kd] + w * x[kend]
    zD0 = (1.0 - w) * z[kd] + w * z[kend]
    for j in range(nm):
        i = b + 1 + j
        if stick[j]:
            vx[i] = 0.0
            vz[i] = 0.0
        else:
            vx[i] = v0x[j] + dvx[j]
            vz[i] = v0z[j] + dvz[j]
            e_fric += -(ffx[j] * vx[i] + ffz[j] * vz[i]) * h
    xo = np.empty(nm)
    zo = np.empty(nm)
    for j in range(nm):
        i = b + 1 + j
        xo[j] = x[i]
        zo[j] = z[i]
        x[i] += h * vx[i]
        z[i] += h * vz[i]
    # contato entre voltas: material uma volta depois fica a ≥ d da volta anterior na vertical
    turn = TWO_PI * rc
    na = kend + 1
    env = np.empty(na)
    acc = -1e300
    for i in range(na):
        v = sw * x[i]
        if v > acc:
            acc = v
        env[i] = acc
    for j in range(nm):
        i = b + 1 + j
        q = sw * x[i] - turn
        if q < env[0]:
            continue
        lo = 0
        hi = i
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if env[mid] <= q:
                lo = mid
            else:
                hi = mid
        span = env[hi] - env[lo]
        f = (q - env[lo]) / span if span > 1e-12 else 0.0
        if f > 1.0:
            f = 1.0
        zp = z[lo] + f * (z[hi] - z[lo])
        if vertical < 0:
            lim = zp - rope_d
            if z[i] > lim:
                z[i] = lim
        else:
            lim = zp + rope_d
            if z[i] < lim:
                z[i] = lim
    for j in range(nm):
        i = b + 1 + j
        vx[i] = (x[i] - xo[j]) / h
        vz[i] = (z[i] - zo[j]) / h
    vx[b] = 0.0
    vz[b] = 0.0
    # energia da cadeia 0..kend: cinética (inércia escalonada) + potencial (peso real) + elástica
    E = 0.0
    T0 = 0.0
    for i in range(1, kend + 1):
        E += 0.5 * m * (vx[i] * vx[i] + vz[i] * vz[i]) + m_real * g * z[i]
        dx = x[i] - x[i - 1]
        dz = z[i] - z[i - 1]
        st = math.sqrt(dx * dx + dz * dz) - ds
        if st > 0.0:
            E += 0.5 * EAds * st * st
            if i == 1:
                T0 = EAds * st
    out[0] = e_fric
    out[1] = E
    out[2] = T0
    out[3] = (1.0 - w) * x[kd] + w * x[kend] - xD0
    out[4] = (1.0 - w) * z[kd] + w * z[kend] - zD0


def warmup() -> None:
    """Compila o kernel (cache em disco) com uma cadeia mínima; usado na construção da imagem."""
    n = 6
    x = np.linspace(0.0, 1.0, n)
    z = np.zeros(n)
    vx = np.zeros(n)
    vz = np.zeros(n)
    out = np.zeros(5)
    chain_step(x, z, vx, vz, 0, n - 1, 0.2, 5e4, 0.1, 0.75, 0.015, 9.81, 2.5e-4, 10.0, -5.0, 1e3,
               0.4, 2.5, -1, 0.012, 1.0, 0.5, out)
