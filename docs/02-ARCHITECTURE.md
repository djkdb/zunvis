# JUNVIS — 2단계: 아키텍처 설계

> 단계: **2. 설계** (1단계 분석 결과 기반)
> 입력: `docs/01-ANALYSIS.md`
> 원칙: Feature Folder / Clean Architecture / SOLID / DDD / Plugin Architecture / Event Bus

---

## 이 문서를 읽기 전에 — 구현하며 바뀐 것

설계는 지도이지 영토가 아니다. 구현하며 사실이 달라진 곳을 여기 모아 둔다.
각 항목의 근거는 해당 단계 문서에 있다.

| 이 문서의 계획 | 실제 | 근거 |
|---|---|---|
| 서술적 기억은 Mem0에 위임 | 자체 SQLite+FTS5. Mem0 어댑터는 없음 | [06 §0](06-MEMORY.md) |
| `MemoryPort`를 `core`에 | 각 feature가 자기 Port를 선언하고 조립 루트가 채움 | 계약 8·10·11번 |
| `browser` Bounded Context | 만들지 않음. 외부 MCP 서버로 씀 | [07 §0](07-MCP-HOST.md) |
| 임베딩 기반 도구 선별 | 토큰 겹침 랭커. 임베딩은 포트만 열어 둠 | [07 §3](07-MCP-HOST.md) |
| `scheduler` Bounded Context | 만들지 않음. launchd가 한다 | [04 §0](04-DAILY-BRIEF.md) |
| Plugin Architecture (`~/.junvis/plugins`) | **아직 없음.** 외부 MCP 서버가 그 자리를 대신하고 있다 | — |
| Vision / Coding Agent | **아직 없음** | — |

### 현재 구현된 Bounded Context

`project_brain` · `creator` · `brief` · `voice` · `memory`
그리고 `core`의 MCP Host.

---

## 0. 확정된 기술 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 코어 런타임 | **Python 3.12 (uv 관리)** | Mem0·Browser Use·MCP Python SDK를 그대로 임포트. 1단계에서 "코드로 직접 의존"할 3개가 전부 Python 생태계 |
| 네이티브 레이어 | **Swift 헬퍼 바이너리 `junvis-mac`** | ScreenCaptureKit·Vision·Accessibility·AVSpeechSynthesizer는 Python에서 접근 불가. JSON-RPC over stdio로 통신 |
| 전역 단축키/윈도우 제어 | **Hammerspoon + AppleScript** | pynput류 비네이티브 훅은 macOS 26에서 깨짐(1단계 7번 교훈) |
| 상주 방식 | **launchd** (`~/Library/LaunchAgents`) | 자체 데몬 상주 대신 OS 표준 |
| 저장소 | **SQLite (WAL) + FTS5**, 벡터는 로컬 Qdrant | 검소하고 백업 쉬움. 1단계 4번 참조 |
| LLM | **Ollama 기본 / Claude 폴백** — `ModelPort` 뒤 | 로컬 우선, 필요 시에만 클라우드 |
| 도구 표준 | **MCP 단일** | 1단계 6번 |
| MVP 범위 | **Project Brain + MCP 코어** | 매일 쓰는 기능이자 나머지의 토대 |

---

## 1. 전체 구조 — 4계층 × Feature Folder

```
┌──────────────────────────────────────────────────────────────┐
│  apps/  (조립 루트 · Composition Root)                        │
│  mcp_server · cli · daemon · raycast_bridge                  │
└───────────────────────────┬──────────────────────────────────┘
                            │ 주입(inject)
┌───────────────────────────▼──────────────────────────────────┐
│  features/  (Bounded Context 하나 = 폴더 하나)                 │
│                                                              │
│   project_brain   memory   agent   creator   brief           │
│   scheduler       voice    vision  browser   coding          │
│                                                              │
│   각 feature 내부: interface → application → domain          │
│                              infrastructure ─┘ (구현만)       │
└───────────────────────────┬──────────────────────────────────┘
                            │ 사용
┌───────────────────────────▼──────────────────────────────────┐
│  core/  (Shared Kernel — 얇게 유지)                           │
│  eventbus · mcp · policy · trace · plugin · model            │
│  persistence · domain(공통 VO/이벤트 기반타입)                 │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  native/junvis-mac  (Swift)  ·  외부: Ollama · Qdrant · MCP   │
└──────────────────────────────────────────────────────────────┘
```

