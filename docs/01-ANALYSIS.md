> ⚠️ **이 문서는 소스를 읽지 않고 쓴 것이다.** URL이 하나도 없는 것이 그
> 증거다. 실제로 클론해서 읽은 조사는 [10-REFERENCE-SURVEY.md](10-REFERENCE-SURVEY.md)에
> 있고, 거기서 **§2의 Open Interpreter 결론이 틀렸음**이 확인됐다.
> 라이선스 판단도 그쪽이 원문을 인용한다.

# JUNVIS — 1단계: 오픈소스 분석

> 단계: **1. 분석** (설계·구현 전)
> 조사일: 2026-08-11 / 조사 방법: 각 저장소 및 공식 문서 직접 확인
> 원칙: 복붙하지 않는다. 장점만 흡수한다.

---

## 0. 조사 요약 (한눈에)

| # | 프로젝트 | 저장소 | 언어 | 라이선스 | JUNVIS에서의 역할 | 채택 판정 |
|---|---|---|---|---|---|---|
| 1 | OpenJarvis | `open-jarvis/OpenJarvis` | Python(+Rust) | Apache-2.0 | Agent Framework / Scheduler / Learning | **설계 참조 + 부분 차용** |
| 2 | Open Interpreter | `OpenInterpreter/open-interpreter` | Rust | Apache-2.0 | Coding Agent | **개념 차용** (Claude Code 우선) |
| 3 | Browser Use | `browser-use/browser-use` | Python | MIT | Browser Agent | **의존성으로 직접 사용** |
| 4 | ScreenPipe | `mediar-ai/screenpipe` | Rust | ⚠️ 상용 소스공개 | Vision | **코드 차용 불가 / 설계만 참조** |
| 5 | Mem0 | `mem0ai/mem0` | Python/TS | Apache-2.0 | Long Memory | **의존성으로 사용 (로컬 구성)** |
| 6 | Anthropic MCP | `modelcontextprotocol/*` | 다중 SDK | MIT | Tool System | **표준으로 전면 채택** |
| 7 | Jarvis (macOS) | `isair/jarvis` | Python | ⚠️ 개인용 무료 | Voice / Wake Word | **기법만 차용 / 코드 차용 불가** |

### 이번 조사에서 나온 가장 중요한 3가지

1. **ScreenPipe는 MIT가 아니다.** Screenpipe Commercial License(소스공개)이며 개인·비상업 용도만 무료다. 코드를 JUNVIS에 가져오면 라이선스 위반이 될 수 있다. → **아키텍처 아이디어만 참조하고, Vision 계층은 자체 구현한다.**
2. **Open Interpreter는 우리가 아는 그 프로젝트가 아니다.** 현재 메인은 OpenAI Codex를 포크한 **Rust 재작성판**(저비용 모델 최적화, 네이티브 샌드박스, ACP 호환)이고, 기존 Python 버전은 커뮤니티 포크로 분리됐다. → **Python 라이브러리로 임포트하던 옛 방식은 성립하지 않는다.**
3. **isair/jarvis도 개인용 무료 라이선스**다. 상업적 사용은 개발자 문의 필요. → **Wake Word·Intent Judge·Smart Tool Selection 같은 "기법"만 차용하고 코드는 가져오지 않는다.**

---

## 1. OpenJarvis — Agent Framework / Memory / Tool / Plugin / Scheduler / Learning

**출처:** Stanford Scaling Intelligence Lab + Lambda / Apache-2.0 / Python ≥3.10 + Rust 확장

### 핵심 구조
- 5개 핵심 추상: **Intelligence, Engine, Agentic Logic, Memory, Learning** — trace 기반 피드백으로 연결
- 실행 모드 3종: **on-demand / scheduled / continuous**
- 내장 에이전트 8종: `morning_digest`(예약), `deep_research`·`orchestrator`·`native_react`·`native_openhands`·`simple`(온디맨드), `monitor_operative`·`operative`(상시)
- 스케줄러 데몬이 SQLite의 등록 태스크를 읽어 시각에 맞춰 발화
- Tool = **agentskills.io** 표준 Skill + MCP 지원
- 로컬 모델(Ollama) 우선, 필요 시 클라우드 엔진 폴백
- 25+ 데이터 소스, 32+ 메시징 채널

