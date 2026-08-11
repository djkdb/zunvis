# JUNVIS

macOS를 위한 개인 AI OS. 개발자 AI 비서가 아니라 **CTO + 콘텐츠 매니저 + 프로젝트 매니저 + AI 비서**를 목표로 한다.

> 새로운 AI 비서를 만드는 것이 아니다. 최고 수준 오픈소스를 분석해 **장점만 흡수한다.**

## 지금 되는 것 (MVP)

**Project Brain + MCP 코어.** JUNVIS가 GitHub 프로젝트를 기억하고, 그 지식을 Claude Code에 MCP로 그대로 넘긴다.

```bash
junvis add ~/dev/zunvis --purpose "개인 AI OS"   # 등록 + git·README 자동 수집
junvis list                                      # 기억하고 있는 프로젝트
junvis context zunvis                            # Context Pack 출력
junvis search "AI 웹앱"                          # 전문 검색(FTS5)
junvis remember zunvis "Ollama를 기본으로 쓴다"   # 사실 주입
junvis doctor                                    # 상태 점검
```

### Claude Code에 붙이기

`~/.claude.json` 또는 프로젝트 `.mcp.json`:

```json
{
  "mcpServers": {
    "junvis": {
      "command": "junvis-mcp"
    }
  }
}
```

노출되는 도구: `junvis_project_list` · `junvis_project_context` · `junvis_project_search` · `junvis_project_register` · `junvis_project_remember` · `junvis_project_refresh`

세션을 시작할 때 `junvis_project_context`를 부르면 목적·기술스택·아키텍처·최근 커밋·TODO·이슈·메모·README가 토큰 예산에 맞춰 조립되어 주입된다.

## 설치

```bash
uv venv && uv pip install -e ".[dev]"
```

Python 3.11+ 필요. macOS 우선 설계이며 Windows 기능은 구현하지 않는다.

### 자동 갱신 (launchd)

```bash
./scripts/install-launchd.sh      # 6시간마다 스냅샷 갱신
./scripts/install-launchd.sh --uninstall
```

## 구조

```
src/junvis/
├── core/        # 공유 커널 — eventbus · policy · trace · persistence
├── features/    # Bounded Context 하나 = 폴더 하나
│   └── project_brain/
│       ├── domain/          # 순수. 외부 기술을 모른다
│       ├── application/     # 유스케이스 + Port
│       ├── infrastructure/  # SQLite · git · GitHub 어댑터
│       ├── interface/       # MCP 도구 · 이벤트 구독자
│       └── contracts.py     # 다른 feature에 공개하는 전부
└── apps/        # 조립 루트 — cli · mcp_server
```

의존성은 항상 안쪽을 향한다. 이 규칙은 문서가 아니라 **import-linter 계약으로 강제**된다:

```bash
lint-imports    # 계층을 어기면 실패한다
pytest          # 도메인은 외부 의존 없이 단위 테스트로 검증된다
```

## 설계 문서

| 문서 | 내용 |
|---|---|
| [`docs/JUNVIS-BRIEF.md`](docs/JUNVIS-BRIEF.md) | 원본 요구사항 |
| [`docs/01-ANALYSIS.md`](docs/01-ANALYSIS.md) | 오픈소스 7종 분석 — 장점/단점/가져올 것/가져오면 안 되는 것 |
| [`docs/02-ARCHITECTURE.md`](docs/02-ARCHITECTURE.md) | 아키텍처 설계 + MVP 태스크 분해 |

## 핵심 결정

- **도구 표준은 MCP 하나.** 자체 도구 포맷을 만들지 않는다. JUNVIS는 MCP Host이자 Server다.
- **기억은 2층.** 구조적 기억(프로젝트·커밋·캘린더)은 자체 SQLite가 소유하고, 서술적 기억은 Mem0에 위임한다.
- **모든 부작용은 PolicyEngine을 통과한다.** SAFE/LOW는 자동, MEDIUM/HIGH는 확인, FORBIDDEN은 거부.
- **모든 실행은 Trace를 남긴다.** Trace가 개인화의 원재료다.
- **로컬 우선.** Ollama가 기본이고 클라우드는 명시적 폴백이다.

## 라이선스 주의

ScreenPipe(상용 소스공개)와 isair/jarvis(개인용 무료)는 **코드를 가져오지 않는다.** 설계와 기법만 참조하고 해당 계층은 자체 구현한다. 자세한 내용은 [`docs/01-ANALYSIS.md` §9](docs/01-ANALYSIS.md).