### 의존성 규칙 (반드시 지킨다)

1. `domain`은 **아무것도 임포트하지 않는다.** 표준 라이브러리만. Mem0·Browser Use·SQLite·MCP를 도메인은 모른다.
2. `application`은 `domain`만 임포트한다. 외부는 **Port(추상)** 로만 만난다.
3. `infrastructure`는 `application`의 Port를 **구현**한다. 화살표는 항상 안쪽을 향한다.
4. `interface`는 바깥 세계(MCP 도구, CLI, 이벤트 핸들러)를 `application` 유스케이스로 번역한다.
5. **feature끼리 서로의 내부를 임포트하지 않는다.** 교류는 오직 ① Event Bus ② `contracts.py`에 공개된 읽기 전용 DTO 두 가지뿐.
6. `core`는 어떤 feature도 임포트하지 않는다.

> 이 규칙은 문서로만 두지 않고 **import-linter 계약으로 CI에서 강제**한다(4단계 테스트에서 구성).

### Feature 내부 표준 구조

```
features/project_brain/
├── domain/
│   ├── model.py          # Project(Aggregate Root), ProjectSnapshot, TodoItem
│   ├── value_objects.py  # ProjectId, RepoRef, TechStack, Purpose
│   ├── events.py         # ProjectRegistered, SnapshotRefreshed, ProjectOpened
│   ├── repository.py     # ProjectRepository (인터페이스, ABC)
│   └── services.py       # 순수 도메인 규칙 (엔티티 하나로 안 되는 것)
├── application/
│   ├── ports.py          # GitPort, GitHubPort, ModelPort 재노출
│   ├── use_cases/
│   │   ├── register_project.py
│   │   ├── refresh_snapshot.py
│   │   ├── load_context.py
│   │   └── search_projects.py
│   └── dto.py
├── infrastructure/
│   ├── sqlite_repository.py
│   ├── git_adapter.py        # 로컬 git 읽기
│   ├── github_adapter.py     # GitHub MCP/API 경유
│   └── readme_parser.py
├── interface/
│   ├── mcp_tools.py      # MCP 도구로 노출
│   ├── cli.py
│   └── subscribers.py    # Event Bus 구독
└── contracts.py          # 다른 feature에 공개하는 DTO만
```

---

## 2. DDD — Bounded Context 지도

| Context | 책임 | Aggregate Root | 다른 Context와의 관계 |
|---|---|---|---|
| **project_brain** | 프로젝트를 기억하고 컨텍스트를 조립 | `Project` | creator·brief에 `ProjectSummary` 공개 |
| **memory** | 서술적 기억(Mem0) + 구조적 기억 소유 | `MemoryEntry`, `Preference` | 전 Context가 `MemoryPort`로 소비 |
| **agent** | 오케스트레이션·계획·다중 에이전트 협업 | `Task`, `Plan` | 모든 실행의 진입점 |
| **creator** | ZUN 브랜드 콘텐츠 생산 | `ContentIdea`, `ContentPlan` | project_brain 구독 → 신규 프로젝트 감지 |
| **brief** | Daily Brief 조립 | `Briefing` | 여러 Context의 공개 DTO를 읽기만 함 |
| **scheduler** | 시간 기반 발화 | `ScheduledJob` | 이벤트만 발행, 도메인 로직 없음 |
| **voice** | Wake word·STT·TTS | `Utterance` | `voice.command` 발행 |
| **vision** | 화면 이해 | `ScreenObservation` | Pull 전용, 기본 OFF |
| **browser** | 웹 자동화 | `BrowserTask` | agent의 하위 도구 |
| **coding** | 코드 작성 위임 | `CodingSession` | Claude Code 어댑터 |

