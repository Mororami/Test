# Bithumb AI Trade Kit 설정

이 저장소는 [Bithumb AI Trade Kit](https://github.com/bithumb-official/bithumb-ai-trade-kit)의
**MCP 서버**와 **CLI + Skills**를 사용할 수 있도록 설정되어 있습니다.

- MCP 설정 가이드: [setup-mcp.md](https://github.com/bithumb-official/bithumb-ai-trade-kit/blob/main/setup-mcp.md)
- CLI/Skills 설정 가이드: [setup-cli-skills.md](https://github.com/bithumb-official/bithumb-ai-trade-kit/blob/main/setup-cli-skills.md)

## 사전 요구사항

- Node.js 18+ (`node -v`로 확인)

---

## 1. MCP 서버

### 구성 파일

- `.mcp.json` — 프로젝트 루트의 Claude Code MCP 설정. `bithumb` 서버를
  `npx @bithumb-official/bithumb-mcp --modules all`로 실행합니다.

### 사용

1. 아래 [API 키 설정](#api-키-설정)의 환경 변수를 등록합니다.
2. Claude Code를 재시작하면 `.mcp.json`의 `bithumb` MCP 서버가 로드됩니다.
3. 프롬프트에서 승인하면 서버가 연결되고 `bithumb_market_ticker` 등 도구를 사용할 수 있습니다.

### 옵션

`.mcp.json`의 `args`에서 실행 옵션을 조정할 수 있습니다.

- `--modules <list>`: `market, account, trade, twap, withdraw, deposit` 또는 `all` (기본: 전체)
- `--read-only`: 조회 전용 (주문 생성/취소 비활성화)
- `--log-level <level>`: `error, warn, info, debug`

예를 들어 조회만 허용하려면:

```json
"args": ["-y", "@bithumb-official/bithumb-mcp", "--modules", "market,account", "--read-only"]
```

---

## 2. CLI

### 설치

```bash
npm install -g @bithumb-official/bithumb-cli
bithumb --version
```

### 사용 예시

```bash
# 공개 데이터 (인증 불필요)
bithumb market ticker KRW-BTC

# 설정 진단 (무인증)
bithumb system diagnose

# 모듈별 도움말
bithumb <market|account|trade|twap|withdraw|deposit> --help
```

> 전역 설치(`-g`)는 npm 전역 경로에 설치되며, 실행 환경이 초기화되면 다시 설치해야 합니다.

---

## 3. Skills

### 설치

```bash
npx skills add bithumb-official/bithumb-ai-trade-kit
```

설치되는 6개 스킬 (`.agents/skills/`, 소스/해시는 `skills-lock.json`에 고정):

| 스킬 | 설명 |
|---|---|
| `bithumb-market`  | 시세·호가·캔들·체결·마켓 목록·유의 종목·경보제·공지·수수료 (무인증) |
| `bithumb-account` | 자산·지갑 상태·API 키·주문 가능 정보 |
| `bithumb-trade`   | 주문 조회/생성/취소·배치·TWAP |
| `bithumb-deposit` | 입금 주소/내역 |
| `bithumb-withdraw`| 출금(코인/원화) |
| `bithumb-system`  | 진단·로컬 감사 로그 (무인증) |

각 스킬은 `bithumb` CLI를 호출하므로 [CLI 설치](#2-cli)가 선행되어야 합니다.
잠금 파일로부터 재설치하려면:

```bash
npx skills install
```

---

## API 키 설정

Bithumb [API 관리 포털](https://www.bithumb.com/react/api-support/management-api)에서
발급받은 키를 **환경 변수로만** 등록하세요.
**키 값을 코드나 설정 파일에 직접 넣지 마세요.**

### macOS / Linux

```bash
echo 'export BITHUMB_ACCESS_KEY="your_access_key"' >> ~/.zshrc
echo 'export BITHUMB_SECRET_KEY="your_secret_key"' >> ~/.zshrc
source ~/.zshrc
```

### Windows (PowerShell)

```powershell
[System.Environment]::SetEnvironmentVariable("BITHUMB_ACCESS_KEY", "your_access_key", "User")
[System.Environment]::SetEnvironmentVariable("BITHUMB_SECRET_KEY", "your_secret_key", "User")
```

설정 후 확인:

```bash
bithumb system diagnose
```

---

## 네트워크 참고 (원격/샌드박스 환경)

시세·주문 등 실제 기능은 `https://api.bithumb.com` 로의 아웃바운드 접속이 필요합니다.
egress(아웃바운드) 정책이 제한된 원격/샌드박스 환경에서는 해당 도메인이 차단되어
(`HTTP 403`) MCP·CLI·Skills가 설치·설정은 정상이어도 실시간 데이터에 접근하지 못할 수 있습니다.
이 경우 `api.bithumb.com`을 허용하는 네트워크 정책의 환경이나 로컬 머신에서 실행하세요.