| 항목 | 내용 |
|---|---|
| **장점** | ① JUNVIS와 목표가 가장 가까움(로컬 우선 개인 AI OS) ② 실행 모드 3분류(on-demand/scheduled/continuous)가 명확하고 그대로 쓸 만함 ③ **trace-driven learning** — 실행 로그를 학습 신호로 되먹임하는 구조가 "Personal Memory" 요구와 정확히 일치 ④ 스케줄러가 프레임워크 1급 시민(→ Daily Brief 구현의 원형) ⑤ 에너지·FLOPs·지연·비용을 1급 제약으로 평가 ⑥ Apache-2.0 이라 차용 자유 ⑦ Ollama 기본 |
| **단점** | ① 프레임워크가 크고 자체 세계관(agentskills.io)이 강해 그대로 쓰면 우리 아키텍처가 종속됨 ② Clean Architecture/DDD 관점의 계층 분리가 우리 기준과 다름 ③ macOS 전용 최적화가 아님(크로스 플랫폼 지향 → Windows/WSL 코드가 섞임) ④ 에이전트 8종이 범용이라 ZUN 브랜드/콘텐츠 같은 개인 도메인은 비어 있음 ⑤ 연구 프로젝트 성격상 API 안정성 보장 약함 |
| **가져올 기능** | • 실행 모드 3분류(on-demand / scheduled / continuous)<br>• **Trace 스키마 + 학습 루프** (모든 실행을 trace로 남기고 → 개인화 신호로 사용)<br>• SQLite 기반 스케줄러 데몬 설계<br>• Engine 추상화(로컬↔클라우드 모델 폴백)<br>• 비용/지연을 1급 제약으로 두는 평가 관점 |
| **가져오면 안 되는 부분** | • 프레임워크 전체 임포트 (종속성 폭발, 우리 계층 구조 붕괴)<br>• agentskills.io 스킬 포맷을 우리 1급 표준으로 삼는 것 → **우리 표준은 MCP**<br>• Windows/WSL 지원 코드<br>• 내장 에이전트 8종 그대로 복사<br>• 자체 메시징 채널 32종 (우리는 macOS 네이티브 UX 우선) |
| **통합 방법** | OpenJarvis를 **의존성이 아니라 "설계 교과서"로 사용**한다. `core/agent`의 실행 모드 3분류와 `core/trace`의 trace 스키마를 우리 도메인 언어로 재정의해 이식한다. 스케줄러는 macOS `launchd` + SQLite 조합으로 자체 구현(데몬을 파이썬 프로세스로 상주시키지 않음). Engine 추상화는 우리 `ModelPort` 인터페이스로 흡수해 Ollama/Claude를 같은 포트 뒤에 둔다. |

---

## 2. Open Interpreter — Coding Agent

**출처:** `OpenInterpreter/open-interpreter` / Apache-2.0 / **Rust (OpenAI Codex 포크)**

### 현재 상태 (중요)
- 저비용 모델에 최적화된 **코딩 에이전트 하네스**. TUI(`i` 명령)로 동작
- macOS/Linux/Windows **네이티브 샌드박스** 안에서 명령 실행 + 승인(approvals) 체계
- 세션 내 `/harness`, `/model` 로 하네스·모델 교체
- Codex SDK 프로토콜 및 **ACP(Agent Client Protocol)** 호환
- 모든 모델이 UI를 조작·테스트하게 해주는 QA 스킬(agent-browser, trycua 연동)
- 기존 Python 구현은 **커뮤니티 포크로 이관**

