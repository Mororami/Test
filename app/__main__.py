"""실행 진입점: python -m app <command>"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

import httpx

from app.config import AppConfig, ConfigError, load_config
from app.fmt import fmt_num, fmt_pct
from app.models import Snapshot
from app.notifier import TelegramError, TelegramNotifier

log = logging.getLogger("app")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app", description="Bitkub 시세 알람 봇 + 김프 대시보드")
    p.add_argument("-c", "--config", help="config.yaml 경로 (기본: ./config.yaml 또는 $KIMP_CONFIG)")
    p.add_argument("-v", "--verbose", action="store_true", help="디버그 로그")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("bot", help="시세 수집 + Telegram 알람")
    sub.add_parser("dashboard", help="시세 수집 + 웹 대시보드 (알람 전송 없음)")
    sub.add_parser("all", help="시세 수집 + Telegram 알람 + 웹 대시보드 (한 프로세스)")
    once = sub.add_parser("once", help="한 번 수집해서 콘솔에 김프 표 출력")
    once.add_argument("-n", "--top", type=int, default=30, help="표시할 코인 수")
    exp = sub.add_parser("export", help="한 번 수집해서 서버 없이 열 수 있는 HTML 파일로 저장")
    exp.add_argument("-o", "--output", default="kimp.html", help="저장할 파일 (기본: kimp.html)")
    sub.add_parser("test-telegram", help="Telegram 설정 확인용 메시지 전송")
    sub.add_parser("chat-id", help="봇이 받은 메시지에서 chat_id 찾기")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2

    try:
        if args.command == "bot":
            return asyncio.run(run_bot(cfg))
        if args.command == "dashboard":
            return run_server(cfg, with_alerts=False)
        if args.command == "all":
            return run_server(cfg, with_alerts=True)
        if args.command == "once":
            return asyncio.run(run_once(cfg, args.top))
        if args.command == "export":
            return asyncio.run(run_export(cfg, args.output))
        if args.command == "test-telegram":
            return asyncio.run(test_telegram(cfg))
        if args.command == "chat-id":
            return asyncio.run(find_chat_id(cfg))
    except KeyboardInterrupt:
        pass
    return 0


async def run_bot(cfg: AppConfig) -> int:
    from app.collector import Collector

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    async with Collector(cfg, alerts_enabled=True) as collector:
        log.info("알람 봇 시작 (수집 주기 %gs, Telegram %s)", cfg.poll_interval_sec,
                 "설정됨" if cfg.telegram.configured else "미설정 → 콘솔 출력")
        await collector.run(stop)
    return 0


def run_server(cfg: AppConfig, *, with_alerts: bool) -> int:
    import uvicorn

    from app.collector import Collector
    from app.dashboard import create_app

    collector = Collector(cfg, alerts_enabled=with_alerts)
    app = create_app(collector, cfg)
    log.info("대시보드: http://%s:%d  (알람 %s)", cfg.dashboard.host, cfg.dashboard.port,
             "켜짐" if with_alerts else "꺼짐")
    uvicorn.run(app, host=cfg.dashboard.host, port=cfg.dashboard.port, log_level="info")
    return 0


async def run_once(cfg: AppConfig, top: int) -> int:
    from app.collector import Collector

    async with Collector(cfg) as collector:
        snapshot = await collector.poll_once()
    if snapshot is None:
        print(f"수집 실패: {collector.last_error}", file=sys.stderr)
        return 1
    print(render_table(snapshot, top))
    return 0


async def run_export(cfg: AppConfig, output: str) -> int:
    from app.collector import Collector
    from app.export import render_standalone

    async with Collector(cfg) as collector:
        snapshot = await collector.poll_once()
    if snapshot is None:
        print(f"수집 실패: {collector.last_error}", file=sys.stderr)
        return 1
    path = Path(output)
    path.write_text(render_standalone(snapshot, cfg.dashboard.kimp_highlight_pct), encoding="utf-8")
    print(f"{path} 저장 ({snapshot.stats.matched_count}개 비교, 환율 {snapshot.rate_used.thb_krw:.3f})")
    return 0


def render_table(snap: Snapshot, top: int) -> str:
    matched = sorted((r for r in snap.rows if r.kimp_pct is not None),
                     key=lambda r: r.kimp_pct, reverse=True)  # type: ignore[arg-type,return-value]
    implied = "-" if snap.usdt_implied_thb_krw is None else f"{snap.usdt_implied_thb_krw:.4f}"
    s = snap.stats
    lines = [
        f"환율 1 THB = {snap.rate_used.thb_krw:.4f} KRW ({snap.rate_used.source}"
        f"{', ' + snap.rate_used.as_of if snap.rate_used.as_of else ''}) | USDT 내재환율 {implied}",
        f"Bitkub {s.bitkub_count} / Bithumb {s.bithumb_count} / 비교 가능 {s.matched_count}"
        f" | 김프 중간값 {fmt_pct(s.median_kimp_pct)}",
        "",
    ]
    header = f"{'Coin':<8}{'Bitkub THB':>16}{'Bitkub KRW':>16}{'Bithumb KRW':>16}{'Kimp':>9}{'24h BK':>9}{'24h BH':>9}"
    lines += [header, "-" * len(header)]
    for r in matched[:top]:
        lines.append(f"{r.symbol:<8}{fmt_num(r.bitkub_thb):>16}{fmt_num(r.bitkub_krw):>16}"
                     f"{fmt_num(r.bithumb_krw):>16}{fmt_pct(r.kimp_pct):>9}"
                     f"{fmt_pct(r.bitkub_change_24h_pct):>9}{fmt_pct(r.bithumb_change_24h_pct):>9}")
    if len(matched) > top:
        lines.append(f"... 외 {len(matched) - top}개")
    return "\n".join(lines)


async def test_telegram(cfg: AppConfig) -> int:
    if not cfg.telegram.configured:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 .env 에 없습니다", file=sys.stderr)
        return 2
    async with httpx.AsyncClient(timeout=15) as client:
        tg = TelegramNotifier(cfg.telegram.bot_token, cfg.telegram.chat_id, client)  # type: ignore[arg-type]
        try:
            me = await tg.get_me()
            print(f"봇: @{me.get('username')} (id {me.get('id')})")
            await tg.send("✅ <b>Bitkub 시세 알람 봇</b> 연결 테스트 성공")
        except (TelegramError, httpx.HTTPError) as exc:
            print(f"실패: {exc}", file=sys.stderr)
            return 1
    print(f"chat_id {cfg.telegram.chat_id} 로 테스트 메시지를 보냈습니다")
    return 0


async def find_chat_id(cfg: AppConfig) -> int:
    if not cfg.telegram.bot_token:
        print("TELEGRAM_BOT_TOKEN 이 .env 에 없습니다", file=sys.stderr)
        return 2
    async with httpx.AsyncClient(timeout=15) as client:
        tg = TelegramNotifier(cfg.telegram.bot_token, "", client)
        try:
            updates = await tg.get_updates()
        except (TelegramError, httpx.HTTPError) as exc:
            print(f"실패: {exc}", file=sys.stderr)
            return 1
    chats: dict[int, tuple[str, str]] = {}
    for update in updates:
        for key in ("message", "edited_message", "channel_post"):
            chat = (update.get(key) or {}).get("chat")
            if chat:
                name = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
                chats[chat["id"]] = (chat.get("type", ""), name)
    if not chats:
        print("아직 받은 메시지가 없습니다. 봇(또는 봇이 있는 그룹)에 아무 메시지나 보낸 뒤 다시 실행하세요.")
        return 1
    print("chat_id\ttype\tname")
    for chat_id, (kind, name) in chats.items():
        print(f"{chat_id}\t{kind}\t{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
