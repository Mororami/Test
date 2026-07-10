# Bithumb MCP 설정

이 저장소는 [Bithumb MCP 서버](https://github.com/bithumb-official/bithumb-ai-trade-kit/blob/main/setup-mcp.md)를 Claude Code에서 사용할 수 있도록 설정되어 있습니다.

## 구성 파일

- `.mcp.json` — 프로젝트 루트에 위치한 Claude Code MCP 설정. `bithumb` 서버를 `npx @bithumb-official/bithumb-mcp`로 실행합니다.

## 사전 요구사항

- Node.js 18+ (`node -v`로 확인)

## API 키 설정

Bithumb [API 관리 포털](https://www.bithumb.com/react/api-support/management-api)에서 발급받은 키를 환경 변수로 등록하세요. **키 값은 코드나 설정 파일에 직접 넣지 말고 환경 변수로만 관리합니다.**

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

## 사용

1. 위 환경 변수를 설정합니다.
2. Claude Code를 재시작하면 `.mcp.json`의 `bithumb` MCP 서버가 로드됩니다.
3. 프롬프트에서 승인하면 서버가 연결됩니다.

### 옵션

`.mcp.json`의 `args`에서 실행 옵션을 조정할 수 있습니다.

- `--modules <list>`: `market, account, trade, twap, withdraw, deposit` 또는 `all` (기본: 전체)
- `--read-only`: 조회 전용 (주문 생성/취소 비활성화)
- `--log-level <level>`: `error, warn, info, debug`

예를 들어 조회만 허용하려면:

```json
"args": ["-y", "@bithumb-official/bithumb-mcp", "--modules", "market,account", "--read-only"]
```
