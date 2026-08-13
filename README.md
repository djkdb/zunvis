# JUNVIS

macOS를 위한 개인 AI OS. 개발자 AI 비서가 아니라 **CTO + 콘텐츠 매니저 + 프로젝트 매니저 + AI 비서**를 목표로 한다.

> 새로운 AI 비서를 만드는 것이 아니다. 최고 수준 오픈소스를 분석해 **장점만 흡수한다.**

## 실행

Finder에서 **`JUNVIS.command`를 더블클릭**한다. 터미널이 열리고 알아서 진행한다.

```
JUNVIS  /Users/zun/dev/zunvis

1. 코드 최신화
  브랜치: main
  Already up to date.

2. 실행 환경
  준비됨: /Users/zun/dev/zunvis/.venv/bin/junvis

3. 무엇을 할까요
  1) 듣기 — 호출어 또는 박수 두 번   (기본)
  2) 오늘 브리핑
  3) 상태 점검
  4) 직접 입력 (마이크 없이 텍스트로)
  5) 그냥 종료

선택 [1]:
```

최신화 → 가상환경·의존성 설치 → 메뉴. 처음 한 번만 설치가 돌고 그 다음부터는 바로 뜬다.

- **수정 중인 파일이 있으면 최신화를 건너뛴다.** 작업을 지우지 않는다.
- 인터넷이 없어도 지금 있는 코드로 실행된다.
- PATH는 이 창 안에서만 넓힌다. 셸 설정은 건드리지 않는다.

첫 실행에서 macOS가 "확인되지 않은 개발자" 경고를 내면 파일을 **우클릭 → 열기**를 한 번 하면
그 다음부터는 더블클릭으로 열린다.

터미널에서 직접 쓰려면 아래 명령들을 그대로 쓴다.

## 지금 되는 것

### 1. Project Brain — 프로젝트를 기억한다

```bash
junvis scan ~/dev                                # git 저장소를 한 번에 전부 등록
junvis add ~/dev/zunvis --purpose "개인 AI OS"   # 하나만 등록 + git·README 자동 수집
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

### 4. Voice — 말을 건다

```
$ junvis listen
호출어: 자비스, junvis, jarvis

  (무시: 호출어 없음)
< 자비스 프로젝트 뭐 있어
> 프로젝트는 ZUNVIS입니다.
< 오늘 브리핑                        ← 후속 발화 창: 호출어 없이도 통과
> 8월 12일 브리핑입니다. 멈춰 있는 작업, ZUNVIS에 커밋되지 않은 변경. …
```

어려운 부분은 마이크를 읽는 일이 아니라 **언제 반응할지 결정하는 일**이다.

```
발화 → ① 비어 있나 → ② 내가 방금 말한 것인가(에코) → ③ 호출어가 있나
     → ④ 진짜 명령인가(소형 로컬 모델) → 실행 → 응답