| 항목 | 내용 |
|---|---|
| **장점** | ① **네이티브 샌드박스 + 승인 게이트**라는 안전 모델이 명확 — 코드 실행 에이전트의 정석 ② 하네스/모델을 런타임에 교체하는 추상화가 좋음(로컬 저비용 모델 대응) ③ ACP 호환 → 에디터·클라이언트와 표준으로 연결 가능 ④ Apache-2.0 ⑤ Rust라 단일 바이너리 배포·성능 유리 |
| **단점** | ① Rust 재작성으로 **Python에서 라이브러리처럼 임포트할 수 없음** — 프로세스/프로토콜로만 연동 ② Codex 포크라 상류 변화에 끌려다님 ③ 우리에겐 **Claude Code라는 더 강한 코딩 에이전트가 이미 있음** → 기능 중복 ④ TUI 중심이라 JUNVIS의 음성/데몬 UX와 결이 다름 ⑤ 옛 Python 버전 자료가 인터넷에 널려 있어 잘못된 전제를 만들기 쉬움 |
| **가져올 기능** | • **승인 게이트 모델**: 위험 등급별 자동실행/확인요구/거부 정책<br>• 네이티브 샌드박스로 실행 격리한다는 원칙<br>• 하네스·모델 런타임 스위칭 추상화<br>• **ACP를 코딩 에이전트 연동 프로토콜로 채택**한다는 발상 |
| **가져오면 안 되는 부분** | • Rust 코드베이스 포크 (유지보수 부담 폭증)<br>• `--auto-run` 류의 무승인 실행을 기본값으로 두는 것<br>• 자체 TUI를 JUNVIS의 메인 인터페이스로 삼는 것<br>• 옛 Python `interpreter` 패키지 의존 (사실상 유지보수 이관됨) |
| **통합 방법** | JUNVIS는 코딩 에이전트를 **직접 만들지 않는다.** `CodingAgentPort` 인터페이스를 정의하고 **기본 어댑터를 Claude Code**로, 대안 어댑터를 Open Interpreter(별도 프로세스, ACP/CLI 경유)로 붙인다. Open Interpreter에서 실제로 가져오는 것은 코드가 아니라 **위험도 기반 승인 정책 테이블**이며, 이를 JUNVIS 전역 `PolicyEngine`으로 일반화해 파일쓰기·셸·브라우저·시스템제어에 공통 적용한다. |

---

## 3. Browser Use — Browser Agent

**출처:** `browser-use/browser-use` / **MIT** / Python + Playwright

### 핵심 구조
- **Agent**(의사결정) / **Controller·Registry**(도구 등록) / **DOM Extraction**(페이지→LLM 입력 변환) / **BrowserSession**(상태 유지)
- 스크린샷 렌더링 없이 DOM을 LLM 친화 구조로 변환해 상호작용 요소 식별
- `@tools.action(description=...)` 데코레이터로 커스텀 액션 확장
- OpenAI/Anthropic/Google + **Ollama 로컬 모델** 지원, headless/headed, CDP 원격 브라우저
- 클라우드 유료 티어(프록시 로테이션, CAPTCHA)가 난이도 높은 작업에서 OSS보다 우수

| 항목 | 내용 |
|---|---|
| **장점** | ① **MIT** — 7종 중 라이선스가 가장 깨끗 ② 액션 레지스트리 확장 모델이 우리 Plugin Architecture와 궁합이 좋음 ③ DOM→텍스트 변환 품질이 검증되어 있어 우리가 직접 만들 이유가 없음 ④ Playwright 기반이라 macOS에서 안정 ⑤ Ollama 지원으로 로컬 우선 원칙 유지 가능 ⑥ Python 라이브러리로 **그대로 임포트 가능** |
| **단점** | ① Chrome 프로세스가 메모리를 많이 먹고 병렬 확장 시 인프라 관리 필요 ② 토큰 소모가 작업 복잡도에 따라 급증 ③ CAPTCHA·스텔스는 사실상 유료 클라우드 기능 ④ 자체 `bu-*` 모델로 유도하는 상업적 인센티브 존재 ⑤ 에이전트 루프를 자체적으로 돌리므로 우리 Orchestrator와 **제어권이 충돌**할 수 있음 |
| **가져올 기능** | • 라이브러리 자체를 **직접 의존성으로 사용** (재구현 금지)<br>• Registry + 데코레이터 확장 패턴 → JUNVIS 플러그인 등록 방식의 참고 모델<br>• DOM 직렬화 결과를 Vision 대체 신호로 활용<br>• 브라우저 세션 재사용(로그인 상태 유지) 개념 |
| **가져오면 안 되는 부분** | • 클라우드 티어·`bu-*` 전용 모델 종속<br>• Browser Use의 Agent 루프를 JUNVIS 최상위 오케스트레이터로 삼는 것 → **JUNVIS Orchestrator가 상위, Browser Use는 하위 도구**<br>• CAPTCHA 우회·스텔스 기능 (정책적으로도 배제)<br>• 무제한 병렬 브라우저 실행 |
| **통합 방법** | `features/browser` 안에서만 Browser Use를 알게 한다. 도메인 계층은 `BrowserAgentPort`(작업 서술 → 결과)만 보고, 인프라 계층 `BrowserUseAdapter`가 실제 라이브러리를 감싼다. **한 번의 호출 = 하나의 서브태스크**로 제한해 토큰 폭주를 막고, 진행 상황은 Event Bus로 `browser.step` 이벤트를 발행해 상위 오케스트레이터가 취소·개입할 수 있게 한다. 브라우저 프로필은 전용 1개만 상주시킨다. |

