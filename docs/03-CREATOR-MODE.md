# JUNVIS — Creator Mode 설계

> 단계: **설계** (MVP 이후 두 번째 Bounded Context)
> 선행: `docs/02-ARCHITECTURE.md` / MVP(Project Brain + MCP 코어) 완료
> 목표: "릴스 하나 만들자" 한 마디로 9개 구성요소를 한 번에 생성한다

---

## 0. 왜 이걸 먼저 만드는가

Daily Brief보다 Creator Mode를 먼저 만드는 이유는 두 가지다.

1. **ModelPort를 세우게 된다.** 지금까지 JUNVIS는 LLM을 한 번도 부르지 않았다. Creator Mode는 LLM 없이 성립하지 않으므로 `core/model`을 만들 수밖에 없고, 이 조각은 Daily Brief·Voice·Agent가 전부 기다리고 있다.
2. **Event Bus 훅이 이미 있다.** `project.registered`는 MVP에서 이미 발행되고 있다. `creator`가 여기 붙는 순간, 설계 §3에서 약속한 "project_brain은 creator의 존재를 모른다"가 실제로 증명된다.

---

## 1. Bounded Context 경계

| 항목 | 내용 |
|---|---|
| **책임** | ZUN 브랜드 콘텐츠의 착상 → 생성 → 발행 기록 |
| **Aggregate Root** | `ContentIdea` |
| **다른 Context와의 관계** | `project_brain`의 **이벤트만 구독**한다. 프로젝트 컨텍스트는 `ProjectContextPort`로 받으며, 그 구현은 조립 루트가 끼운다 |
| **공개하는 것** | `contracts.py`의 `ContentSummary`와 토픽 3종 |

### 교차 임포트 규칙 (새로 강제)

`creator`는 `project_brain`의 **`contracts` 모듈만** 임포트할 수 있다. domain·application·infrastructure·interface 접근은 import-linter 계약 6번이 차단한다.

프로젝트 컨텍스트가 필요한 곳에서는 `creator/application/ports.py`의 `ProjectContextPort`를 쓰고, `apps/adapters.py`가 `LoadProjectContext`를 그 자리에 끼운다. **feature끼리 직접 연결하지 않고 조립 루트에서 만나게 하는 것**이 요점이다.

---

## 2. ModelPort — 로컬 우선을 코드로

```
ModelRequest(role=…) ──▶ ModelPort ──┬── OllamaAdapter  (기본, 로컬)
                                     ├── EchoAdapter    (테스트, 결정적)
                                     └── (향후) ClaudeAdapter
```

역할→모델 해석은 어댑터 안에 둔다. 별도의 Router 클래스를 두면 아무것도
결정하지 않는 간접층이 하나 더 생길 뿐이다.

| 역할 | 쓰임 | 기본 모델 |
|---|---|---|
| `FAST` | 분류·판정·요약. Wake word Intent Judge도 나중에 여기 붙는다 | `llama3.2:3b` |
| `DEEP` | 계획·창작·코드 | `qwen2.5:14b` |

- 모델 이름은 `JUNVIS_MODEL_FAST` / `JUNVIS_MODEL_DEEP` 환경변수로 바꾼다.
- **폴백은 자동 승격이 아니다.** 로컬이 죽으면 예외를 던지고, 클라우드로 올릴지는 정책이 정한다(설계 §5.5).
- 구조화 출력은 Ollama의 `format`에 **JSON Schema를 그대로 넘겨** 얻는다. 프롬프트로 "JSON만 주세요"라고 비는 방식은 쓰지 않는다.
- 새 의존성을 추가하지 않는다. `urllib`로 충분하다.

---

## 3. 도메인 모델

### `ReelScript` — 브리프가 요구한 9개 구성요소

브리프의 Creator Mode 항목을 그대로 값 객체로 옮긴다.

