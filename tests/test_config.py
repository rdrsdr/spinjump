"""Contrato de configuração: YAML validado, presets, overrides, impulso ↔ velocidade."""
import pytest
import yaml

from spinjump.config import (DEFAULT_CONFIG, SimConfig, auto_rope_length, list_presets, load_config,
                                resolve, to_plain)
from spinjump.cli import main as cli_main


def test_default_valid_and_rope_model():
    cfg = load_config()
    assert cfg.rope.model == "wrap_tether"
    assert cfg.rope.length_m == "auto"


@pytest.mark.parametrize("model", ["chain", "cable_plugin", "xyz"])
def test_rejected_rope_models(model):
    with pytest.raises(ValueError):
        load_config(sets=[f"rope.model={model}"])


def test_inextensible_rejected_with_explanation():
    with pytest.raises(ValueError, match="inextens"):
        load_config(sets=["rope.axial_EA_N=null"])


def test_unknown_parameter_rejected():
    with pytest.raises(KeyError):
        load_config(sets=["rope.nonexistent=1"])
    raw = yaml.safe_load(DEFAULT_CONFIG.read_text())
    raw["rope"]["typo_field"] = 1
    with pytest.raises(ValueError):
        SimConfig.model_validate(raw)


def test_overrides_repeatable_and_typed():
    cfg = load_config(sets=["launch.azimuth_deg=-30", "launch.azimuth_deg=45", "wind.enabled=false",
                            "contact.solref=[0.01, 1.0]"])
    assert cfg.launch.azimuth_deg == 45.0
    assert cfg.wind.enabled is False
    assert cfg.contact.solref == [0.01, 1.0]


def test_impulse_mode_J_equals_m_dv():
    cfg = load_config(sets=["launch.mode=impulse", "launch.impulse_Ns=400", "object.mass_kg=80"])
    _, notes = resolve(cfg)
    assert notes["launch"]["speed_ms"] == pytest.approx(5.0)
    with pytest.raises(ValueError):
        load_config(sets=["launch.mode=impulse", "launch.impulse_Ns=null"])


def test_auto_length_formula():
    est = auto_rope_length(50.0, 0.0)
    assert est["L_m"] == pytest.approx(86.6, abs=0.05)
    cfg, notes = resolve(load_config())
    assert cfg.rope.length_m == pytest.approx(auto_rope_length(50.0, notes["launch"]["speed_ms"])["L_m"], abs=1e-3)


def test_presets_and_wind_ground_presets():
    assert len(list_presets()) >= 5
    for p in list_presets():
        load_config(preset=p)
    cfg, _ = resolve(load_config(sets=["wind.preset=breeze", "ground.preset=ice"]))
    assert cfg.wind.speed_mean_ms == 5 and cfg.ground.friction_slide == 0.1


def test_ui_and_cli_reach_same_model():
    """Formulário (dict mesclado) e CLI (--set) produzem a mesma configuração validada."""
    form = {"launch": {"mode": "impulse", "impulse_Ns": 320.0, "speed_ms": None, "azimuth_deg": 90.0},
            "rope": {"length_m": 90.0}, "wind": {"enabled": False}}
    a = load_config(extra=form)
    b = load_config(sets=["launch.mode=impulse", "launch.impulse_Ns=320", "launch.speed_ms=null",
                          "launch.azimuth_deg=90", "rope.length_m=90", "wind.enabled=false"])
    assert to_plain(a) == to_plain(b)


def test_cli_rope_length(capsys):
    assert cli_main(["rope-length", "--height", "50", "--v0", "0"]) == 0
    out = capsys.readouterr().out
    assert "L = 86.6" in out