---

## 4. ScreenPipe — Vision

**출처:** `mediar-ai/screenpipe` / **⚠️ Screenpipe Commercial License (source-available)** / Rust

### 핵심 구조 (배울 점이 많음)
- **이벤트 기반 캡처** — 상시 녹화가 아니라 앱 전환·클릭·타이핑 중단·스크롤 등 의미 있는 변화 시점에만 캡처
- 텍스트 추출은 **OS 접근성 트리(Accessibility Tree) 우선**, 실패 시 OCR(macOS는 Apple Vision) 폴백
- 오디오: Whisper Large-V3-Turbo 로컬 + 화자 분리(diarization)
- 저장: **SQLite + FTS5 전문검색**, 프레임은 JPEG (8시간 ≈ 300MB, 상시녹화 대비 1/7)
- **Pipe** = 마크다운 파일로 정의하는 예약 AI 에이전트, YAML frontmatter로 앱/윈도우/콘텐츠/기간 **권한을 선언적으로 제한**
- localhost:3030 REST API + SQL 직접 접근, MCP 서버 제공
- 비용: CPU 5–10%, RAM 0.5–3GB, 디스크 월 5–20GB

| 항목 | 내용 |
|---|---|
| **장점** | ① **이벤트 기반 캡처**라는 발상 자체가 최고의 자산 — 비용을 한 자릿수 배로 줄임 ② **접근성 트리 우선 / OCR 폴백** 전략이 정확도·비용 모두에서 우월 ③ SQLite+FTS5라는 검소한 저장 설계 ④ Pipe의 **선언적 데이터 권한(frontmatter)** 모델이 프라이버시 설계의 모범 ⑤ macOS TCC 권한·오디오 제외 목록 등 실전 노하우 ⑥ MCP 서버를 이미 제공 |
| **단점** | ① **라이선스가 치명적** — 개인·비상업만 무료, 상업 이용 유료($25~150/seat/월). 코드 차용 시 법적 위험 ② 서명된 데스크톱 앱은 PostHog 분석·Sentry 크래시 리포트가 **기본 활성** (로컬 우선을 표방하나 텔레메트리 존재) ③ 디스크 월 5–20GB는 개인 기기에 부담 ④ 화면 전체를 기록하므로 **민감정보 유출면이 가장 넓은 컴포넌트** ⑤ Rust 바이너리라 우리 프로세스와 분리 운영 필요 |
| **가져올 기능** | 코드가 아니라 **설계 원칙만**:<br>• 이벤트 기반(변화 감지) 캡처 트리거<br>• 접근성 트리 우선 → OCR 폴백 파이프라인<br>• SQLite + FTS5 + 프레임 파일 분리 저장<br>• **선언적 권한 필터**(앱/윈도우/콘텐츠/기간)를 Vision 접근의 1급 개념으로<br>• 보존 기간(TTL) + 자동 정리 |
| **가져오면 안 되는 부분** | • **소스 코드 일체** (라이선스 위반 위험)<br>• 상시 24/7 전체 녹화 기본값<br>• 텔레메트리(PostHog/Sentry) 패턴<br>• 클라우드 동기화<br>• 유료 티어 종속 |
| **통합 방법** | ScreenPipe를 **의존하지 않는다.** `features/vision`을 macOS 네이티브로 자체 구현한다: ScreenCaptureKit(캡처) + Accessibility API(텍스트) + **Apple Vision Framework(온디바이스 OCR, 무료·오프라인)**. 캡처는 기본 **OFF**이며 사용자가 명시적으로 켠 앱 화이트리스트에서만 동작한다(전체 기록이 아니라 선택 기록). 저장은 SQLite+FTS5, 기본 보존 7일, 민감 앱(1Password·은행·메신저) 영구 차단 목록을 코드에 하드코딩한다. Vision은 **Pull 방식**(에이전트가 물어볼 때만 조회)으로 두고 Push 스트림은 만들지 않는다. |