| 브리프 요구 | 필드 |
|---|---|
| 주제 선정 | `ContentIdea.topic` |
| Hook 작성 | `hook` |
| 대본 작성 | `scenes[].narration` |
| 장면 구성 | `scenes[]` (순서·비주얼·나레이션·길이) |
| B-roll 아이디어 | `broll[]` |
| 캡션 작성 | `caption` |
| 해시태그 | `hashtags[]` |
| 썸네일 문구 | `thumbnail_text` |
| 댓글 유도 문구 | `comment_bait` |

**도메인이 플랫폼 규칙을 안다.** 모델이 뭘 뱉든 여기서 걸린다.

- 캡션 2,200자 초과 → 거부 (Instagram 실제 상한)
- 해시태그 30개 초과 → 거부 (Instagram 실제 상한)
- 해시태그는 `#` 없이 저장하고 소문자로 정규화, 중복 제거
- 장면 0개 → 거부. Hook 없음 → 거부

### `ContentIdea` 상태 기계

```
SUGGESTED ──accept──▶ DRAFTED ──publish──▶ PUBLISHED
    │                    │
    └──dismiss──▶ DISMISSED ◀──dismiss──┘
```

- `SUGGESTED`: `project.registered`를 듣고 자동 생성된 제안. 아직 대본이 없다.
- `DRAFTED`: 대본이 붙었다.
- 대본 없이 `PUBLISHED`로 갈 수 없다 — 도메인 불변식.
- `DISMISSED`에는 대본을 붙일 수 없다.

### `BrandVoice` — 학습되는 ZUN 성향

브리프의 콘텐츠 성향(AI, 바이브 코딩, Claude Code, MCP, 개발 생산성, 새로운 웹앱, 개발 브이로그, 프로젝트 제작기)을 기본값으로 심고, 이후 사용자가 갱신한다. 발행 기록이 쌓이면 여기에 되먹임하는 것이 다음 단계다.

---

## 4. 이벤트

| 토픽 | 발행 시점 | 예상 구독자 |
|---|---|---|
| `content.suggested` | 새 프로젝트 감지로 제안 생성 | `brief` (오늘의 제안) |
| `content.drafted` | 대본 생성 완료 | `brief` |
| `content.published` | 발행 기록 | `memory`(성향 학습), `brief` |

그리고 `creator`가 **구독**하는 것: `project.registered` → 릴스 제안 자동 생성. 이것이 브리프의 "Content Assistant"다.

---

## 5. MCP 도구

| 도구 | 설명 | 위험도 |
|---|---|---|
| `junvis_content_create` | 주제 또는 프로젝트로 9개 구성요소를 한 번에 생성 | LOW |
| `junvis_content_list` | 상태별 콘텐츠 목록 | SAFE |
| `junvis_content_get` | 전체 대본 조회 | SAFE |
| `junvis_content_dismiss` | 제안 버리기 | LOW |
| `junvis_content_published` | 발행 기록 | LOW |
| `junvis_brand_voice` | 브랜드 성향 조회·갱신 | LOW |

---

## 6. 구현 순서

| # | 태스크 | 완료 기준 |
|---|---|---|
| C1 | `core/model` — Port·Ollama·Echo·Router | Echo로 결정적 테스트, Ollama는 HTTP 계층만 스텁 |
| C2 | creator domain | 플랫폼 규칙과 상태 기계가 단위 테스트로 검증됨 |
| C3 | creator application | Fake 생성기로 전 유스케이스 검증 |
| C4 | creator infrastructure | SQLite 왕복 + 프롬프트 조립 + JSON 파싱 |
| C5 | creator interface | MCP 도구 + `project.registered` 구독자 |
| C6 | 조립 + CLI + E2E | 실제 MCP 클라이언트로 릴스 생성 왕복 |

---

## 7. 하지 않는 것

- **Instagram API 연동.** 발행은 사람이 한다. JUNVIS는 기록만 한다.
- **자동 게시.** 브리프에 없고, 되돌릴 수 없는 외부 행위다.
- **이미지·영상 생성.** 텍스트 기획까지가 이번 범위다.
- **업로드 시간 추천의 통계 모델.** 발행 데이터가 쌓이기 전에는 근거 없는 숫자를 만들 뿐이다.
