# JUNVIS — MCP Host 설계

> 단계: **설계**
> 선행: 전 기능
> 목표: JUNVIS가 외부 MCP 서버를 도구로 쓴다

---

## 0. Browser를 만들려다 여기로 온 이유

계획은 `browser` Bounded Context를 만들고 Browser Use를 라이브러리로 감싸는
것이었다. 실제로 설치해 보고 계획을 바꿨다.

```
$ uv pip install browser-use
$ pytest
TypeError: Server.__init__() got an unexpected keyword argument 'on_list_tools'
```

`browser-use 0.13.7`은 `mcp==1.26.0`을 **정확히 고정**한다. JUNVIS의 MCP
서버는 SDK 2.0 API로 짜여 있다. 한 환경에 공존할 수 없다.

선택지는 셋이었다.

| 안 | 판단 |
|---|---|
| 우리 MCP 서버를 1.26 API로 내린다 | ❌ MCP 서버는 JUNVIS의 심장이다(M9). 남의 핀에 우리 심장을 맞출 수 없고, 상대가 핀을 올리면 또 깨진다 |
| 자체 Playwright 에이전트를 만든다 | ❌ Browser Use를 쓰기로 한 이유였던 DOM 추출 품질을 잃는다 |
| **별도 프로세스로 쓴다** | ✅ |

그리고 확인해 보니 **Browser Use는 자체 MCP 서버를 제공한다**
(`browser_use/mcp/server.py`). 그러면 감싸는 어댑터를 쓸 이유가 없다.
JUNVIS가 그 서버에 **붙으면** 된다.

이것은 임시방편이 아니라 1단계 분석이 이미 정해둔 관계다.

> **가져오면 안 되는 부분**: Browser Use의 Agent 루프를 JUNVIS 최상위
> 오케스트레이터로 삼는 것 → JUNVIS Orchestrator가 상위, Browser Use는 하위 도구

별도 프로세스의 종속 도구가 정확히 그 관계다. 그리고 얻는 것이 훨씬 크다:
**브라우저 전용 어댑터 대신, 어떤 서드파티 MCP 서버든 쓸 수 있는 길**이 열린다.

---

## 1. JUNVIS는 이제 양방향이다

설계 §6에서 이렇게 적어뒀다.

> JUNVIS는 **MCP Host**가 된다. `core/mcp`에 레지스트리를 두고 서버를
> **지연 기동(lazy spawn) + 유휴 시 종료**한다.

지금까지는 Server 쪽만 만들었다. 이제 Host 쪽을 만든다.

```
Claude Code ──MCP──▶ JUNVIS ──MCP──▶ browser-use
                       │              notion, slack, …
                       └─ 자체 기능 (project/creator/brief/memory)
```

---

## 2. 지연 기동 — 그런데 도구 목록은 어떻게 아는가

"부팅 시 전체 서버 기동 금지"와 "어떤 도구가 있는지 알아야 한다"는 충돌한다.
서버를 띄우지 않으면 도구 목록을 모르기 때문이다.

**도구 카탈로그를 캐시한다.**

```
처음 등록      → 한 번 띄워서 도구 목록을 받아 SQLite에 저장 → 종료
이후 목록 조회  → 캐시에서 (서버를 띄우지 않는다)
실제 호출      → 그때 띄운다 → 유휴 시간 뒤 종료
```

캐시가 낡을 수 있다. 그래서 호출 시 도구가 없으면 카탈로그를 갱신하고 한 번
더 시도한다.

---

## 3. 컨텍스트 오염 대책

1단계 분석의 MCP 항목에서 가장 큰 단점으로 꼽은 것이다.

> 도구가 많아지면 **컨텍스트 오염(context rot)** — 모든 도구 정의를 프롬프트에
> 넣을 수 없다

`isair/jarvis`의 해법(임베딩 기반 관련도 필터)을 차용하되, **기본 구현은
토큰 겹침 순위**로 한다. 임베딩을 쓰려면 임베딩 모델이 떠 있어야 하는데,
그건 도구 하나 고르자고 요구하기엔 무겁다. `ToolRankerPort` 뒤에 두었으므로
품질이 아쉬우면 교체한다.

---

## 4. 정책

외부 서버는 우리가 만들지 않은 코드다. 그래서:

- 외부 도구 호출은 `mcp.external.<서버>.<도구>` 행위로 판정한다 → 기본 **MEDIUM**(확인 필요)
- 서버 설정의 `trusted: true`로 낮출 수 있다 → LOW(자동)
- 등록되지 않은 서버는 호출할 수 없다

MCP를 통해 JUNVIS를 쓰는 경우 확인 통로가 없다. 그래서 도구 인자에
`confirm: true`를 요구한다 — 호스트(Claude Code)가 사용자에게 묻고 넘긴다.
SDK의 Elicitation을 쓰지 않는 이유는 도구 핸들러가 세션에 접근하지 않는
순수 함수이기 때문이다. 그 단순함을 지키는 편이 낫다.

---

## 5. 설정

`~/.junvis/mcp.json` — Claude Code와 같은 모양을 쓴다. 익숙한 형식을 두고
새 형식을 만들 이유가 없다.

```json
{
  "mcpServers": {
    "browser": {
      "command": "uvx",
      "args": ["--from", "browser-use", "python", "-m", "browser_use.mcp.server"],
      "env": { "OPENAI_API_KEY": "" },
      "trusted": false
    }
  }
}
```

`uvx`로 띄우면 browser-use가 **자기 격리된 환경**에 설치되므로 JUNVIS의
`mcp` 버전과 충돌하지 않는다. §0의 문제가 구조적으로 사라진다.

---

## 6. 구현 순서

| # | 태스크 | 완료 기준 |
|---|---|---|
| H1 | 설정·카탈로그 | 설정 왕복, 캐시 저장/조회 |
| H2 | Host — 지연 기동·호출·유휴 종료 | 실제 MCP 서버를 띄워 호출 왕복 |
| H3 | 정책 게이트·도구 선별 | 미확인 외부 호출이 막힌다 |
| H4 | CLI·배선 | `junvis mcp add/list/tools/call` |

## 7. 하지 않는 것

- **원격 HTTP 서버.** 로컬 stdio로 충분하다(설계 §6).
- **서버 자동 발견.** 사용자가 명시적으로 등록한 것만 쓴다.
- **임베딩 랭커.** 포트만 열어 둔다.
- **browser-use를 의존성으로.** §0이 그 이유 전부다.