```

①~③은 모델 없이 결정적으로 판정된다. ④만 `ModelRole.FAST`를 쓴다 — 이 판정에 큰 모델을 부르면 말 한마디마다 몇 초씩 기다리게 된다.

**무엇을 실행할지는 LLM이 정하지 않는다.** 아는 명령은 읽을 수 있는 규칙이 결정론적으로 실행한다. 규칙이 아무것도 못 잡았을 때만 대화로 넘어가고, 그때 모델이 하는 일은 **말로 답하는 것뿐**이다 — 브리핑을 실행할지 릴스를 만들지는 여전히 정하지 않는다. 이 구분이 무너지면 "왜 갑자기 이걸 실행했지?"를 설명할 수 없다.

```bash
junvis ask "요즘 뭐부터 하면 좋을까"    # 마이크 없이 대화
junvis ask                              # 계속 대화
```

대화의 두뇌는 **Claude Code CLI**다. 이미 깔려 있고 로그인돼 있으므로 API 키도 Ollama도 필요 없다. 없으면 Ollama로 내려간다.

```
$ junvis ask "내 프로젝트 중에 릴스 소재로 뭐가 제일 좋을까"
beta랑 alpha 둘 다 아직 초기 커밋 단계라서, 지금은 "무슨 프로젝트인지" 자체보다
어떤 과정을 보여주느냐가 콘텐츠 소재예요. … "프로젝트 목록"이라고 하시면
현재 상태 먼저 보여드릴 수 있어요.
```

대화는 **아는 것 위에서만** 한다. 프로젝트·기억·브랜드 성향을 싣고 답한다. 근거 없이 답하면 그럴듯한 거짓말을 하고, 그게 개인 비서에서 가장 나쁜 실패다.

**파일을 고칠 수 있는 도구는 막는다.** 음성은 오인식이 잦아서, "그거 지워줘"가 잘못 들리면 무엇이 지워질지 알 수 없다.

```bash
junvis listen                 # 마이크 (sox + whisper-cli 필요)
junvis listen --native        # 상시 대기 + 박수 두 번 (junvis-mac 필요)
junvis listen --stdin         # 텍스트 입력 — 어디서나 동작
junvis orb                    # 부르면 반응하는 화면
junvis say "안녕하세요"        # TTS 확인
```

`junvis orb`는 다른 창에서 띄운다. 이름을 부르면 밝아지고, 생각할 때 회전이
빨라지고, 답할 때 파동이 퍼진다. 음성에서 침묵은 "못 들었다"와 "생각 중이다"를
구분해 주지 못하는데, 화면 하나가 그 문제를 없앤다([docs/09](docs/09-ORB.md)).

**오브는 아무것도 결정하지 않는다.** 꺼도, 죽어도 명령은 그대로 실행된다.

`--native`는 **맥 내장 음성 인식**을 쓴다. brew도, Whisper 모델 내려받기도,
Swift 컴파일도 필요 없다 — PyObjC로 `SFSpeechRecognizer`를 직접 부른다.

```bash
uv pip install -e ".[mac]"    # 이게 전부
```

박수 두 번은 **이름을 부른 것과 똑같이** 다룬다 — "네?" 하고 후속 명령을 기다린다.
문 닫는 소리·말소리·울림을 걸러내는 규칙은 [12개 테스트로 검증](tests/features/voice/test_clap.py)돼 있다.
왜 Swift가 아닌지는 [docs/08 §7](docs/08-NATIVE-HELPER.md) 참고.

`--stdin`이 장식이 아닌 이유: 어떤 STT를 쓰든 파이프로 연결하면 JUNVIS가 동작한다.

> 인식은 **온디바이스로 못박는다.** 개인 기억이 애플 서버로 나가면 안 된다.

### 5. Personal Memory — 기억하고 적용한다

```bash
junvis memo "썸네일 문구는 3단어 이하로" --scope content --pin
junvis memo "Ollama를 기본 모델로 쓴다"
junvis memos 썸네일            # 회상
junvis forget 6925e492
```

기억은 쌓이기만 하면 죽은 데이터다. **바로 다음 릴스 프롬프트에 실린다.**

```
$ junvis reel "MCP 서버 만들기"
  → 프롬프트에 "사용자가 기억시킨 규칙 (반드시 지킬 것): 썸네일 문구는 3단어 이하로"
```

회상과 주입은 다른 일이다. 회상 결과를 그대로 프롬프트에 부으면 로컬 소형 모델이 무너지므로, `digest()`가 고정된 것 먼저 → 중복 제거 → 점수 순으로 예산 안에 압축한다.

**무엇을 기억하지 않을지가 더 중요하다.** 발행한 콘텐츠와 시작한 프로젝트는 자동으로 기억하지만, 음성 명령은 남기지 않는다 — 말한 것을 전부 저장하면 잡음이 신호를 덮는다.

### 6. MCP Host — 남의 도구를 쓴다

JUNVIS는 이제 양방향이다. 도구를 **제공**할 뿐 아니라 외부 MCP 서버를 **소비**한다.

```
Claude Code ──MCP──▶ JUNVIS ──MCP──▶ browser-use
                       │              notion, slack, …
                       └─ 자체 기능
