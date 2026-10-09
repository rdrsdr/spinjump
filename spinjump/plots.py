"""Gráficos estáticos (Matplotlib/Agg). Um eixo por gráfico; paleta categórica em ordem fixa;
cores de status sempre acompanhadas de rótulo textual."""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .i18n import t as tr  # noqa: E402
from .sim import TELEMETRY_FIELDS  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
STATUS = {"OK": "#0ca30c", "ATENÇÃO": "#fab219", "DANO": "#d03b3b"}
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 9.5, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "lines.linewidth": 1.6, "legend.frameon": False, "legend.fontsize": 8.5,
    "font.family": "DejaVu Sans",
})


def _cols(samples):
    S = np.asarray(samples, dtype=float)
    return S, {k: i for i, k in enumerate(TELEMETRY_FIELDS)}


def _vmark(ax, t, label):
    if t is not None:
        ax.axvline(t, color=MUTED, lw=0.9, ls="--")
        ax.annotate(label, (t, 1.0), xycoords=("data", "axes fraction"), xytext=(3, -12),
                    textcoords="offset points", color=INK2, fontsize=8)


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def make_all(sim, summary: dict, outdir: Path) -> list[str]:
    S, F = _cols(sim.samples)
    t = S[:, F["t"]]
    tg = summary["ground_arrival"]["t_s"]
    R, H = sim.R, sim.cfg.tower.height_m
    files = []

    # 1. trajetória 3D
    fig = plt.figure(figsize=(6.4, 5.6))
    ax = fig.add_subplot(111, projection="3d")
    th = np.linspace(0, 2 * math.pi, 60)
    for z in np.linspace(0, H, 6):
        ax.plot(R * np.cos(th), R * np.sin(th), z, color=AXIS, lw=0.7)
    for a in np.linspace(0, 2 * math.pi, 12, endpoint=False):
        ax.plot([R * math.cos(a)] * 2, [R * math.sin(a)] * 2, [0, H], color=AXIS, lw=0.5)
    ax.plot(S[:, F["x"]], S[:, F["y"]], S[:, F["z"]], color=SERIES[0], lw=1.4, label=tr("p.com"))
    ax.plot(S[:, F["Dx"]], S[:, F["Dy"]], S[:, F["Dz"]], color=SERIES[1], lw=1.0, label=tr("p.depart"))
    if tg is not None:
        i = int(np.searchsorted(t, tg))
        ax.scatter([S[i, F["x"]]], [S[i, F["y"]]], [S[i, F["z"]]], color=INK, s=24, label=tr("p.first_ground"))
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)"); ax.set_zlabel("z (m)")
    ax.set_title(tr("p.traj3d"))
    lim = max(np.abs(S[:, [F["x"], F["y"]]]).max(), R) * 1.05
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(0, H * 1.02)
    ax.legend(loc="upper left")
    _save(fig, outdir / "trajectory_3d.png"); files.append("trajectory_3d.png")

    # 2. vista superior
    fig, ax = plt.subplots(figsize=(6.2, 6.0))
    ax.add_patch(plt.Circle((0, 0), R, color=AXIS, alpha=0.6, lw=0))
    ax.plot(S[:, F["x"]], S[:, F["y"]], color=SERIES[0], label=tr("p.com"))
    if tg is not None:
        i = int(np.searchsorted(t, tg))
        ax.plot(S[i:, F["x"]], S[i:, F["y"]], color=SERIES[1], lw=2.0, label=tr("p.on_ground"))
        ax.scatter([S[i, F["x"]]], [S[i, F["y"]]], color=INK, s=22, zorder=5)
        ax.annotate(tr("p.touch"), (S[i, F["x"]], S[i, F["y"]]), xytext=(5, 5), textcoords="offset points",
                    color=INK2, fontsize=8)
    ax.scatter([S[0, F["x"]]], [S[0, F["y"]]], color=SERIES[2], s=22, zorder=5)
    ax.annotate(tr("p.start"), (S[0, F["x"]], S[0, F["y"]]), xytext=(5, -10), textcoords="offset points",
                color=INK2, fontsize=8)
    ax.scatter([S[-1, F["x"]]], [S[-1, F["y"]]], marker="s", color=INK, s=22, zorder=5)
    ax.annotate(tr("p.end"), (S[-1, F["x"]], S[-1, F["y"]]), xytext=(5, -10), textcoords="offset points",
                color=INK2, fontsize=8)
    ax.set_aspect("equal"); ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
    ax.set_title(tr("p.top"))
    ax.legend(loc="best")
    _save(fig, outdir / "trajectory_top.png"); files.append("trajectory_top.png")

    def series_plot(fname, title, ylabel, cols_labels, hlines=(), ylim0=False, dashed=()):
        fig, ax = plt.subplots(figsize=(7.2, 3.4))
        for k, (col, lab) in enumerate(cols_labels):
            y = -S[:, F[col[1:]]] if col.startswith("-") else S[:, F[col]]
            ax.plot(t, y, color=SERIES[k], label=lab, ls="--" if col in dashed else "-",
                    lw=2.2 if col in dashed else 1.6)
        for y, lab, color in hlines:
            ax.axhline(y, color=color, lw=1.0, ls=":")
            ax.annotate(lab, (0, y), xycoords=("axes fraction", "data"), xytext=(4, 3),
                        textcoords="offset points", color=INK2, fontsize=8)
        _vmark(ax, tg, tr("p.ground"))
        ax.set_xlabel(tr("p.time")); ax.set_ylabel(ylabel); ax.set_title(title)
        if ylim0:
            ax.set_ylim(bottom=0)
        if len(cols_labels) > 1:
            ax.legend(loc="best")
        _save(fig, outdir / fname); files.append(fname)

    series_plot("height.png", tr("p.height"), "z (m)", [("z", tr("p.com")), ("lowest_z", tr("p.lowest"))])
    series_plot("speed.png", tr("p.speed"), "m/s", [("speed", tr("p.speed_l"))], ylim0=True)
    series_plot("wall_distance.png", tr("p.wall"), "m", [("wall_dist", tr("p.wall_l"))],
                hlines=[(0.0, tr("p.wall_line"), MUTED)])
    c = sim.cfg
    series_plot("tension.png", tr("p.tension"), "N",
                [("tension", tr("p.t_obj")), ("tension_anchor", tr("p.t_anchor"))],
                hlines=[(c.rope.load_warn_fraction * c.rope.breaking_load_N, tr("p.load_warn"), STATUS["ATENÇÃO"])]
                if S[:, F["tension"]].max() > 0.3 * c.rope.load_warn_fraction * c.rope.breaking_load_N else ())
    series_plot("wound_length.png", tr("p.wound"), "m",
                [("stored_len", tr("p.stored")), ("wound_len", tr("p.contact")),
                 ("free_len", tr("p.free"))], ylim0=True, dashed=("wound_len",))
    series_plot("energy.png", tr("p.energy"), "J",
                [("e_total", tr("p.e_total")), ("w_peel", tr("p.e_peel")),
                 ("w_rope_damp", tr("p.e_damp")), ("-w_drag", tr("p.e_drag"))])

    # impactos: pico em g por evento, colorido por classe com rótulo
    ev = sim.impacts.events
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    if ev:
        for e in ev:
            col = STATUS[e["classification"]]
            mk = "o" if e["surface"] == "ground" else "^"
            ax.vlines(e["t_start"], 0, e["decel_peak_g"], color=col, lw=1.4)
            ax.scatter([e["t_start"]], [e["decel_peak_g"]], color=col, marker=mk, s=36, zorder=4,
                       edgecolors=SURFACE, linewidths=1.5)
        thr = sim.impacts.threshold
        if sim.impacts.metric == "g":
            ax.axhline(thr, color=STATUS["DANO"], ls=":", lw=1)
            ax.annotate(f"{tr('class.DANO')} ≥ {thr:g} g", (0, thr), xycoords=("axes fraction", "data"), xytext=(4, 3),
                        textcoords="offset points", color=INK2, fontsize=8)
            w = c.impact.warn_fraction * thr
            ax.axhline(w, color=STATUS["ATENÇÃO"], ls=":", lw=1)
            ax.annotate(f"{tr('class.ATENÇÃO')} ≥ {w:g} g", (0, w), xycoords=("axes fraction", "data"), xytext=(4, 3),
                        textcoords="offset points", color=INK2, fontsize=8)
        from matplotlib.lines import Line2D
        handles = [Line2D([], [], color=STATUS[k], marker="o", ls="", label=tr(f"class.{k}")) for k in STATUS] + [
            Line2D([], [], color=MUTED, marker="o", ls="", label=tr("surface.ground")),
            Line2D([], [], color=MUTED, marker="^", ls="", label=tr("surface.tower"))]
        ax.legend(handles=handles, loc="upper left", ncol=5)
    else:
        ax.text(0.5, 0.5, tr("p.no_impacts"), transform=ax.transAxes, ha="center", color=INK2)
    ax.set_ylim(bottom=0)
    ax.set_xlabel(tr("p.time")); ax.set_ylabel(tr("p.peak_g"))
    ax.set_title(tr("p.impacts"))
    _save(fig, outdir / "impacts.png"); files.append("impacts.png")
    return files


def heatmap(grid: np.ndarray, xs, ys, xlabel, ylabel, title, cbar_label, path: Path, fmt="{:.2f}"):
    """Mapa de calor sequencial (um matiz, claro→escuro) com valores anotados."""
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        "blue_seq", ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#104281", "#0d366b"])
    fig, ax = plt.subplots(figsize=(1.2 + 0.9 * len(xs), 1.2 + 0.6 * len(ys)))
    ax.grid(False)
    im = ax.imshow(grid, cmap=cmap, aspect="auto", origin="lower")
    ax.set_xticks(range(len(xs)), [str(x) for x in xs]); ax.set_yticks(range(len(ys)), [str(y) for y in ys])
    vmax = np.nanmax(grid) if np.isfinite(grid).any() else 1
    for i in range(len(ys)):
        for j in range(len(xs)):
            v = grid[i, j]
            if np.isfinite(v):
                ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=8,
                        color="#ffffff" if v > 0.55 * vmax else INK)
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.set_title(title)
    cb = fig.colorbar(im, ax=ax); cb.set_label(cbar_label)
    _save(fig, path)