### 유비쿼터스 언어 (코드·문서·대화에서 같은 단어를 쓴다)

| 용어 | 정의 | 쓰지 말 것 |
|---|---|---|
| **Project** | 사용자가 소유한 개발 프로젝트 1개 | repo, folder |
| **Snapshot** | 특정 시점 프로젝트 상태(README·스택·TODO·커밋) | cache, index |
| **Context Pack** | 에이전트에게 주입할 압축된 컨텍스트 묶음 | prompt |
| **Trace** | 실행 1건의 전 기록(입력·도구·결과·비용) | log |
| **Recall** | 기억 조회 결과 | search result |
| **Digest** | Recall을 주입용으로 압축한 것 | summary |
| **Capability** | 플러그인/도구가 요구하는 권한 단위 | permission |
| **Skill** | 사용하지 않음 — 우리 표준은 MCP **Tool** | — |

---

## 3. Event Bus

### 설계

```python
# core/eventbus/bus.py (개념)
class EventBus(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, topic: str, handler: Handler, *, mode: Delivery) -> None: ...
```

- **토픽 명명**: `<context>.<과거형 사실>` — `project.registered`, `voice.command_received`, `trace.completed`
- **전달 모드 2종**
  - `SYNC`: 같은 트랜잭션 안에서 즉시 (도메인 불변식 유지용, 실패 시 롤백)
  - `ASYNC`: **Outbox 테이블에 기록 후** 워커가 처리 (기억 쓰기, 콘텐츠 제안, 인덱싱 등 느린 작업)
- **내구성**: `outbox(id, topic, payload, occurred_at, processed_at, attempts)` — 프로세스가 죽어도 유실 없음
- **순서 보장**: Aggregate 단위로만 보장. 전역 순서는 보장하지 않는다(불필요한 병목)
- **실패 정책**: 3회 재시도(지수 백오프) → `deadletter` 테이블 → Daily Brief에 보고

### 이벤트가 아키텍처를 살리는 지점

브리프의 "Content Assistant"(새 프로젝트 만들면 릴스 제안)는 **feature 간 직접 호출로 구현하면 결합이 생긴다.** Event Bus로 풀면:

```
project_brain: ProjectRegistered 발행
        │
        ├─► creator/subscribers.py   → "이 프로젝트 릴스 만들까?" 제안 생성
        ├─► memory/subscribers.py    → 서술 기억에 기록
        └─► brief/subscribers.py     → 내일 브리핑 항목에 추가
```

`project_brain`은 `creator`의 존재를 **모른다.** 이것이 OCP(개방-폐쇄)의 실현이다.

---

## 4. Plugin Architecture

### 왜 필요한가
ZUN 콘텐츠 전략, 새 데이터 소스, 새 에이전트는 **코어를 고치지 않고** 추가되어야 한다.

### 플러그인 계약

```
~/.junvis/plugins/zun-reels/
├── plugin.toml
└── plugin.py
```

```toml
# plugin.toml
[plugin]
id = "zun-reels"
version = "0.1.0"
entry = "plugin:Plugin"
junvis_api = "^1.0"          # 코어 API 호환 범위

[capabilities]                # 선언하지 않은 것은 못 쓴다
requires = ["memory:read", "project:read", "model:local"]
optional = ["network:github"]

[subscriptions]
events = ["project.registered", "content.requested"]

[tools]                       # MCP 도구로 자동 노출
exposes = ["zun_generate_reel", "zun_caption"]
```

```python
class Plugin(JunvisPlugin):
    def activate(self, ctx: PluginContext) -> None:
        ctx.on("project.registered", self.suggest_reel)
        ctx.register_tool(zun_generate_reel)
```

### 규칙
- 플러그인은 `PluginContext`가 주는 **좁은 파사드만** 본다. 코어 내부·다른 feature의 도메인 객체 접근 불가.
- 선언하지 않은 Capability 호출은 `PolicyEngine`이 **차단**한다.
- 로딩 실패한 플러그인은 격리하고 나머지는 정상 동작한다(장애 전파 금지).
- 플러그인은 별도 프로세스가 아니라 같은 프로세스에서 로드하되, **버전 협상**(`junvis_api`)으로 호환성을 관리한다.

