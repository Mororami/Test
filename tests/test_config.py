import pytest

from app.config import ConfigError, config_from_dict


def test_defaults():
    cfg = config_from_dict({}, env={})
    assert cfg.poll_interval_sec == 30
    assert cfg.fx.mode == "forex"
    assert cfg.alerts.pump.enabled and cfg.alerts.kimp.enabled and not cfg.alerts.change_24h.enabled
    assert not cfg.telegram.configured


def test_nested_override_and_env():
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1", "DASHBOARD_PORT": "9000"}
    cfg = config_from_dict({"alerts": {"pump": {"threshold_pct": 3}, "cooldown_min": 5},
                            "symbols": {"include": ["btc"], "aliases": {"abc": "xyz"}}}, env=env)
    assert cfg.alerts.pump.threshold_pct == 3
    assert cfg.alerts.pump.window_min == 5          # 지정하지 않은 값은 기본값 유지
    assert cfg.alerts.cooldown_min == 5
    assert cfg.symbols.include == ["BTC"]
    assert cfg.symbols.aliases == {"ABC": "XYZ"}
    assert cfg.telegram.configured
    assert cfg.dashboard.port == 9000


@pytest.mark.parametrize("data", [
    {"nope": 1},
    {"alerts": {"pump": {"threshold": 1}}},
    {"fx": {"mode": "eur"}},
    {"poll_interval_sec": 0},
    {"alerts": {"pump": {"window_min": 120}}, "history_max_age_sec": 60},
    {"telegram": {"bot_token": "x"}},
    {"symbols": {"mismatch_kimp_pct": 0}},
])
def test_invalid(data):
    with pytest.raises(ConfigError):
        config_from_dict(data, env={})
