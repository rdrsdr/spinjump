"""Renderização offscreen no servidor (OSMesa por padrão; EGL opcional).

A cena é desenhada a partir de um ``FrameState`` extraído do estado físico:
qpos do objeto e as polilinhas da corda calculadas pelo mesmo ``WrapTether``
que produz as forças. Nenhum texto é desenhado sobre a imagem; rótulos e
avisos ficam no painel HTML, fora da cena.

O renderizador roda num processo separado (``RenderWorker``) para não
disputar o GIL com o laço físico.
"""
from __future__ import annotations

import io
import math
import multiprocessing as mp
import os
import threading
from dataclasses import dataclass, field

import numpy as np

ROPE_TAUT = (0.95, 0.80, 0.10, 1.0)
ROPE_SLACK = (0.45, 0.75, 1.0, 1.0)
ROPE_STORED = (0.85, 0.45, 0.10, 1.0)
ROPE_GEODESIC = (0.95, 0.60, 0.15, 1.0)
MARK_ANCHOR = (0.9, 0.1, 0.1, 1.0)
MARK_DEPART = (0.1, 0.9, 0.3, 1.0)


@dataclass
class FrameState:
    t: float
    qpos: np.ndarray
    stored: np.ndarray            # hélice armazenada (passo possivelmente ampliado, apenas visual)
    geodesic: np.ndarray
    free: np.ndarray
    anchor: np.ndarray
    depart: np.ndarray
    slack: bool
    com: np.ndarray
    radial: np.ndarray            # direção radial horizontal do objeto (câmera de acompanhamento)


@dataclass
class CameraState:
    mode: str = "free"            # free | side | follow
    azimuth: float = -60.0
    elevation: float = -12.0
    distance: float = 95.0
    lookat: list = field(default_factory=lambda: [0.0, 0.0, 22.0])


def frame_state(sim, pitch_scale: float) -> FrameState:
    rope = sim.rope
    s = rope.s
    com = sim.d.xipos[sim.b.body_id].copy()
    rad = np.array([com[0], com[1], 0.0])
    n = np.linalg.norm(rad)
    rad = rad / n if n > 1e-9 else np.array([1.0, 0.0, 0.0])
    return FrameState(
        t=float(sim.d.time), qpos=sim.d.qpos.copy(),
        stored=rope.stored_polyline(pitch_scale, pts_per_turn=36).astype(np.float32),
        geodesic=rope.geodesic_polyline().astype(np.float32),
        free=rope.free_polyline().astype(np.float32),
        anchor=rope.stored_point(0.0), depart=s.D.copy(), slack=bool(s.slack), com=com, radial=rad)