---

## 5. 핵심 횡단 관심사 (core/)

### 5.1 PolicyEngine — 승인 게이트 (Open Interpreter 차용)

모든 부작용은 여기를 통과한다.

| 위험 등급 | 예시 | 기본 정책 |
|---|---|---|
| `SAFE` | 기억 조회, 프로젝트 읽기 | 자동 실행 |
| `LOW` | 파일 쓰기(작업 디렉터리 내) | 자동 실행 + Trace |
| `MEDIUM` | git commit, 브라우저 조작, 외부 API | **확인 요구** (MCP Elicitation) |
| `HIGH` | git push, 셸 실행, 시스템 제어, 결제 | **확인 요구 + 근거 표시** |
| `FORBIDDEN` | 민감 앱 캡처, 자격증명 접근, 대량 삭제 | **거부** |

- 판정은 **행위 + 대상 + 컨텍스트** 조합. `git push`라도 `origin/main`이면 등급 상승.
- 사용자 확인은 **MCP Elicitation**을 기본 통로로 사용 → Claude Code에서도 동일하게 동작.

### 5.2 Trace — 학습의 원천 (OpenJarvis 차용)

```
trace(id, request, plan, tool_calls[], model, tokens, latency_ms,
      cost, outcome, user_feedback, occurred_at)
```

- 모든 실행이 Trace 1건을 남긴다. **Trace가 곧 Personal Memory의 원재료다.**
- 파생: 자주 쓰는 프롬프트 / 모델 / MCP / 작업 시간대 / 실패 패턴 → 브리프의 "Personal Memory" 항목이 여기서 자동으로 나온다.
- 비용·지연을 1급 필드로 둔다(로컬 우선 판단 근거).

### 5.3 MCP Host — 컨텍스트 오염 방지 (isair/jarvis 기법 차용)

```
요청 → 임베딩 기반 도구 사전선별(상위 N=12) → 필요한 서버만 lazy spawn
     → 실행 → 유휴 5분 후 서버 종료
```

- 부팅 시 전체 서버 기동 **금지**.
- 도구 설명은 임베딩 인덱스에 미리 저장, 요청마다 유사도 상위 N개만 프롬프트에 주입.

### 5.4 MemoryPort — 2층 기억

```python
class MemoryPort(Protocol):
    def remember(self, entry: MemoryWrite) -> None: ...      # 비동기(Outbox)
    def recall(self, query: Recall) -> list[MemoryHit]: ...
    def digest(self, hits: list[MemoryHit], budget: int) -> str: ...  # 압축 주입
```

| 층 | 내용 | 저장소 | 소유 |
|---|---|---|---|
| 구조적 | 프로젝트, 커밋, 콘텐츠 캘린더, 습관 통계 | **자체 SQLite** | JUNVIS |
| 서술적 | 대화, 선호, 일화 | **Mem0**(로컬 Ollama+Qdrant) | 위임 |

`digest()`가 핵심이다 — 회상 결과를 그대로 넣지 않고 **토큰 예산 안으로 압축**해 주입한다.

### 5.5 ModelPort

```python
class ModelPort(Protocol):
    async def complete(self, req: ModelRequest) -> ModelResponse: ...
```
- `OllamaAdapter`(기본) / `ClaudeAdapter`(폴백) / `EchoAdapter`(테스트용)
- 라우팅 규칙: 분류·판정·요약 = 로컬 소형 / 계획·코드·창작 = 고성능
- 폴백은 **명시적 정책**이지 자동 승격이 아니다(비용 통제).

---

## 6. MVP 설계 — Project Brain + MCP 코어

### 목표
> "프로젝트를 열면 JUNVIS가 그 프로젝트를 이미 알고 있다. 그리고 그 지식을 Claude Code에서 바로 쓸 수 있다."

### 도메인 모델

