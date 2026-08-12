# JUNVIS

macOS를 위한 개인 AI OS. 개발자 AI 비서가 아니라 **CTO + 콘텐츠 매니저 + 프로젝트 매니저 + AI 비서**를 목표로 한다.

> 새로운 AI 비서를 만드는 것이 아니다. 최고 수준 오픈소스를 분석해 **장점만 흡수한다.**

## 지금 되는 것

### 1. Project Brain — 프로젝트를 기억한다

```bash
junvis add ~/dev/zunvis --purpose "개인 AI OS"   # 등록 + git·README 자동 수집
junvis list                                      # 기억하고 있는 프로젝트
junvis context zunvis                            # Context Pack 출력
junvis search "AI 웹앱"                          # 전문 검색(FTS5)
junvis remember zunvis "Ollama를 기본으로 쓴다"   # 사실 주입
junvis doctor                                    # 상태 점검
```

### 2. Creator Mode — ZUN 브랜드 콘텐츠를 만든다

새 프로젝트를 등록하면 JUNVIS가 먼저 제안한다.

```
$ junvis add ~/dev/reels-editor --name "릴스 편집기"
릴스 편집기 — reels-editor
  스택   : Python, Next.js
  최근   : a1b2c3d 첫 커밋

제안: "릴스 편집기 만든 과정" 릴스 만들까요?
  → junvis reel --id 7f3a9c21
```

한 번 부르면 **9개 구성요소가 한 번에** 나온다 — Hook · 장면 구성 · 대본 · B-roll · 캡션 · 해시태그 · 썸네일 문구 · 댓글 유도 문구.

```bash
junvis reel --id 7f3a9c21                # 제안을 대본으로
junvis reel "MCP로 Claude Code 확장하기"   # 주제로 바로
junvis reel "..." --project zunvis        # 그 프로젝트의 실제 사실을 근거로
junvis reel "..." --carousel              # 릴스 대신 캐러셀

junvis content --status suggested         # 아직 손대지 않은 제안
junvis show 7f3a9c21                      # 전체 대본
junvis published 7f3a9c21 --url https://…  # 발행 기록
junvis brand                              # ZUN 브랜드 성향
```

로컬 모델(Ollama)이 필요하다. `ollama serve` 후 `junvis doctor`로 연결을 확인한다.
모델은 `JUNVIS_MODEL_FAST` / `JUNVIS_MODEL_DEEP`로 바꾼다.

> JUNVIS는 Instagram에 **올리지 않는다.** 기획하고 기억할 뿐, 발행은 사람이 한다.

### 3. Daily Brief — 하루를 시작한다

```
$ junvis brief
# 2026-08-12 브리핑

## 멈춰 있는 작업
- ! ZUNVIS에 커밋되지 않은 변경
    main · 마지막 커밋: 6b4ebc1 feat: Creator Mode
    → junvis context zunvis

## ZUN 콘텐츠
- · 아직 발행한 콘텐츠가 없습니다
    → junvis content

## 대기 중인 아이디어
- ZUNVIS 만든 과정
    → junvis reel --id de118215

## 작업 습관
- 최근 7일 동안 6번 작업했습니다
- 가장 활발한 시간대: 22시
```

일정 · 멈춰 있는 작업 · 할 일 · 열린 이슈 · ZUN 콘텐츠 · 아이디어 · 프로젝트 · AI 소식 · 작업 습관을 **우선순위대로** 모은다.

순서는 표현이 아니라 도메인 규칙이다. 마지막 업로드 이후 14일이 지나면 ZUN 콘텐츠가 열린 이슈보다 위로 올라온다 — 브랜드 성장이 장기 목표이기 때문이다.

캘린더는 macOS Calendar.app, 뉴스는 Hacker News, 작업 습관은 Trace에서 온다. **어느 하나가 실패해도 나머지는 나온다.**

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

노출되는 도구:

