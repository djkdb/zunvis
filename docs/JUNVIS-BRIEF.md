# JUNVIS — 프로젝트 브리프 (작업 대기 중)

> 상태: **대기**. 분석/설계/구현은 다음 주에 시작한다.
> 이 문서는 사용자가 지시한 원본 요구사항을 보존한 것이다. 작업 재개 시 이 파일부터 읽는다.

---

## 0. 대전제

우리는 새로운 AI 비서를 만드는 것이 아니다.

GitHub의 여러 최고 수준 오픈소스를 분석하여 **장점만 가져와** 하나의 개인 AI OS인 **"JUNVIS"** 를 개발한다.

---

## 1. 개발 환경

- macOS (Apple Silicon)
- Claude Code
- VSCode
- Ollama
- MCP
- GitHub
- Raycast
- Hammerspoon
- AppleScript

Windows 기능은 구현하지 않는다. **macOS 최우선 설계.**

---

## 2. 먼저 해야 할 일 — 오픈소스 분석

다음 오픈소스를 모두 분석한다.

| # | 프로젝트 | 역할 |
|---|---|---|
| 1 | OpenJarvis | Agent Framework / Memory / Tool / Plugin / Scheduler / Learning |
| 2 | Open Interpreter | Coding Agent |
| 3 | Browser Use | Browser Agent |
| 4 | ScreenPipe | Vision |
| 5 | Mem0 | Long Memory |
| 6 | Anthropic MCP | Tool System |
| 7 | Jarvis AI Assistant (macOS) | Voice / Wake Word |

각 프로젝트마다 아래 항목을 **표로** 정리한다.

- 장점
- 단점
- 가져올 기능
- 가져오면 안 되는 부분
- 우리 프로젝트에 어떻게 통합할지

---

## 3. 그 후

최적의 아키텍처를 **새로** 설계한다.

- 기존 프로젝트를 그대로 복붙하지 않는다.
- 각 프로젝트의 장점만 흡수한다.

---

## 4. 최종 목표 — JUNVIS

Iron Man JARVIS처럼:

- 기억한다
- 말한다
- 계획한다
- 코드 작성한다
- 컴퓨터를 제어한다
- 프로젝트를 이해한다
- GitHub를 이해한다
- MCP를 사용한다
- 여러 Agent가 협업한다

---

## 5. 반드시 적용할 원칙

- Feature Folder
- Clean Architecture
- SOLID
- DDD
- Plugin Architecture
- Event Bus

---

## 6. 작업 방식

모든 작업은 다음 순서로 진행한다.

1. 분석
2. 설계
3. 구현
4. 테스트
5. 리팩토링

**기존 구조를 먼저 이해하기 전에는 절대 코드를 수정하지 않는다.**

작업을 작은 단위의 체크리스트(Task)로 나누고, 각 단계마다 결과를 요약한 뒤 다음 단계로 진행한다.

---

# PERSONAL CONTEXT

JUNVIS는 사용자를 장기적으로 이해하는 AI다.
사용자는 단순한 개발자가 아니다. 사용자의 **모든 디지털 활동**을 도와주는 AI OS를 목표로 한다.

## 1. Software Development

- 다양한 AI 웹앱 개발
- GitHub 프로젝트 관리
- Claude Code 활용
- MCP 활용
- macOS 개발환경
- VSCode
- Ollama
- Cursor
- AI Agent 개발

## 2. ZUN Instagram

사용자는 **"ZUN"** 이라는 개발자 브랜드를 운영한다. JUNVIS는 이 브랜드를 항상 이해하고 있어야 한다.

도와줄 수 있는 업무:

- 릴스 아이디어 생성
- 캐러셀 기획
- 썸네일 문구 작성
- Hook 제작
- 캡션 작성
- 댓글 전략
- 업로드 시간 추천
- 바이럴 아이디어
- 시리즈 기획
- 콘텐츠 캘린더
- 인스타 분석
- 성장 전략

사용자의 콘텐츠 성향을 학습한다. 예: AI / 바이브 코딩 / Claude Code / MCP / 개발 생산성 / 새로운 웹앱 / 개발 브이로그 / 프로젝트 제작기

## 3. Project Brain

JUNVIS는 사용자의 GitHub 프로젝트를 모두 기억한다.

프로젝트마다 README, 기술스택, 목적, 아키텍처, TODO, 최근 작업, 최근 Commit, Issue 를 기억한다.

프로젝트를 열면 자동으로 Context를 불러온다.

## 4. Content Assistant

새로운 프로젝트를 만들면 자동으로 제안한다.

- "이 프로젝트 릴스 만들까?"
- "캐러셀도 만들까?"
- "GitHub README 개선할까?"
- "Product Hunt 올릴까?"

## 5. Personal Memory

JUNVIS는 사용자의 다음을 학습한다.

- 자주 쓰는 프롬프트
- 자주 사용하는 모델
- 자주 쓰는 MCP
- 개발 습관
- 콘텐츠 제작 습관
- GitHub 사용 패턴
- 작업 시간
- 선호하는 UI

## 6. Daily Brief

매일 시작할 때 브리핑한다.

- 오늘 일정
- GitHub 알림
- 해야 할 작업
- ZUN 콘텐츠 업로드 여부
- 진행 중인 프로젝트
- 최근 아이디어
- AI 최신 소식 (개발과 콘텐츠 제작에 도움이 되는 내용 중심)

## 7. Creator Mode

사용자가 "릴스 하나 만들자"라고 하면 자동으로 한 번에 생성한다.

- 주제 선정
- Hook 작성
- 대본 작성
- 장면 구성
- B-roll 아이디어
- 캡션 작성
- 해시태그
- 썸네일 문구
- 댓글 유도 문구

---

## 최종 목표 (역할 정의)

JUNVIS는 '개발자 AI 비서'가 아니라
**'나의 CTO + 콘텐츠 매니저 + 프로젝트 매니저 + AI 비서'** 역할을 수행한다.

모든 제안은 사용자의 장기 목표(개발, 프로젝트, ZUN 브랜드 성장)를 기준으로 우선순위를 판단한다.