---

## 5. Mem0 — Long Memory

**출처:** `mem0ai/mem0` / Apache-2.0 / Python + TypeScript / 63k+ stars

### 핵심 구조
- **Multi-Level Memory**: User / Session / Agent 상태를 분리 보존
- 2026-04 알고리즘: **단일 패스 추출**(LLM 1회 호출), **엔티티 링킹**, **다중 신호 검색**(시맨틱 + BM25 + 엔티티 부스팅), **시간 추론**
- 벤치마크: LoCoMo 92.5, LongMemEval 94.4, BEAM(1M) 64.1, p50 0.88–1.09s
- 백엔드: 기본 OpenAI `gpt-5-mini` + `text-embedding-3-small`, 벡터스토어 Qdrant 등
- 배포: 라이브러리 / 셀프호스트(Docker Compose) / 클라우드
- Claude Code·Cursor용 에이전트 스킬 및 CLI 제공

| 항목 | 내용 |
|---|---|
| **장점** | ① 장기 기억 문제를 **검색 문제로 정확히 정식화** — 우리가 처음부터 만들 이유 없음 ② 시맨틱+BM25+엔티티 하이브리드 검색은 직접 구현 시 몇 주 걸릴 품질 ③ **시간 추론**이 "언제 무엇을 했나"류 개인 기억에 필수 ④ User/Session/Agent 분리가 JUNVIS의 다중 에이전트 구조와 정확히 맞음 ⑤ Apache-2.0 ⑥ 로컬 임베딩·로컬 LLM으로 교체 가능 |
| **단점** | ① **기본값이 OpenAI API** — 그대로 쓰면 개인 기억이 외부로 나감(로컬 우선 원칙 위반) ② 매니지드 플랫폼이 OSS SDK보다 성능 좋다고 공식 언급 → OSS는 벤치마크 수치 그대로 안 나옴 ③ 기억 추출이 LLM 호출이라 **쓰기 비용·지연** 발생 ④ 하이브리드 검색 품질이 임베딩 모델에 민감(Qwen 600M+ 권장) ⑤ 셀프호스트 수동 설정 필요 |
| **가져올 기능** | • 라이브러리를 **로컬 구성으로 의존성 채택**(Ollama LLM + 로컬 임베딩 + 로컬 Qdrant)<br>• Multi-Level(User/Session/Agent) 메모리 스코프 개념<br>• 다중 신호 검색(시맨틱+키워드+엔티티) 전략<br>• 시간 추론 기반 회상<br>• 단일 패스 추출로 쓰기 비용 억제 |
| **가져오면 안 되는 부분** | • **기본 OpenAI 백엔드 설정 그대로 사용** (반드시 로컬로 오버라이드)<br>• Mem0 Cloud / 매니지드 플랫폼<br>• 벤치마크 수치를 우리 성능 목표로 그대로 인용<br>• Mem0를 유일한 기억 저장소로 삼는 것 (구조적 기억은 우리 DB가 소유) |
| **통합 방법** | 기억을 **두 층으로 분리**한다. ① **구조적 기억**(프로젝트·커밋·콘텐츠 캘린더·습관 통계)은 JUNVIS 자체 SQLite 스키마가 **소유권**을 갖는다 — 정확성이 중요하고 벡터검색이 부적합. ② **서술적 기억**(대화, 선호, 일화)은 Mem0에 위임한다. 도메인은 `MemoryPort`만 보고, `Mem0Adapter`가 로컬 Ollama·로컬 임베딩·로컬 Qdrant로 구성된 Mem0를 감싼다. 기억 쓰기는 동기 경로에서 빼고 **Event Bus 구독자가 비동기로 처리**해 응답 지연을 만들지 않는다. |