| Project Brain | Creator | Brief |
|---|---|---|
| `junvis_project_list` | `junvis_content_create` | `junvis_daily_brief` |
| `junvis_project_context` | `junvis_content_list` | |
| `junvis_project_search` | `junvis_content_get` | |
| `junvis_project_register` | `junvis_content_dismiss` | |
| `junvis_project_remember` | `junvis_content_published` | |
| `junvis_project_refresh` | `junvis_brand_voice` | |

세션을 시작할 때 `junvis_project_context`를 부르면 목적·기술스택·아키텍처·최근 커밋·TODO·이슈·메모·README가 토큰 예산에 맞춰 조립되어 주입된다.

## 설치

```bash
uv venv && uv pip install -e ".[dev]"
```

Python 3.11+ 필요. macOS 우선 설계이며 Windows 기능은 구현하지 않는다.

### 정기 작업 (launchd)

```bash
./scripts/install-launchd.sh                    # 스냅샷 갱신 + 평일 아침 브리핑
./scripts/install-launchd.sh --brief-hour 8     # 브리핑 시각 변경
./scripts/install-launchd.sh --uninstall
```

자체 상주 데몬을 띄우지 않는다. macOS에는 이미 launchd가 있고, 재부팅·절전 복귀를 OS가 처리한다. 아침 브리핑은 알림 센터로 한 줄 요약을 보낸다.

## 구조

```
src/junvis/
├── core/        # 공유 커널 — eventbus · policy · trace · model · mcp · persistence
├── features/    # Bounded Context 하나 = 폴더 하나
│   ├── project_brain/
│   │   ├── domain/          # 순수. 외부 기술을 모른다
│   │   ├── application/     # 유스케이스 + Port
│   │   ├── infrastructure/  # SQLite · git · GitHub 어댑터
│   │   ├── interface/       # MCP 도구 · 이벤트 구독자
│   │   └── contracts.py     # 다른 feature에 공개하는 전부
│   ├── creator/             # 같은 구조
│   └── brief/               # 같은 구조
└── apps/        # 조립 루트 — cli · mcp_server · adapters
```

**feature는 서로를 임포트하지 않는다.** 그런데도 프로젝트를 등록하면 릴스 제안이 생기고, 브리핑은 세 곳의 데이터를 모은다.

- `project_brain` ↔ `creator`: Event Bus (`project.registered` → 릴스 제안)
- `brief` → 나머지: 자기 입력 형태를 스스로 정의하고 `apps/adapters.py`가 채운다

이 규칙은 import-linter 계약 9개로 CI에서 강제된다.

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
| [`docs/03-CREATOR-MODE.md`](docs/03-CREATOR-MODE.md) | Creator Mode 설계 + ModelPort |
| [`docs/04-DAILY-BRIEF.md`](docs/04-DAILY-BRIEF.md) | Daily Brief 설계 + 우선순위 규칙 |

## 핵심 결정

- **도구 표준은 MCP 하나.** 자체 도구 포맷을 만들지 않는다. JUNVIS는 MCP Host이자 Server다.
- **기억은 2층.** 구조적 기억(프로젝트·커밋·캘린더)은 자체 SQLite가 소유하고, 서술적 기억은 Mem0에 위임한다.
- **모든 부작용은 PolicyEngine을 통과한다.** SAFE/LOW는 자동, MEDIUM/HIGH는 확인, FORBIDDEN은 거부.
- **모든 실행은 Trace를 남긴다.** Trace가 개인화의 원재료다.
- **로컬 우선.** Ollama가 기본이고 클라우드는 명시적 폴백이다.

## 라이선스 주의

ScreenPipe(상용 소스공개)와 isair/jarvis(개인용 무료)는 **코드를 가져오지 않는다.** 설계와 기법만 참조하고 해당 계층은 자체 구현한다. 자세한 내용은 [`docs/01-ANALYSIS.md` §9](docs/01-ANALYSIS.md).