```

```bash
junvis mcp add browser uvx --from browser-use python -m browser_use.mcp.server
junvis mcp tools 브라우저      # 질의와 관련된 도구만
junvis mcp call browser navigate --args '{"url":"https://…"}'
junvis mcp list
```

설정은 `~/.junvis/mcp.json`이며 **Claude Code와 같은 `mcpServers` 형식**이다. 기존 설정을 그대로 옮길 수 있다.

세 가지가 설계대로 지켜진다:

- **지연 기동** — 도구 목록은 카탈로그 캐시에서 답한다. 서버는 실제로 호출할 때만 뜨고, 유휴 5분 뒤 내려간다.
- **컨텍스트 오염 방지** — 질의와 관련된 상위 12개 도구만 고른다.
- **정책 게이트** — 외부 서버 호출은 확인이 필요하다. 설정에서 `trusted`로 표시한 서버만 자동 통과한다.

그리고 이 Host는 **다시 MCP로 노출된다.** Claude Code가 `junvis_external_tools`로 도구를 찾고 `junvis_external_call`로 부르면, 그 호출이 JUNVIS의 정책 게이트와 도구 선별을 거쳐 나간다.

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

| Project Brain | Creator | Brief · Memory | Host |
|---|---|---|---|
| `junvis_project_list` | `junvis_content_create` | `junvis_daily_brief` | `junvis_external_tools` |
| `junvis_project_context` | `junvis_content_list` | `junvis_remember` | `junvis_external_call` |
| `junvis_project_search` | `junvis_content_get` | `junvis_recall` | |
| `junvis_project_register` | `junvis_content_dismiss` | `junvis_memories` | |
| `junvis_project_remember` | `junvis_content_published` | `junvis_forget` | |
| `junvis_project_refresh` | `junvis_brand_voice` | `junvis_pin_memory` | |

세션을 시작할 때 `junvis_project_context`를 부르면 목적·기술스택·아키텍처·최근 커밋·TODO·이슈·메모·README가 토큰 예산에 맞춰 조립되어 주입된다.

## 첫 실행 (macOS)

```bash
uv venv && uv pip install -e ".[dev]"
source .venv/bin/activate

junvis setup                 # 무엇이 되고 무엇이 없는지, 뭘 치면 되는지
junvis setup --claude-code   # .mcp.json에 JUNVIS 등록
junvis add .                 # 이 프로젝트부터 기억시키기
junvis brief
```

`junvis setup`은 **아무것도 바꾸지 않는다**(`--claude-code`로 등록할 때만 예외). 점검이 무언가를 고치기 시작하면 점검을 믿을 수 없게 된다.

```
$ junvis setup
코어
  ✓ Python 3.13.1
  ✓ macOS 15.3

로컬 모델 (릴스 생성·음성 판정에 필요)
  · Ollama에 연결할 수 없습니다

할 일:
  1. Ollama 설치 후 실행: brew install ollama && ollama serve
  2. 음성 입력 도구 설치: brew install sox whisper-cpp
  ...
지금 안 해도 나머지 기능은 동작합니다.
```

Ollama 없이도 Project Brain · Daily Brief · Personal Memory · MCP Host는 전부 동작한다. 릴스 생성과 음성 판정만 모델이 필요하다.

### 선택 사항

| 환경변수 | 기본 | 뜻 |
|---|---|---|
| `JUNVIS_CALENDAR` | 꺼짐 | 브리핑에 오늘 일정 포함. AppleScript라 느리고 권한이 필요해 기본은 꺼져 있다 |
| `JUNVIS_MODEL_FAST` / `_DEEP` | `llama3.2:3b` / `qwen2.5:14b` | 쓸 Ollama 모델 |
| `JUNVIS_WHISPER_MODEL` | — | `junvis listen`의 whisper.cpp 모델 경로 |
| `JUNVIS_WAKE_WORDS` | `자비스,junvis,jarvis` | 호출어 |
| `JUNVIS_LOG_LEVEL` | 조용함 | 진단이 필요할 때 `DEBUG` |

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
├── core/        # 공유 커널 — eventbus · policy · trace · model · mcp(Host) · persistence
├── features/    # Bounded Context 하나 = 폴더 하나
│   ├── project_brain/
│   │   ├── domain/          # 순수. 외부 기술을 모른다
│   │   ├── application/     # 유스케이스 + Port
│   │   ├── infrastructure/  # SQLite · git · GitHub 어댑터
│   │   ├── interface/       # MCP 도구 · 이벤트 구독자
│   │   └── contracts.py     # 다른 feature에 공개하는 전부
│   ├── creator/             # 같은 구조
│   ├── brief/               # 같은 구조
│   ├── voice/               # 같은 구조
│   └── memory/              # 같은 구조
└── apps/        # 조립 루트 — cli · mcp_server · adapters · voice_router
```

