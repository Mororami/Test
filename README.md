# Bitkub 시세 알람 봇 + Bitkub × Bithumb 김프 대시보드

Bitkub(태국, THB 마켓)에 상장된 코인의 시세를 원화로 환산해 보여주고, 급등하거나 김치 프리미엄(김프)이 커지면
Telegram 으로 알려주는 봇과, Bitkub·Bithumb 가격을 나란히 비교하는 웹 대시보드입니다.
두 기능은 하나의 Python 프로젝트에서 같은 수집 로직을 공유합니다.

| 구성 | 실행 | 하는 일 |
|---|---|---|
| **1. 시세 알람 봇** | `python -m app bot` | 30초마다 Bitkub 전 종목 수집 → THB→KRW 환산 → 급등/김프 조건 판정 → Telegram 전송 |
| **2. 김프 대시보드** | `python -m app dashboard` | `http://127.0.0.1:8080` 에서 Bitkub vs Bithumb 가격·김프·거래대금 표 (정렬·검색·자동 갱신·다크모드) |
| 둘 다 | `python -m app all` | 한 프로세스에서 봇 + 대시보드 |

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env          # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 입력 (아래 참고)

python -m app once            # 한 번 수집해서 김프 표를 콘솔에 출력 (연결 확인)
python -m app all             # 알람 봇 + 대시보드 (http://127.0.0.1:8080)
```

Python 3.11 이상. 거래소·환율 API 는 모두 공개 API 라 거래소 API 키는 필요 없습니다.

## Telegram 설정

1. Telegram 에서 [@BotFather](https://t.me/BotFather) 에게 `/newbot` → 발급된 토큰을 `.env` 의 `TELEGRAM_BOT_TOKEN` 에 넣습니다.
2. 만든 봇에게 아무 메시지나 보내거나(개인 알림), 봇을 그룹에 초대한 뒤 그룹에서 메시지를 보냅니다.
3. `python -m app chat-id` 를 실행하면 봇이 받은 메시지의 `chat_id` 목록이 나옵니다. 원하는 값을 `TELEGRAM_CHAT_ID` 에 넣습니다.
4. `python -m app test-telegram` 으로 테스트 메시지가 오는지 확인합니다.

`.env` 가 없거나 비어 있으면 알림은 Telegram 대신 콘솔에 출력됩니다.

## 명령어

| 명령 | 설명 |
|---|---|
| `python -m app bot` | 시세 수집 + Telegram 알람 |
| `python -m app dashboard` | 시세 수집 + 웹 대시보드 (알람 전송 없음, 감지된 알림은 대시보드에만 표시) |
| `python -m app all` | 시세 수집 + Telegram 알람 + 웹 대시보드 |
| `python -m app once [-n 30]` | 한 번 수집해서 김프 상위 N개를 콘솔에 표로 출력 |
| `python -m app test-telegram` | Telegram 연결 테스트 메시지 전송 |
| `python -m app chat-id` | 봇이 받은 메시지에서 chat_id 찾기 |
| 공통 옵션 | `-c 경로` 설정 파일 지정, `-v` 디버그 로그 |

대시보드 API: `GET /api/snapshot` (전체 표 데이터), `GET /api/alerts?limit=50` (최근 알림), `GET /api/health`.

## 설정 (`config.yaml`)

비밀값은 `.env`, 나머지 동작 파라미터는 `config.yaml` 입니다. 주요 항목:

```yaml
poll_interval_sec: 30            # 수집 주기

fx:
  mode: forex                    # forex: 외환 환율 / usdt: 두 거래소 USDT 가격으로 역산한 환율
  override_thb_krw: null         # 환율을 직접 고정하고 싶을 때 (예: 41.5)

alerts:
  pump:                          # 단기 급등: 최근 window_min 분 동안 threshold_pct % 이상 상승
    enabled: true
    window_min: 5
    threshold_pct: 5.0
    min_quote_volume_thb: 100000 # Bitkub 24h 거래대금이 이보다 작은 코인은 무시
  change_24h:                    # Bitkub 24h 변동률 기준 (기본 꺼짐)
    enabled: false
    threshold_pct: 20.0
  kimp:                          # |김프| 가 threshold_pct % 이상 (Bithumb 상장 코인만)
    enabled: true
    threshold_pct: 5.0
    min_quote_volume_thb: 100000
    min_quote_volume_krw: 10000000
  cooldown_min: 30               # 같은 코인·같은 종류 알림 재발송 최소 간격
  startup_message: true          # 봇 시작 시 시작 알림

symbols:
  include: []                    # 비우면 Bitkub 전체. 예: [BTC, ETH, XRP]
  exclude: []                    # 제외할 심볼
  aliases: {}                    # 두 거래소 심볼이 다를 때 매핑 {BITKUB심볼: BITHUMB심볼}
  mismatch_kimp_pct: 50          # |김프| 가 이 값 이상이면 '티커만 같은 다른 코인' 으로 보고 알림·통계에서 제외

