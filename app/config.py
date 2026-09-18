"""설정 로딩.

- 비밀값(Telegram 토큰 등)은 .env / 환경 변수에서 읽는다.
- 동작 파라미터(임계치, 주기 등)는 config.yaml 에서 읽는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping, get_type_hints

import yaml
from dotenv import load_dotenv

DEFAULT_CONFIG_PATH = Path("config.yaml")
FX_MODES = ("forex", "usdt")


@dataclass
class PumpAlertConfig:
    enabled: bool = True
    window_min: float = 5.0           # 이 시간(분) 동안의 상승률을 본다
    threshold_pct: float = 5.0        # 상승률이 이 값(%) 이상이면 알림
    min_quote_volume_thb: float = 0   # Bitkub 24h 거래대금(THB) 최소값


@dataclass
class Change24hAlertConfig:
    enabled: bool = False
    threshold_pct: float = 20.0       # Bitkub 24h 변동률이 이 값(%) 이상이면 알림
    min_quote_volume_thb: float = 0


@dataclass
class KimpAlertConfig:
    enabled: bool = True
    threshold_pct: float = 5.0        # |김프| 가 이 값(%) 이상이면 알림
    min_quote_volume_thb: float = 0
    min_quote_volume_krw: float = 0


@dataclass
class AlertConfig:
    pump: PumpAlertConfig = field(default_factory=PumpAlertConfig)
    change_24h: Change24hAlertConfig = field(default_factory=Change24hAlertConfig)
    kimp: KimpAlertConfig = field(default_factory=KimpAlertConfig)
    cooldown_min: float = 30.0        # 같은 코인·같은 종류 알림의 재발송 최소 간격
    startup_message: bool = True      # 봇 시작 시 Telegram 으로 시작 알림


@dataclass
class FxConfig:
    mode: str = "forex"               # forex: 외환 환율 / usdt: 양 거래소 USDT 가격에서 역산
    refresh_sec: float = 3600
    override_thb_krw: float | None = None   # 수동 고정 환율 (예: 41.5)


@dataclass
class SymbolConfig:
    include: list[str] = field(default_factory=list)   # 비어 있으면 Bitkub 전체
    exclude: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)  # Bitkub 심볼 -> Bithumb 심볼
    mismatch_kimp_pct: float = 50.0   # |김프| 가 이 값 이상이면 다른 코인으로 의심해 알림·통계에서 제외


@dataclass
class DashboardConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    kimp_highlight_pct: float = 3.0   # |김프| 가 이 값 이상이면 대시보드에서 강조


@dataclass
class TelegramConfig:
    bot_token: str | None = None
    chat_id: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass
class AppConfig:
    poll_interval_sec: float = 30
    history_max_age_sec: float = 3600
    fx: FxConfig = field(default_factory=FxConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    symbols: SymbolConfig = field(default_factory=SymbolConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


class ConfigError(ValueError):
    pass


def _build(cls, data: Mapping[str, Any]):
    """dataclass 필드 이름에 맞춰 (중첩 포함) 인스턴스를 만든다. 모르는 키는 오류."""
    if not isinstance(data, Mapping):
        raise ConfigError(f"'{cls.__name__}' 설정은 키-값 매핑이어야 합니다")
    hints = get_type_hints(cls)
    names = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - names)
    if unknown:
        raise ConfigError(f"{cls.__name__} 에 알 수 없는 설정 키: {unknown}")
    kwargs: dict[str, Any] = {}
    for name, value in data.items():
        hint = hints[name]
        if isinstance(hint, type) and is_dataclass(hint):
            if value is None:
                continue
            value = _build(hint, value)
        kwargs[name] = value
    return cls(**kwargs)


def config_from_dict(data: Mapping[str, Any] | None, env: Mapping[str, str] | None = None) -> AppConfig:
    data = dict(data or {})
    env = os.environ if env is None else env
    if "telegram" in data:
        raise ConfigError("Telegram 토큰/채팅 ID 는 config.yaml 이 아니라 .env 에 넣어 주세요")

    cfg = _build(AppConfig, data)
    cfg.telegram = TelegramConfig(
        bot_token=env.get("TELEGRAM_BOT_TOKEN") or None,
        chat_id=env.get("TELEGRAM_CHAT_ID") or None,
    )
    if env.get("DASHBOARD_HOST"):
        cfg.dashboard.host = env["DASHBOARD_HOST"]
    if env.get("DASHBOARD_PORT"):
        cfg.dashboard.port = int(env["DASHBOARD_PORT"])

    cfg.symbols.include = [s.upper() for s in cfg.symbols.include]
    cfg.symbols.exclude = [s.upper() for s in cfg.symbols.exclude]
    cfg.symbols.aliases = {k.upper(): v.upper() for k, v in cfg.symbols.aliases.items()}
    _validate(cfg)
    return cfg


def _validate(cfg: AppConfig) -> None:
    if cfg.poll_interval_sec <= 0:
        raise ConfigError("poll_interval_sec 는 0보다 커야 합니다")
    if cfg.fx.mode not in FX_MODES:
        raise ConfigError(f"fx.mode 는 {FX_MODES} 중 하나여야 합니다")
    if cfg.fx.override_thb_krw is not None and cfg.fx.override_thb_krw <= 0:
        raise ConfigError("fx.override_thb_krw 는 0보다 커야 합니다")
    if cfg.alerts.pump.window_min <= 0:
        raise ConfigError("alerts.pump.window_min 은 0보다 커야 합니다")
    for name, threshold in (
        ("alerts.pump", cfg.alerts.pump.threshold_pct),
        ("alerts.change_24h", cfg.alerts.change_24h.threshold_pct),
        ("alerts.kimp", cfg.alerts.kimp.threshold_pct),
    ):
        if threshold <= 0:
            raise ConfigError(f"{name}.threshold_pct 는 0보다 커야 합니다")
    if cfg.symbols.mismatch_kimp_pct <= 0:
        raise ConfigError("symbols.mismatch_kimp_pct 는 0보다 커야 합니다")
    if cfg.history_max_age_sec < cfg.alerts.pump.window_min * 60:
        raise ConfigError("history_max_age_sec 는 alerts.pump.window_min(분)보다 길어야 합니다")


def load_config(path: str | os.PathLike[str] | None = None) -> AppConfig:
    """`.env` 를 읽은 뒤 config.yaml(없으면 기본값)로 AppConfig 를 만든다."""
    load_dotenv()
    config_path = Path(path or os.environ.get("KIMP_CONFIG") or DEFAULT_CONFIG_PATH)
    data: Any = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ConfigError(f"{config_path} 최상위는 키-값 매핑이어야 합니다")
    return config_from_dict(data)