---

## 6. Anthropic MCP — Tool System

**출처:** `modelcontextprotocol/modelcontextprotocol` / **MIT** / 스펙 개정 **2025-11-25**

### 핵심 구조
- 역할 분리: **Host**(앱) — **Client**(1:1 연결) — **Server**(도구 제공자)
- 서버 프리미티브: **Tools**(모델이 호출), **Resources**(컨텍스트 데이터), **Prompts**(사용자 선택 템플릿)
- 클라이언트 프리미티브: **Sampling**(서버가 모델 추론 요청), **Elicitation**(서버가 사용자에게 추가 입력 요청), **Roots**(파일시스템 경계)
- 전송: **stdio**(로컬), **Streamable HTTP**(원격) / 원격은 OAuth 2.1 계열 인가
- 다국어 공식 SDK (TypeScript, Python, Java, Kotlin, C#, Go, Swift 등)

| 항목 | 내용 |
|---|---|
| **장점** | ① **표준이다.** Claude Code·Cursor·VSCode·ScreenPipe 등 우리 환경 전체가 이미 말하는 언어 ② MIT ③ Host/Client/Server 분리가 **Clean Architecture 경계와 자연스럽게 일치** ④ stdio 전송은 macOS 로컬 도구에 이상적(네트워크 노출 0) ⑤ Roots·Elicitation이 권한·사용자 확인을 **프로토콜 수준에서** 제공 ⑥ 한 번 MCP 서버로 만들면 JUNVIS 밖(Claude Code 등)에서도 재사용 |
| **단점** | ① 스펙이 빠르게 개정됨(버전 협상 필수) ② 도구가 많아지면 **컨텍스트 오염(context rot)** — 모든 도구 정의를 프롬프트에 넣을 수 없음 ③ stdio 서버는 프로세스 수만큼 자원 소모 ④ 원격 서버 인가(OAuth 2.1) 구현 부담 ⑤ 프로토콜 자체는 권한 정책을 강제하지 않음 → 호스트가 책임 |
| **가져올 기능** | • **JUNVIS의 유일한 도구 표준으로 채택** (자체 도구 포맷 만들지 않음)<br>• Tools/Resources/Prompts 3분류를 도메인 언어로 사용<br>• Roots로 파일 접근 경계 강제<br>• **Elicitation을 사용자 확인(HITL) 기본 통로**로 사용<br>• Sampling으로 서버가 로컬 모델을 역호출 |
| **가져오면 안 되는 부분** | • 모든 MCP 서버를 부팅 시 전부 상시 기동 (자원 낭비 + 컨텍스트 오염)<br>• 도구 정의 전체를 매 요청 프롬프트에 주입<br>• 검증 없이 서드파티 MCP 서버 신뢰<br>• 원격 HTTP 서버를 초기 범위에 포함 (로컬 stdio로 충분) |
| **통합 방법** | JUNVIS는 **MCP Host**가 된다. `core/mcp`에 레지스트리를 두고 서버를 **지연 기동(lazy spawn) + 유휴 시 종료**한다. 도구 선택은 7번 항목의 임베딩 기반 필터를 적용해 요청당 상위 N개만 주입한다. 동시에 JUNVIS의 개인 도메인 기능(Project Brain, ZUN 콘텐츠, Personal Memory)은 **역으로 MCP 서버로도 노출**해 Claude Code에서 그대로 쓰게 한다 — 이게 JUNVIS를 "앱"이 아니라 "OS"로 만드는 핵심이다. 서드파티 서버는 `PolicyEngine`의 화이트리스트를 통과해야만 등록된다. |

---

## 7. Jarvis AI Assistant (macOS) — Voice / Wake Word

**출처:** `isair/jarvis` / **⚠️ 개인 사용 무료, 상업 이용은 개발자 문의** / Python / macOS 우선 개발

> 후보군 중 `AdelElo13/Open-Jarvis`(Swift 네이티브)는 현재 접근 불가(404), `cgtarmenta/jarvis`(Rust, ~4MB)와 `Priler/jarvis`(Rust+Tauri)도 있으나, **macOS 우선 + 메모리 + MCP 통합**까지 갖춘 `isair/jarvis`가 우리 목표와 가장 가깝다.

### 핵심 구조
- **Wake word**: 문장 어디에서든 "Jarvis"를 인식 + 소형 모델 기반 **LLM Intent Judge**로 "실제 명령 vs 잡음/에코" 분류 + **자기 음성 에코 필터링**
- **STT**: Whisper(tiny~large-v3-turbo) / **TTS**: Piper(~60MB, 로컬) 또는 Chatterbox(음성 클로닝)
- **LLM**: Ollama 기본, 모든 OpenAI 호환 서버(LM Studio, llama.cpp, vLLM, MLX 등)
- **메모리**: 자기조직화 **Knowledge Graph Memory** + **memory digest**(회상 내용을 짧게 압축 후 주입 → 소형 모델의 프롬프트 길이 열화 방지)
- **도구**: **Smart Tool Selection** — 임베딩 기반 관련도 필터로 무제한 MCP 도구를 컨텍스트 오염 없이 사용 + **Task-list Planner**로 다단계 분해
- 한계: 음성 전용(텍스트 채팅 없음), macOS 26(Tahoe)에서 pynput 문제로 받아쓰기 불가, 무음 구간 Whisper 환각

| 항목 | 내용 |
|---|---|
| **장점** | ① **Wake word 오탐 문제의 실전 해법**(Intent Judge + 에코 필터)이 가장 값진 자산 ② **memory digest 압축 주입** — 로컬 소형 모델을 쓰는 우리에게 결정적 ③ **Smart Tool Selection**이 MCP 컨텍스트 오염 문제의 직접적 답 ④ 완전 로컬·오프라인 동작 ⑤ Piper TTS가 60MB로 가볍고 품질 좋음 ⑥ macOS 우선 개발이라 우리 환경과 동일 |
| **단점** | ① **라이선스가 개인용 한정** — 코드 차용 불가 ② 음성 전용 UI(텍스트 채팅 없음) → JUNVIS엔 부적합 ③ Whisper 무음 환각, 정지 명령이 에코로 걸러지는 버그 ④ pynput 의존이 최신 macOS에서 깨짐 → **네이티브 API를 써야 한다는 교훈** ⑤ 지식그래프 메모리가 Mem0와 역할 중복 ⑥ 1인 개발 프로젝트 지속성 리스크 |
| **가져올 기능** | 코드가 아니라 **기법만**:<br>• Wake word → **Intent Judge(소형 로컬 모델) → 실행** 2단 게이트<br>• 자기 음성 에코 필터링<br>• **memory digest**: 회상 결과를 압축해 주입<br>• **임베딩 기반 도구 사전선별**(요청당 상위 N개 MCP 도구만)<br>• Task-list Planner(다단계 분해)<br>• STT/TTS를 교체 가능한 어댑터로 두는 구조 |
| **가져오면 안 되는 부분** | • **소스 코드** (라이선스)<br>• 음성 전용 인터페이스 (JUNVIS는 음성·텍스트·Raycast 병행)<br>• `pynput` 등 비네이티브 입력 훅 → **Hammerspoon/네이티브 API 사용**<br>• 자체 Knowledge Graph 메모리 (Mem0와 중복 → Mem0로 일원화)<br>• Whisper 무음 구간 무보정 사용 |
| **통합 방법** | `features/voice`를 자체 구현한다. Wake word는 macOS 온디바이스 음성 API 또는 경량 KWS 모델로 1차 필터 → **Ollama 소형 모델(예: 3B 이하) Intent Judge**로 2차 판정 → 통과 시에만 Event Bus에 `voice.command` 발행. TTS는 `TtsPort` 뒤에 macOS `AVSpeechSynthesizer`(기본, 무설치)와 Piper(고품질) 두 어댑터를 둔다. 전역 단축키는 pynput이 아니라 **Hammerspoon**으로 처리해 macOS 버전 종속을 피한다. memory digest와 임베딩 도구 필터는 각각 `core/memory`, `core/mcp`의 **필수 구성요소**로 승격한다. |

---

## 8. 교차 분석 — 겹치는 책임 정리

같은 일을 하는 컴포넌트가 여러 개다. 중복을 남기면 아키텍처가 무너지므로 **소유권을 하나로 확정**한다.

| 책임 | 후보 | **확정 소유자** | 근거 |
|---|---|---|---|
| 장기 기억 | OpenJarvis Memory, Mem0, isair KG Memory | **Mem0(서술적) + 자체 SQLite(구조적)** | Mem0가 검색 품질 최고, 구조적 데이터는 벡터검색 부적합 |
| 도구 표준 | agentskills.io, Browser Use Registry, MCP | **MCP 단일 표준** | 우리 환경 전체가 이미 MCP를 말함 |
| 스케줄러 | OpenJarvis 데몬, ScreenPipe Pipes | **자체 구현 + launchd** | macOS 네이티브가 더 안정적, 파이썬 상주 데몬 회피 |
| 코드 작성 | Open Interpreter, Claude Code | **Claude Code (1순위)** | 이미 사용 중이고 더 강력, OI는 대안 어댑터 |
| 화면 이해 | ScreenPipe | **자체 구현(ScreenCaptureKit+Vision)** | 라이선스 위험 회피 + 비용 통제 |
| 브라우저 | Browser Use | **Browser Use 직접 사용** | MIT + 품질 검증됨, 재구현 이유 없음 |
| 음성 | isair/jarvis | **자체 구현(기법만 차용)** | 라이선스 + 음성전용 UI 부적합 |
| 학습/개인화 | OpenJarvis trace | **자체 Trace 스키마** | 도메인(ZUN 브랜드 등)이 우리 고유 |

## 9. 라이선스 리스크 요약

| 프로젝트 | 라이선스 | 코드 차용 | 조치 |
|---|---|---|---|
| OpenJarvis | Apache-2.0 | ✅ 가능 | 설계 참조 위주, 차용 시 NOTICE 표기 |
| Open Interpreter | Apache-2.0 | ✅ 가능 | 프로세스 연동만 |
| Browser Use | MIT | ✅ 가능 | 의존성으로 사용 |
| **ScreenPipe** | **상용 소스공개** | ❌ **불가** | **코드 미사용, 아이디어만 참조** |
| Mem0 | Apache-2.0 | ✅ 가능 | 의존성으로 사용 |
| MCP | MIT | ✅ 가능 | 표준 채택 |
| **isair/jarvis** | **개인용 무료** | ❌ **불가** | **기법만 차용, 자체 구현** |

> JUNVIS가 개인용에 머무는 한 ScreenPipe·isair/jarvis를 **도구로 쓰는 것**은 문제없다. 금지되는 것은 **소스를 우리 저장소에 복제·파생**하는 것이다. 향후 공개·상업화 가능성을 고려해 처음부터 자체 구현한다.

---

## 10. 1단계 결론 — 설계로 넘길 확정 사항

1. **JUNVIS는 MCP Host다.** 도구 표준은 MCP로 단일화하고, 우리 개인 도메인 기능도 역으로 MCP 서버로 노출한다.
2. **기억은 2층 구조다.** 구조적 기억은 우리가 소유(SQLite), 서술적 기억은 Mem0(전부 로컬 구성)에 위임한다.
3. **실행 모드는 3종이다.** on-demand / scheduled / continuous — OpenJarvis 분류를 채택.
4. **모든 실행은 Trace를 남긴다.** Trace가 곧 Personal Memory·개인화·Daily Brief의 원천이다.
5. **Vision은 자체 구현하고 기본 OFF다.** 이벤트 기반 + 접근성 트리 우선 + 화이트리스트 + TTL.
6. **위험 행위는 PolicyEngine을 통과해야 한다.** 승인 게이트를 전역 개념으로 일반화한다.
7. **컨텍스트 오염 대책은 필수 구성요소다.** 임베딩 기반 도구 선별 + memory digest 압축.
8. **외부 라이브러리는 전부 Port 뒤에 둔다.** 도메인은 Mem0·Browser Use·Ollama·Claude Code를 알지 못한다.
9. **macOS 네이티브 API를 우선한다.** launchd, ScreenCaptureKit, Vision, Accessibility, Hammerspoon.
10. **복붙은 없다.** 7종 중 코드로 직접 의존하는 것은 **Browser Use / Mem0 / MCP SDK** 3개뿐이다.