**feature는 서로를 임포트하지 않는다.** 그런데도 프로젝트를 등록하면 릴스 제안이 생기고, 브리핑은 세 곳의 데이터를 모으고, 음성 명령은 셋 중 무엇이든 실행한다.

- `project_brain` ↔ `creator`: Event Bus (`project.registered` → 릴스 제안)
- `brief` → 나머지: 자기 입력 형태를 스스로 정의하고 `apps/adapters.py`가 채운다
- `voice` → 나머지: 무엇을 실행할지 모른다. `apps/voice_router.py`가 정한다
- `memory` → 나머지: 누가 자기를 쓰는지 모른다. `apps/memory_learning.py`가 이벤트를 기억으로 옮긴다

이 규칙은 import-linter 계약 12개로 CI에서 강제된다.

의존성은 항상 안쪽을 향한다. 이 규칙은 문서가 아니라 **import-linter 계약으로 강제**된다:

```bash
lint-imports    # 계층을 어기면 실패한다
pytest          # 도메인은 외부 의존 없이 단위 테스트로 검증된다
```

## 아직 검증되지 않은 것

이 저장소는 Linux에서 개발됐다. macOS 전용 코드는 작성됐지만 **실행 확인되지 않았다** — `say`, Calendar.app(AppleScript), 알림 센터, 마이크 녹음(sox+whisper.cpp), launchd 스크립트. 전부 플랫폼 검사로 비-macOS에서는 조용히 비활성화되고, 각 파일 상단에 그 사실을 적어 뒀다.

미착수: Vision, Coding Agent, 플러그인 아키텍처. 자세한 현황은 [`docs/02-ARCHITECTURE.md` §10](docs/02-ARCHITECTURE.md).

## 설계 문서

| 문서 | 내용 |
|---|---|
| [`docs/JUNVIS-BRIEF.md`](docs/JUNVIS-BRIEF.md) | 원본 요구사항 |
| [`docs/01-ANALYSIS.md`](docs/01-ANALYSIS.md) | 오픈소스 7종 분석 — 장점/단점/가져올 것/가져오면 안 되는 것 |
| [`docs/02-ARCHITECTURE.md`](docs/02-ARCHITECTURE.md) | 아키텍처 설계 + MVP 태스크 분해 |
| [`docs/03-CREATOR-MODE.md`](docs/03-CREATOR-MODE.md) | Creator Mode 설계 + ModelPort |
| [`docs/04-DAILY-BRIEF.md`](docs/04-DAILY-BRIEF.md) | Daily Brief 설계 + 우선순위 규칙 |
| [`docs/05-VOICE.md`](docs/05-VOICE.md) | Voice 설계 + 4단 게이트 |
| [`docs/06-MEMORY.md`](docs/06-MEMORY.md) | Personal Memory 설계 + digest 압축 |
| [`docs/07-MCP-HOST.md`](docs/07-MCP-HOST.md) | MCP Host 설계 + Browser Use를 라이브러리로 쓰지 않는 이유 |

## 핵심 결정

- **도구 표준은 MCP 하나.** 자체 도구 포맷을 만들지 않는다. JUNVIS는 MCP Host이자 Server다. 서드파티 도구는 라이브러리로 감싸지 않고 **별도 프로세스의 MCP 서버로 쓴다** — 의존성 충돌이 구조적으로 사라지고, 어댑터를 하나도 쓰지 않는다.
- **기억은 2층.** 구조적 기억(프로젝트·커밋·캘린더)과 서술적 기억(선호·규칙) 모두 자체 SQLite가 소유한다. 의미 검색이 필요해지면 `MemoryRepository` 뒤에 Mem0를 끼운다 — [이유](docs/06-MEMORY.md#0-원래-계획에서-바꾼-것).
- **모든 부작용은 PolicyEngine을 통과한다.** SAFE/LOW는 자동, MEDIUM/HIGH는 확인, FORBIDDEN은 거부.
- **모든 실행은 Trace를 남긴다.** Trace가 개인화의 원재료다.
- **로컬 우선.** Ollama가 기본이고 클라우드는 명시적 폴백이다.

## 라이선스 주의

ScreenPipe(상용 소스공개)와 isair/jarvis(개인용 무료)는 **코드를 가져오지 않는다.** 설계와 기법만 참조하고 해당 계층은 자체 구현한다. 자세한 내용은 [`docs/01-ANALYSIS.md` §9](docs/01-ANALYSIS.md).
