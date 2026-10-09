"""Contrato de configuração: YAML validado por Pydantic, presets e overrides.

Todos os números físicos padrão vivem em ``configs/default.yaml``. Este módulo
só define tipos, faixas válidas e regras de resolução (comprimento ``auto``,
presets de vento/solo, impulso ↔ velocidade).
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .i18n import t

PKG_DIR = Path(__file__).resolve().parent
REPO_DIR = PKG_DIR.parent
CONFIG_DIR = REPO_DIR / "configs"
DEFAULT_CONFIG = CONFIG_DIR / "default.yaml"
PRESET_DIR = CONFIG_DIR / "presets"

G = 9.81  # m/s², também usado em opt.gravity (fixo; não é parâmetro de cenário)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Tower(_Strict):
    height_m: float = Field(gt=1.0, le=500.0)
    diameter_m: float = Field(gt=0.2, le=50.0)
    wall_friction: float = Field(ge=0.0, le=2.0)


class Rope(_Strict):
    model: str
    length_m: float | Literal["auto"]
    diameter_m: float = Field(gt=0.001, le=0.1)
    linear_density_kg_m: float = Field(ge=0.0, le=5.0)
    element_length_m: float = Field(gt=0.005, le=10.0)
    bend_E_pa: Optional[float] = None
    twist_G_pa: Optional[float] = None
    axial_EA_N: Optional[float] = None
    axial_damping_ratio: float = Field(ge=0.0, le=2.0)
    wall_friction: float = Field(ge=0.0, le=2.0)
    ground_friction: float = Field(ge=0.0, le=2.0)
    wind_drag_Cd_normal: float = Field(ge=0.0, le=5.0)
    wind_drag_Cd_tangent: float = Field(ge=0.0, le=1.0)
    winding_pitch_factor: float = Field(ge=1.0, le=100.0)
    winding_handedness: Literal["ccw", "cw"]
    anchor_below_top_m: float = Field(gt=0.0)
    self_collision: bool = False
    breaking_load_N: float = Field(gt=0.0)
    load_warn_fraction: float = Field(gt=0.0, le=1.0)

    @field_validator("model")
    @classmethod
    def _model_ok(cls, v: str) -> str:
        if v == "wrap_tether":
            return v
        if v == "chain":
            raise ValueError(t("cfg.chain"))
        if v == "cable_plugin":
            raise ValueError(t("cfg.cable"))
        raise ValueError(t("cfg.model_unknown", v=v))

    @field_validator("length_m")
    @classmethod
    def _len_ok(cls, v):
        if v != "auto" and not (1.0 <= float(v) <= 2000.0):
            raise ValueError(t("cfg.length_range"))
        return v

    @field_validator("axial_EA_N")
    @classmethod
    def _ea_ok(cls, v):
        if v is None:
            raise ValueError(t("cfg.ea_null"))
        if not (1e2 <= v <= 1e8):
            raise ValueError(t("cfg.ea_range"))
        return v


class ObjectCfg(_Strict):
    type: Literal["sandbag", "mannequin"]
    mass_kg: float = Field(gt=1.0, le=500.0)
    height_m: float = Field(gt=0.2, le=3.0)
    radius_m: float = Field(gt=0.03, le=1.0)
    attach_height_fraction: float = Field(ge=0.0, le=1.0)
    start_clearance_m: float = Field(ge=0.0, le=20.0)
    drag_CdA_m2: float = Field(ge=0.0, le=5.0)
    geom_friction: float = Field(ge=0.0, le=2.0)


class Launch(_Strict):
    mode: Literal["velocity", "impulse"]
    speed_ms: Optional[float] = Field(default=None, ge=0.0, le=40.0)
    impulse_Ns: Optional[float] = Field(default=None, ge=0.0, le=20000.0)
    azimuth_deg: float = Field(ge=-180.0, le=180.0)
    elevation_deg: float = Field(ge=-89.0, le=89.0)
    duration_ms: float = Field(ge=0.0, le=2000.0)

    @model_validator(mode="after")
    def _mode_value(self):
        if self.mode == "velocity" and self.speed_ms is None:
            raise ValueError(t("cfg.need_speed"))
        if self.mode == "impulse" and self.impulse_Ns is None:
            raise ValueError(t("cfg.need_impulse"))
        return self


class Air(_Strict):
    enabled: bool
    density_kg_m3: float = Field(ge=0.0, le=2.0)


class Wind(_Strict):
    enabled: bool
    preset: Optional[str] = None
    speed_mean_ms: float = Field(ge=0.0, le=60.0)
    direction_deg: float = Field(ge=-360.0, le=360.0)
    gust_std_ms: float = Field(ge=0.0, le=30.0)
    correlation_time_s: float = Field(gt=0.0, le=600.0)
    shear_exponent: float = Field(ge=0.0, le=1.0)
    reference_height_m: float = Field(gt=0.0, le=500.0)
    seed: int = Field(ge=0)
    presets: dict[str, float]


class Ground(_Strict):
    preset: Optional[str] = None
    friction_slide: float = Field(ge=0.0, le=2.0)
    friction_torsional: float = Field(ge=0.0, le=1.0)
    friction_rolling: float = Field(ge=0.0, le=1.0)
    presets: dict[str, float]
    size_m: float = Field(gt=10.0, le=10000.0)


class Contact(_Strict):
    solref: list[float] = Field(min_length=2, max_length=2)
    solimp: list[float] = Field(min_length=3, max_length=5)
    cone: Literal["elliptic", "pyramidal"]
    impratio: float = Field(ge=1.0, le=100.0)


class Impact(_Strict):
    damage_threshold_g: Optional[float] = Field(default=None, gt=0.0)
    damage_threshold_N: Optional[float] = Field(default=None, gt=0.0)
    filter_window_ms: float = Field(gt=0.0, le=100.0)
    warn_fraction: float = Field(gt=0.0, lt=1.0)
    merge_gap_ms: float = Field(ge=0.0, le=500.0)
    structure_hit_speed_ms: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _one_threshold(self):
        if self.damage_threshold_g is None and self.damage_threshold_N is None:
            raise ValueError(t("cfg.need_threshold"))
        return self


class Solver(_Strict):
    timestep_s: float = Field(gt=1e-6, le=0.01)
    integrator: Literal["implicitfast", "implicit", "Euler", "RK4"]
    iterations: int = Field(ge=1, le=1000)
    max_time_s: float = Field(gt=0.0, le=3600.0)
    rest_speed_ms: float = Field(gt=0.0)
    rest_hold_s: float = Field(ge=0.0)
    rewind_threshold_turns: float = Field(gt=0.0)
    stop_on_structure_hit: bool
    output_hz: float = Field(gt=0.0, le=5000.0)


class UI(_Strict):
    render_hz: float = Field(gt=0.0, le=60.0)
    playback_factor: float = Field(ge=0.1, le=4.0)
    width: int = Field(ge=160, le=1920)
    height: int = Field(ge=120, le=1080)
    jpeg_quality: int = Field(ge=30, le=95)
    helix_visual_pitch_scale: float = Field(ge=1.0, le=200.0)
    rope_visual_radius_m: float = Field(gt=0.0, le=1.0)
    camera: Literal["free", "side", "follow"]


class SimConfig(_Strict):
    name: str = "default"
    tower: Tower
    rope: Rope
    object: ObjectCfg
    launch: Launch
    air: Air
    wind: Wind
    ground: Ground
    contact: Contact
    impact: Impact
    solver: Solver
    ui: UI

    @model_validator(mode="after")
    def _geometry(self):
        if self.rope.anchor_below_top_m >= self.tower.height_m:
            raise ValueError(t("cfg.anchor"))
        if self.wind.preset is not None and self.wind.preset not in self.wind.presets:
            raise ValueError(t("cfg.wind_preset", v=self.wind.preset))
        if self.ground.preset is not None and self.ground.preset not in self.ground.presets:
            raise ValueError(t("cfg.ground_preset", v=self.ground.preset))
        return self


# ---------------------------------------------------------------- utilidades

def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "presets":
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def parse_scalar(text: str) -> Any:
    """Converte o valor textual de ``--set`` com regras YAML (número, bool, null, lista)."""
    return yaml.safe_load(text)


def set_path(d: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            raise KeyError(f"caminho inválido em override: {dotted}")
        cur = cur[k]
    if keys[-1] not in cur and keys[0] not in ("name",):
        raise KeyError(f"parâmetro desconhecido em override: {dotted}")
    cur[keys[-1]] = value


def apply_overrides(raw: dict, sets: list[str] | None) -> dict:
    out = copy.deepcopy(raw)
    for item in sets or []:
        if "=" not in item:
            raise ValueError(f"override deve ter forma caminho=valor: {item!r}")
        path, val = item.split("=", 1)
        set_path(out, path.strip(), parse_scalar(val.strip()))
    return out


def list_presets() -> list[str]:
    return sorted(p.stem for p in PRESET_DIR.glob("*.yaml"))


def load_raw(path: str | Path | None = None, preset: str | None = None,
             sets: list[str] | None = None, extra: dict | None = None) -> dict:
    base = yaml.safe_load(Path(DEFAULT_CONFIG).read_text())
    if path is not None and Path(path).resolve() != DEFAULT_CONFIG.resolve():
        base = deep_merge(base, yaml.safe_load(Path(path).read_text()) or {})
    if preset:
        pf = PRESET_DIR / f"{preset}.yaml"
        if not pf.exists():
            raise FileNotFoundError(f"preset inexistente: {preset} (disponíveis: {list_presets()})")
        pdata = yaml.safe_load(pf.read_text()) or {}
        pdata.pop("description", None)
        pdata.pop("description_en", None)
        base = deep_merge(base, pdata)
        base.setdefault("name", preset)
        if base.get("name") == "default":
            base["name"] = preset
    if extra:
        base = deep_merge(base, extra)
    return apply_overrides(base, sets)


def load_config(path: str | Path | None = None, preset: str | None = None,
                sets: list[str] | None = None, extra: dict | None = None) -> SimConfig:
    return SimConfig.model_validate(load_raw(path, preset, sets, extra))


def preset_description(name: str) -> str:
    from .i18n import get_lang
    data = yaml.safe_load((PRESET_DIR / f"{name}.yaml").read_text()) or {}
    if get_lang() == "en" and data.get("description_en"):
        return str(data["description_en"])
    return str(data.get("description", ""))


# --------------------------------------------------------- resolução derivada

def auto_rope_length(H: float, v0: float = 0.0, g: float = G) -> dict:
    """Estimativa original: v = sqrt(2gH + v0²), r_min = v·sqrt(H/g), L = sqrt(r_min² + H²)."""
    v = math.sqrt(2 * g * H + v0 ** 2)
    r_min = v * math.sqrt(H / g)
    L = math.sqrt(r_min ** 2 + H ** 2)
    return dict(v_ms=v, r_min_m=r_min, L_m=L, H_m=H, v0_ms=v0,
                formula="v = sqrt(2 g H + v0^2); r_min = v sqrt(H/g); L = sqrt(r_min^2 + H^2)")


def launch_speed(cfg: SimConfig) -> float:
    if cfg.launch.mode == "velocity":
        return float(cfg.launch.speed_ms)
    return float(cfg.launch.impulse_Ns) / cfg.object.mass_kg


def launch_impulse(cfg: SimConfig) -> float:
    if cfg.launch.mode == "impulse":
        return float(cfg.launch.impulse_Ns)
    return float(cfg.launch.speed_ms) * cfg.object.mass_kg


def resolve(cfg: SimConfig) -> tuple[SimConfig, dict]:
    """Aplica presets e ``auto``; devolve configuração resolvida e notas de resolução."""
    c = cfg.model_copy(deep=True)
    notes: dict[str, Any] = {}
    if c.wind.preset is not None:
        c.wind.speed_mean_ms = float(c.wind.presets[c.wind.preset])
        notes["wind_preset"] = f"{c.wind.preset}: speed_mean_ms={c.wind.speed_mean_ms}"
    if c.ground.preset is not None:
        c.ground.friction_slide = float(c.ground.presets[c.ground.preset])
        notes["ground_preset"] = f"{c.ground.preset}: friction_slide={c.ground.friction_slide}"
    v0 = launch_speed(c)
    est = auto_rope_length(c.tower.height_m, v0)
    notes["rope_length_estimate"] = est
    if c.rope.length_m == "auto":
        c.rope.length_m = round(est["L_m"], 3)
        notes["rope_length_source"] = t("cfg.len_auto_note")
    else:
        notes["rope_length_source"] = t("cfg.len_manual")
    notes["launch"] = dict(speed_ms=v0, impulse_Ns=launch_impulse(c),
                           delta_v_from_impulse="J = m Δv")
    notes["inapplicable_params"] = {
        "rope.bend_E_pa": t("inap.bend"),
        "rope.twist_G_pa": t("inap.twist"),
        "rope.self_collision": t("inap.self"),
        "rope.ground_friction": t("inap.ground"),
    }
    return c, notes


def to_plain(cfg: SimConfig) -> dict:
    return cfg.model_dump(mode="json")