dashboard:
  host: 127.0.0.1                # 외부에서 접속하려면 0.0.0.0
  port: 8080
  kimp_highlight_pct: 3.0        # 표에서 강조할 |김프| 기준
```

환경 변수 `DASHBOARD_HOST`, `DASHBOARD_PORT` 는 `config.yaml` 값보다 우선합니다. `KIMP_CONFIG` 로 설정 파일 경로를 바꿀 수 있습니다.

### 알림 동작

- **급등**: 봇이 메모리에 가격 이력을 쌓고, 현재가를 `window_min` 분 전 가격과 비교합니다. 봇을 켠 직후에는 이력이 없어 `window_min` 이 지나야 판정이 시작됩니다.
- **김프**: `|김프| >= threshold_pct` 인 코인. 양수면 Bithumb 이 비싼 것(김프), 음수면 Bitkub 이 비싼 것(역프)입니다.
- 조건이 **처음 충족될 때 한 번** 알리고, 계속 충족 중이면 다시 알리지 않습니다. 조건이 풀렸다가 다시 충족되면 `cooldown_min` 이 지난 뒤에 다시 알립니다.
- 한 사이클에 여러 알림이 생기면 한 메시지로 묶어 보냅니다.

## 김프 계산 방식

```
Bitkub 환산가(KRW) = Bitkub 가격(THB) × 환율(1 THB 당 KRW)
김프(%) = (Bithumb 가격(KRW) ÷ Bitkub 환산가(KRW) − 1) × 100
```

- **외환 환율** (`fx.mode: forex`, 기본): [frankfurter](https://frankfurter.dev) (ECB 고시, 영업일 1회 갱신) → 실패 시 [exchangerate-api](https://www.exchangerate-api.com) 순으로 조회하고 1시간 캐시합니다. 둘 다 실패하면 마지막 값을 유지합니다.
- **USDT 내재환율** (`fx.mode: usdt`): `Bithumb KRW-USDT 가격 ÷ Bitkub USDT_THB 가격`. 실제로 스테이블코인을 옮길 때 적용되는 환율에 가까워 차익거래 관점에서는 이쪽이 더 현실적입니다. 대시보드는 두 환율을 항상 같이 보여주고, 김프 계산에 어느 쪽을 썼는지 표시합니다.
- **티커 충돌**: 두 거래소에서 심볼은 같지만 다른 코인인 경우가 있습니다(예: 수집 시점의 `EDGE` 는 김프 −88%). `mismatch_kimp_pct` 이상이면 "동명이인?" 으로 표시하고 알림·통계에서 제외합니다. 확실히 다른 코인이면 `symbols.exclude` 에, 심볼만 다른 같은 코인이면 `symbols.aliases` 에 적어 주세요.

## Docker

```bash
cp .env.example .env   # 토큰 입력
docker compose up -d   # 봇 + 대시보드, http://localhost:8080
```

`config.yaml` 은 컨테이너에 읽기 전용으로 마운트되므로 수정 후 `docker compose restart` 하면 반영됩니다.

## 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest
```

거래소·환율·Telegram 호출은 모두 `httpx.MockTransport` 로 대체되어 네트워크 없이 실행됩니다.

## 프로젝트 구조

```
app/
  __main__.py          CLI (bot / dashboard / all / once / test-telegram / chat-id)
  config.py            .env + config.yaml 로딩·검증
  models.py            Ticker, FxRate, CoinRow, Snapshot, Alert
  exchanges/
    bitkub.py          Bitkub 공개 API (v3, 실패 시 구버전으로 폴백)
    bithumb.py         Bithumb 공개 API v1 (마켓 목록 캐시, 100개씩 조회)
    fx.py              THB→KRW 환율 (frankfurter → exchangerate-api, 캐시·유지)
  market.py            스냅샷 생성: 환산가, 김프, USDT 내재환율, 통계
  history.py           단기 변동률용 가격 이력
  alerts.py            급등/24h/김프 판정, 엣지 트리거 + 쿨다운, 메시지 생성
  notifier.py          Telegram Bot API 전송 (분할, 429 재시도), 콘솔 대체
  collector.py         주기 수집 루프 (봇·대시보드 공용)
  dashboard/
    server.py          FastAPI: /, /api/snapshot, /api/alerts, /api/health
    static/index.html  대시보드 화면 (외부 의존성 없음)
tests/                 pytest (네트워크 없이 실행)
config.yaml            동작 설정
.env.example           비밀값 예시
docs/bithumb-mcp.md    (별도) Claude Code 용 Bithumb MCP 서버 설정 안내
```

## 주의

- 공개 API 시세는 마지막 체결가 기준이며 호가 스프레드·수수료·출금 수수료·송금 시간은 반영되지 않습니다. 실제 차익거래 판단에는 호가창 확인이 필요합니다.
- 외환 환율은 일 1회 고시값이므로 장중 환율 변동은 반영되지 않습니다. 실시간에 가까운 값이 필요하면 `fx.mode: usdt` 를 쓰세요.