```python
# features/project_brain/domain/model.py
@dataclass
class Project:                    # Aggregate Root
    id: ProjectId
    slug: str
    name: str
    local_path: Path | None
    repo: RepoRef | None
    purpose: str                  # 이 프로젝트가 존재하는 이유
    tech_stack: TechStack
    architecture_note: str
    snapshot: ProjectSnapshot | None
    todos: list[TodoItem]

    def refresh(self, s: ProjectSnapshot) -> list[DomainEvent]: ...
    def context_pack(self, budget: TokenBudget) -> ContextPack: ...  # 도메인 규칙
```

`context_pack()`이 이 Context의 심장이다. 무엇을 우선 넣을지(목적 → 스택 → 최근 커밋 → TODO → 이슈)가 **도메인 규칙**이지 프롬프트 문자열이 아니다.

### 노출할 MCP 도구

| 도구 | 설명 | 위험도 |
|---|---|---|
| `junvis_project_list` | 등록된 프로젝트 목록 | SAFE |
| `junvis_project_context` | 프로젝트 Context Pack 반환 (Claude Code가 세션 시작 시 호출) | SAFE |
| `junvis_project_search` | 전체 프로젝트 전문검색(FTS5) | SAFE |
| `junvis_project_register` | 프로젝트 등록/갱신 | LOW |
| `junvis_project_remember` | "이 프로젝트에 대해 기억해둬" | LOW |
| `junvis_project_refresh` | 스냅샷 재수집 | LOW |

### MVP 태스크 분해 (3단계 구현으로 넘길 체크리스트)

| # | 태스크 | 산출물 | 완료 기준 |
|---|---|---|---|
| M1 | 저장소 뼈대 + uv + 계층 강제 | `pyproject.toml`, `src/junvis/`, import-linter 계약 | 계층 위반 시 CI 실패 |
| M2 | `core/persistence` — SQLite(WAL)+마이그레이션 | `schema/001_init.sql` | 마이그레이션 왕복 테스트 통과 |
| M3 | `core/eventbus` — SYNC/ASYNC + Outbox | `bus.py`, `outbox.py` | 프로세스 강제종료 후 이벤트 유실 0 |
| M4 | `core/policy` — PolicyEngine + 등급 테이블 | `policy.py` | HIGH 행위가 확인 없이 통과하지 않음 |
| M5 | `core/trace` — Trace 기록 | `trace.py` | 모든 유스케이스 실행이 Trace 1건 생성 |
| M6 | project_brain **domain** (순수, 외부 의존 0) | `model.py`, `value_objects.py`, `events.py` | 단위 테스트만으로 100% 검증 |
| M7 | project_brain **application** 유스케이스 4종 | `use_cases/` | Fake 어댑터로 전 유스케이스 테스트 |
| M8 | project_brain **infrastructure** — SQLite+git+README 파서 | `infrastructure/` | 실제 로컬 저장소로 스냅샷 수집 성공 |
| M9 | `apps/mcp_server` — MCP 서버 노출 | `mcp_server/` | **Claude Code에서 `junvis_project_context` 호출 성공** |
| M10 | `apps/cli` — `junvis project add/list/context` | `cli/` | 터미널에서 전체 왕복 |
| M11 | GitHub 연동(이슈·커밋) | `github_adapter.py` | 이슈/최근커밋이 Context Pack에 포함 |
| M12 | launchd 등록 + 자동 스냅샷 갱신 | `junvis.plist` | 재부팅 후에도 동작 |

**M9가 MVP의 성공 판정 기준이다.** 여기까지 되면 JUNVIS는 "앱"이 아니라 Claude Code가 쓰는 **개인 지식 계층**이 된다.

---

## 7. SOLID 적용 지점 (선언이 아니라 실제 위치)

| 원칙 | 적용 위치 |
|---|---|
| **SRP** | feature 폴더 = Bounded Context 1개. 유스케이스 파일 1개 = 시나리오 1개 |
| **OCP** | 새 기능은 Event Bus 구독자 + 플러그인으로 추가. 코어 수정 없음 |
| **LSP** | `ModelPort` 구현체(Ollama/Claude/Echo)는 어디서든 교체 가능해야 하며 테스트가 이를 검증 |
| **ISP** | `MemoryPort`를 읽기(`RecallPort`)와 쓰기(`RememberPort`)로 분리. 브리프는 읽기만 의존 |
| **DIP** | 도메인이 Mem0·Browser Use·SQLite를 모른다. 전부 Port 뒤 |