class SceneRenderer:
    def __init__(self, xml: str, width: int, height: int, rope_radius: float, tower_height: float):
        import mujoco
        self.mj = mujoco
        self.m = mujoco.MjModel.from_xml_string(xml)
        # malhas leves: o custo do OSMesa (CPU) cresce com triângulos e compete com a física
        self.m.vis.quality.offsamples = 0
        self.m.vis.quality.shadowsize = 0
        self.m.vis.quality.numslices = 16
        self.m.vis.quality.numstacks = 6
        self.d = mujoco.MjData(self.m)
        self.r = mujoco.Renderer(self.m, height, width, max_geom=4000)
        self.r.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
        self.r.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = 0
        self.cam = mujoco.MjvCamera()
        self.rr = rope_radius
        self.H = tower_height
        self._follow_az = None

    def _set_camera(self, cs: CameraState, fs: FrameState):
        cam = self.cam
        if cs.mode == "side":
            cam.lookat[:] = (0.0, 0.0, self.H * 0.45)
            cam.distance = self.H * 2.0
            cam.azimuth = cs.azimuth
            cam.elevation = -8.0
        elif cs.mode == "follow":
            cam.lookat[:] = fs.com
            # acompanha de fora para dentro, olhando a torre por trás do objeto
            az = math.degrees(math.atan2(fs.radial[1], fs.radial[0])) + 35.0
            if self._follow_az is None:
                self._follow_az = az
            # suavização angular
            dlt = (az - self._follow_az + 180.0) % 360.0 - 180.0
            self._follow_az += 0.25 * dlt
            cam.azimuth = self._follow_az
            cam.elevation = -18.0
            cam.distance = 8.0
        else:
            cam.lookat[:] = cs.lookat
            cam.distance = cs.distance
            cam.azimuth = cs.azimuth
            cam.elevation = cs.elevation

    def _poly(self, scn, pts: np.ndarray, rgba, radius: float):
        mj = self.mj
        n = len(pts)
        for i in range(n - 1):
            if scn.ngeom >= scn.maxgeom - 2:
                return
            g = scn.geoms[scn.ngeom]
            mj.mjv_initGeom(g, mj.mjtGeom.mjGEOM_CAPSULE, np.zeros(3), np.zeros(3), np.zeros(9),
                            np.asarray(rgba, dtype=np.float32))
            mj.mjv_connector(g, mj.mjtGeom.mjGEOM_CAPSULE, radius,
                             pts[i].astype(np.float64), pts[i + 1].astype(np.float64))
            scn.ngeom += 1

    def _sphere(self, scn, pos, r, rgba):
        mj = self.mj
        if scn.ngeom >= scn.maxgeom:
            return
        g = scn.geoms[scn.ngeom]
        mj.mjv_initGeom(g, mj.mjtGeom.mjGEOM_SPHERE, np.array([r, r, r]), np.asarray(pos, dtype=np.float64),
                        np.eye(3).flatten(), np.asarray(rgba, dtype=np.float32))
        scn.ngeom += 1

    def render(self, fs: FrameState, cs: CameraState) -> np.ndarray:
        mj = self.mj
        self.d.qpos[:] = fs.qpos
        mj.mj_kinematics(self.m, self.d)
        self._set_camera(cs, fs)
        self.r.update_scene(self.d, self.cam)
        scn = self.r.scene
        # espessura visual cresce com a distância da câmera para manter a corda legível
        dist = float(np.linalg.norm(np.asarray(self.cam.lookat) - fs.com)) + self.cam.distance
        rr = max(self.rr, 0.0012 * self.cam.distance)
        self._poly(scn, fs.stored, ROPE_STORED, rr * 0.8)
        self._poly(scn, fs.geodesic, ROPE_GEODESIC, rr)
        self._poly(scn, fs.free, ROPE_SLACK if fs.slack else ROPE_TAUT, rr)
        self._sphere(scn, fs.anchor, rr * 2.2, MARK_ANCHOR)
        self._sphere(scn, fs.depart, rr * 2.2, MARK_DEPART)
        del dist
        return self.r.render()


def encode_jpeg(img: np.ndarray, quality: int) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(img).save(b, "JPEG", quality=quality)
    return b.getvalue()


# --------------------------------------------------------- processo dedicado

def _worker_main(conn, xml, width, height, rope_radius, tower_height, quality, gl):
    if gl:
        os.environ["MUJOCO_GL"] = gl
        os.environ["PYOPENGL_PLATFORM"] = gl
    try:
        sr = SceneRenderer(xml, width, height, rope_radius, tower_height)
        conn.send(("ready", None))
    except Exception as e:  # erro de contexto GL etc.
        conn.send(("error", repr(e)))
        return
    while True:
        msg = conn.recv()
        if msg is None:
            break
        fs, cs = msg
        try:
            img = sr.render(fs, cs)
            conn.send(("frame", encode_jpeg(img, quality)))
        except Exception as e:
            conn.send(("error", repr(e)))


class RenderWorker:
    """Processo de renderização: recebe (FrameState, CameraState) e devolve JPEG."""

    def __init__(self, xml: str, width: int, height: int, rope_radius: float, tower_height: float,
                 quality: int):
        ctx = mp.get_context("spawn")
        self.conn, child = ctx.Pipe()
        gl = os.environ.get("MUJOCO_GL", "osmesa")
        self.proc = ctx.Process(target=_worker_main, daemon=True,
                                args=(child, xml, width, height, rope_radius, tower_height, quality, gl))
        self.proc.start()
        kind, payload = self.conn.recv()
        if kind != "ready":
            raise RuntimeError(f"falha ao iniciar renderizador: {payload}")
        self.lock = threading.Lock()

    def render(self, fs: FrameState, cs: CameraState) -> bytes:
        with self.lock:
            self.conn.send((fs, cs))
            kind, payload = self.conn.recv()
        if kind != "frame":
            raise RuntimeError(payload)
        return payload

    def close(self):
        try:
            self.conn.send(None)
        except Exception:
            pass
        self.proc.join(timeout=2)
        if self.proc.is_alive():
            self.proc.kill()