---

## 8. 4단계(테스트) 전략 미리보기

| 층 | 방식 | 비중 |
|---|---|---|
| domain | 순수 단위 테스트, 외부 의존 0, 밀리초 단위 | 최다 |
| application | Fake 어댑터(In-memory Repo, EchoModel) | 다수 |
| infrastructure | 실제 SQLite·실제 git 저장소 픽스처 | 소수 |
| 계층 규칙 | **import-linter 계약** | CI 필수 |
| MCP | MCP 클라이언트로 실제 도구 호출 계약 테스트 | 소수 |

**LLM 응답에 의존하는 테스트는 만들지 않는다.** 모델은 항상 `EchoAdapter`로 대체한다.

---

## 9. 이번 설계가 1단계 분석을 어떻게 반영했는가

| 분석 결론 | 설계 반영 |
|---|---|
| ScreenPipe 라이선스 위험 | `features/vision`을 Swift 네이티브로 자체 구현, 기본 OFF, MVP 제외 |
| Open Interpreter는 Rust 재작성판 | `CodingAgentPort` + Claude Code 어댑터 1순위, OI는 선택적 프로세스 연동 |
| isair/jarvis 개인용 라이선스 | Wake word 2단 게이트·digest·도구 선별 **기법만** 차용, 코드 0줄 |
| MCP가 우리 환경 공통 언어 | JUNVIS를 MCP Host이자 **MCP Server**로 양방향 설계 (MVP 핵심) |
| 컨텍스트 오염 | 임베딩 도구 선별(N=12) + `digest()` 압축을 **필수 구성요소**로 승격 |
| 기억 소유권 분리 | 구조적=자체 SQLite / 서술적=Mem0, `MemoryPort`로 은닉 |
| 실행 모드 3종 | scheduler가 on-demand/scheduled/continuous를 1급으로 지원 |
| Trace 기반 학습 | `core/trace`를 횡단 관심사로 배치, Personal Memory의 원천 |

---

## 10. 진행 상황

| 단계 | 문서 | 상태 |
|---|---|---|
| MVP — Project Brain + MCP 코어 | 이 문서 §6 | ✅ |
| Creator Mode | [03](03-CREATOR-MODE.md) | ✅ |
| Daily Brief | [04](04-DAILY-BRIEF.md) | ✅ |
| Voice | [05](05-VOICE.md) | ✅ (오디오 I/O 미검증) |
| Personal Memory | [06](06-MEMORY.md) | ✅ |
| MCP Host | [07](07-MCP-HOST.md) | ✅ |
| 네이티브 헬퍼 (상시 대기·박수) | [08](08-NATIVE-HELPER.md) | ✅ Python 쪽 / ⚠️ Swift 컴파일 미확인 |
| 오브 (부르면 반응하는 화면) | [09](09-ORB.md) | ✅ |
| Vision | — | 미착수 |
| Coding Agent | — | 미착수 |
| Plugin Architecture | 이 문서 §4 | 미착수 |

### 검증되지 않은 부분

이 저장소는 Linux 컨테이너에서 개발됐다. macOS 전용 코드는 **작성됐지만
실행 확인되지 않았다.**

- `MacSayTts` (`say`), `MacCalendarAdapter` (AppleScript), `notify` (알림 센터)
- `SoxWhisperSource` (마이크 녹음 + whisper.cpp)
- `native/junvis-mac/**.swift` — Swift 툴체인이 없어 **컴파일조차 안 해 봤다**.
  대신 계약(JSON Lines)을 고정하고 가짜 헬퍼로 Python 쪽 전 경로를 테스트했다.
- `scripts/install-launchd.sh` (문법만 확인)

전부 플랫폼 검사로 비-macOS에서는 조용히 비활성화되며, 해당 파일 상단에
그 사실을 적어 두었다.
