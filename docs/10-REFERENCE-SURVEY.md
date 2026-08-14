# 10. 레퍼런스 전수조사 — 실제 소스를 읽고 쓴 것

> 조사일: 2026-08-13 · 방법: **7개 저장소를 직접 클론해서 읽음**
> 대상 커밋: 각 저장소의 그날 `main`

## 0. 이 문서가 존재하는 이유

`docs/01-ANALYSIS.md`는 1단계 분석 문서인데, **URL이 하나도 없다.** 소스를 읽고
쓴 것이 아니라 기억으로 쓴 것이다. 그 위에 아키텍처를 세웠다.

이번에는 클론해서 읽었다. 결과적으로 **한 가지 결론이 틀렸고**, 하나는 근거를
정확히 확인했으며, 우리가 지금 겪고 있는 문제의 답이 남의 저장소에 이미 있었다.

### 한눈에

| 프로젝트 | 실물 | 라이선스(확인) | 우리와의 관계 |
|---|---|---|---|
| Open Interpreter | Rust 2851 · TS 660 파일 | Apache-2.0 | ⚠️ **결론이 틀렸다** (§2) |
| Mem0 | Python 1689 파일 | Apache-2.0 | 기법을 가져올 수 있다 (§3) |
| Browser Use | Python | MIT | Host로 붙이는 판단 유효 (§4) |
| isair/jarvis | Python 228 파일 | **커스텀·비상업·전염성** | 읽되 복사 금지 (§5) |
| ScreenPipe | Rust 948 · TS 877 | **상용** (개인 무료) | 코드 복사 불가 (§6) |
| MCP | 명세 + SDK | MIT→**Apache-2.0 전환 중** | 우리가 절반만 쓰고 있다 (§7) |
| OpenJarvis | — | — | **특정하지 못했다** (§8) |

전부 이번 주에도 커밋되고 있다. 죽은 프로젝트가 하나도 없다.

---

## 1. 가장 중요한 발견 셋

**하나. Open Interpreter를 못 쓴다는 결론이 틀렸다.**
`sdk/python`이 있고 `interpreter exec`라는 비대화식 모드가 있다. 우리가 이미
만든 `ClaudeCodeAdapter`와 **구조가 똑같다**(§2).

**둘. 지금 겪는 음성 문제의 답이 isair/jarvis에 있다.**
에코를 통째로 버리는 우리와 달리 **에코 부분만 잘라내고 사용자 말은 살린다.**
그래서 JUNVIS가 말하는 중에 말을 끊을 수 있다. 우리는 못 한다(§5).

**셋. MCP를 절반만 쓰고 있다.**
우리는 `tools`만 노출한다. 명세에는 `resources`·`prompts`가 있고, 클라이언트
쪽에는 `sampling`이 있다. Context Pack은 이름부터가 resource다(§7).

---

## 2. Open Interpreter — 결론이 틀렸다

`docs/01-ANALYSIS.md`는 이렇게 적었다.

> Codex 기반 Rust로 재작성돼 **Python 라이브러리로 임포트 불가** → 못 씀

앞부분은 맞다. `codex-rs/`에 Rust 2851 파일, `.py`는 CI 스크립트뿐이다.
**뒷부분이 틀렸다.**

```
sdk/
├── python          ← openai-codex 패키지
├── python-runtime
└── typescript
```

게다가 라이브러리를 임포트할 필요조차 없다.

```bash
interpreter exec "summarize the changes in the last commit"
cat task.md | interpreter exec -          # stdin
git diff | interpreter exec "설명해줘"     # 파이프
interpreter exec --json "..."             # 구조화 출력
```

> 사람이 읽는 최종 답은 stdout으로, 진행 상황과 진단은 stderr로 나간다.
> — `docs/exec.md`

**이것은 `claude -p`와 완전히 같은 계약이다.** 우리 `ClaudeCodeAdapter`가
하는 일 — stdin으로 프롬프트, stdout에서 답, 타임아웃, JSON 추출 — 을 그대로
쓸 수 있다. `ModelPort` 뒤에 어댑터 하나가 더 붙는 것뿐이다.

### 무엇이 달라지는가

우리는 이미 "CLI를 두뇌로 쓴다"는 패턴을 갖고 있다. 그것이 Claude 전용이
아니라 **일반적인 패턴**이라는 뜻이다. Codex·Gemini CLI·Kimi 무엇이든 같은
모양으로 붙는다. `ClaudeCodeAdapter`를 `CliAgentAdapter`로 일반화할 값어치가
생겼다.

다만 **지금 당장 할 일은 아니다.** Claude가 이미 잘 되고 있고, 두 번째 CLI를
붙일 실제 이유가 아직 없다. 기록만 해 둔다.

---

## 3. Mem0 — 2단계 기억 관리

우리는 Mem0를 의존성으로 쓰지 않기로 했다(`docs/06 §0`). 그 판단은 유지하되,
**핵심 기법은 확인했고 가져올 수 있다.**

### 구조

```
mem0/
├── memory/      main.py(2500줄+), base, storage
├── llms/  embeddings/  vector_stores/  reranker/   ← 전부 교체 가능한 provider
├── configs/prompts.py                              ← 여기에 진짜 자산이 있다
├── client/  proxy/
└── mem0-ts/                                        ← TypeScript 포팅
```

### 작동 방식 — `add(messages, infer=True)`

`infer=True`(기본값)가 전부다. 대화를 통째로 넣으면 LLM이 **두 번** 돈다.

**1단계 · 사실 추출** (`FACT_RETRIEVAL_PROMPT`)

> You are a Personal Information Organizer… extract relevant pieces of
> information from conversations and organize them into distinct, manageable facts.

핵심은 프롬프트 본문이 아니라 **few-shot 예시**다.

```
Input: Hi.                          Output: {"facts": []}
Input: There are branches in trees. Output: {"facts": []}
Input: Hi, I am looking for a restaurant in San Francisco.
                                    Output: {"facts": ["Looking for a restaurant in San Francisco"]}
```

잡담에 빈 배열을 돌려주도록 **가르친다.** 내가 "말한 것을 전부 저장하면 잡음이
신호를 덮는다"고 걱정해서 자동 저장을 안 넣었는데, 그 걱정에 대한 답이 이것이다.

**2단계 · 기억 조정** (`DEFAULT_UPDATE_MEMORY_PROMPT`)

기존 기억 + 새 사실을 함께 주고 **ADD / UPDATE / DELETE / NONE** 중 하나를
고르게 한다. 예시까지 프롬프트에 박아 두었다.

이 두 번째 단계가 우리에게 아예 없는 것이다. 우리 `RememberFact`는 넣기만
한다. 그래서 "Ollama를 쓴다" → 나중에 "Claude를 쓴다"로 바뀌면 **둘 다 남는다.**

### 가져올 것 / 안 가져올 것

| | 판단 |
|---|---|
| 2단계 프롬프트 구조 | ✅ 개념을 가져온다. Apache-2.0이라 인용도 가능 |
| few-shot으로 잡담 거르기 | ✅ 이게 자동 기억의 열쇠다 |
| 라이브러리 의존 | ❌ 벡터 스토어·임베딩까지 딸려 온다. SQLite+FTS5로 충분하다 |

**비용**: 대화 한 번에 모델 호출이 2회 늘어난다. 음성에서는 답한 뒤에
**비동기로** 돌려야 한다 — 우리에겐 Event Bus와 Outbox가 이미 있다.

---

## 4. Browser Use — 판단이 유효함을 확인

`pyproject.toml:39`

```toml
"mcp==1.26.0",
```

**오늘도 그대로 핀돼 있다.** 우리 MCP SDK 2.x와 충돌한다. 임포트하지 않고
외부 MCP 서버로 붙이기로 한 판단(`docs/07 §0`)이 지금도 옳다.

그리고 붙일 대상이 실제로 있다.

```
browser_use/mcp/
├── server.py      ← 우리가 Host로 띄울 것
├── client.py
└── manifest.json
```

에이전트 루프는 `agent/service.py`의 `run(max_steps=500)` — 단계 기반이고,
`message_manager/`가 대화 이력을 관리하며 `system_prompts/`가 따로 있다.
우리 라우터와는 층위가 다르다. **JUNVIS 상위, Browser Use 하위**라는 1단계
결론이 구조적으로도 맞다.

---

## 5. isair/jarvis — 우리가 지금 겪는 문제의 답

가장 값진 저장소다. Python 228 파일이고, 우리가 이번 주에 싸운 파일들이
그대로 있다.

```
src/jarvis/listening/
├── listening.spec.md      ← 403줄짜리 설계 문서
├── echo_detection.py
├── wake_detection.py
├── intent_judge.py
├── transcript_buffer.py
└── state_manager.py
```

### 먼저 라이선스 — 코드를 복사할 수 없다

> 3. Any derivative works are also licensed under these same terms.
> — `LICENSE`

비상업 용도로는 복사·수정·배포가 허용되지만 **파생물도 같은 조건을 물려받는다.**
JUNVIS는 MIT다. 한 줄이라도 가져오면 MIT를 유지할 수 없다.
**기법만 읽고 우리 손으로 다시 쓴다.**

### 구조가 우리와 근본적으로 다르다 — Transcript-First

우리: 발화 하나 → 게이트 1~4 → 라우팅. 발화가 오면 그 자리에서 판정한다.

그들: **모든 말을 2분짜리 롤링 버퍼에 계속 쌓는다.** 각 조각에 텍스트·시작·끝
시각·에너지·`is_during_tts` 플래그가 붙는다. 호출어가 감지되면 그때 버퍼 전체를
Intent Judge에게 넘긴다.

```
버퍼 → Intent Judge → {directed, query, stop, confidence, reasoning}
```

> Pre-wake-word chatter naturally filtered:
> "blah blah Jarvis what time is it" → "what time is it"

**이 구조라면 우리의 "릴 스 만들어 줘" 문제가 아예 생기지 않는다.** 띄어쓰기도
말더듬도 LLM이 정리해서 깨끗한 질의를 뽑아 준다.

그리고 이것은 우리 원칙을 어기지 않는다. LLM이 하는 일은 **질의 텍스트를
추출하는 것**이지 무엇을 실행할지 정하는 것이 아니다. 추출된 질의를 우리
규칙 라우터에 넣으면 된다.

### 우리보다 나은 것 여섯 가지

**1. 에코를 버리지 않고 잘라낸다.**

`cleanup_leading_echo_during_tts` · `salvage_after_echo_tail`. TTS 텍스트와
겹치는 앞부분만 제거하고 뒤에 붙은 진짜 사용자 말을 살린다.

```python
# min_salvage_words = 3, 주석 그대로:
# 3은 짧은 자연스러운 후속("tell me more please")은 받아들일 만큼 낮고,
# Whisper의 에코 꼬리 환각("…regions like Steneti")은 걷어낼 만큼 높다.
```

우리는 `discard_pending()`으로 **말하는 동안 들어온 것을 전부 버린다.** 무한
루프는 막았지만 **JUNVIS 말을 끊을 수 없게 됐다.** 그들은 끊을 수 있다.

**2. 에너지로 에코와 진짜 목소리를 가른다.**

`energy_spike_threshold: float = 2.0` — TTS 재생 중 기준 에너지를 기록해 두고,
그보다 2배 이상 큰 소리만 진짜 입력으로 본다. 텍스트만 보는 우리보다 확실하다.

**3. TTS 속도로 "그 순간 재생 중이던 구간"을 계산한다.**

`_matches_tts_segment(heard_text, tts_rate, utterance_start_time)`. 긴 답변
전체와 비교하면 유사도가 묻히는데, 시각으로 구간을 좁혀서 비교한다.

내가 손으로 만든 "들린 길이만큼의 앞부분과 비교"가 이것의 조잡한 버전이다.
그들은 `rapidfuzz.fuzz.partial_ratio ≥ 70`을 쓴다 — 부분 문자열 최적 매칭이라
접두사든 중간이든 잡는다. **`difflib`로 손수 구현한 것을 대체할 수 있다.**

**4. 호출어를 퍼지 매칭한다.**

```python
def is_wake_word_detected(text_lower, wake_word, aliases, fuzzy_ratio=0.78)
```

정확 일치 → 별칭 정확 일치 → **토큰별 유사도 0.78**. 우리는 공백만 지우고
정확 일치를 본다. "자비스"가 "자비수"로 들리면 우리는 못 깨어난다.

**5. 별칭을 정규화한 뒤 판정기에 넘긴다.**

> 별칭은 Whisper의 오인식("Jervis", "Jaivis")이다. 이 단계가 없으면 작은 판정
> 모델이 별칭을 보고 **사용자가 다른 사람에게 말하는 중이라고 판단한다.**

**6. 호출어 제거를 정규식이 아니라 프롬프트로 한다.**

> 정규식이 잘못 다루는 경우가 있기 때문이다 — 호출어를 포함한 고유명사
> ("Jarvis Cocker") 같은.

우리 `strip_wake_word`는 정규식이다. "자비스"가 이름에 들어간 것을 말하면
망가진다.

### 그들도 우리와 똑같은 함정을 밟았다

> 판정기는 **관여 신호가 있을 때만** 부른다 — (a) 호출어가 들렸거나 (b) hot
> window 안이거나 (c) TTS가 말하는 중. 순수한 주변 대화는 판정기를 아예
> 건너뛴다. 그러지 않으면 배경 발화마다 동기 오디오 루프가
> `intent_judge_timeout_sec`만큼 멈춰서, Ollama가 느릴 때 UI가 얼어붙는다.

**우리가 어제 겪은 90초 멈춤이 정확히 이것이다.** 그들은 명세에 적어 두었다.

그리고 하나 더:

> `keep_alive: 30m` — 판정 요청마다 Ollama에게 모델을 30분 유지하라고 한다.
> 없으면 기본 5분 유휴 후 모델이 내려가고, 다음 판정이 재적재 비용을 전부
> 물어 타임아웃에 걸린다.

우리 `OllamaAdapter`는 `keep_alive`를 보내지 않는다. 판정기를 Ollama로 되돌린
지금, 이건 바로 겪을 문제다.

### 우리에게 없는 것: 정지 명령

> **Stop detection:** 텍스트 기반으로 "stop", "quiet", "shut up" 등을 확인.

JUNVIS가 긴 브리핑을 읽기 시작하면 **끝날 때까지 기다리는 수밖에 없다.**

---

## 6. ScreenPipe — 코드는 못 쓰지만 구조는 배울 것이 있다

라이선스를 정확히 확인했다.

> **Free Use**: 개인·비상업, 비영리·교육·연구, 그리고 조직 규모와 무관하게
> **7일간의 평가·개발·테스트**.
> **Commercial Use**: 사업/운영 환경, 매출 발생 활동, 영리 법인에 의한 사용.

ZUN 브랜드가 수익을 내기 시작하면 개인 사용의 경계가 흐려진다. **코드 복사는
하지 않는다**는 기존 판단이 맞다.

### 크레이트 구조가 알려주는 것

```
screenpipe-capture / -screen / -audio     캡처
screenpipe-a11y                           접근성 API — OCR 없이 텍스트를 얻는다
screenpipe-redact                         ★ 민감정보 제거
screenpipe-db / -semantic                 저장 + 의미 검색
screenpipe-events                         이벤트 버스 (우리와 같은 선택)
screenpipe-overlay-win                    오버레이 창 (우리 오브에 해당)
```

**`screenpipe-redact`가 우리에게 던지는 질문이 있다.** 다 기록하면 비밀도 같이
기록된다. JUNVIS의 Trace와 기억에도 같은 문제가 있다 — 음성으로 API 키를
읽거나, 프로젝트 스캔이 `.env`를 읽으면 그대로 남는다. 우리에겐 걸러내는 층이
없다.

`-a11y`도 배울 점이다. 화면을 이해하는 데 꼭 OCR이 필요한 게 아니라 접근성
API로 텍스트를 직접 얻을 수 있다. Vision을 만들 때의 출발점이다.

---

## 7. MCP — 우리는 절반만 쓰고 있다

라이선스가 **MIT에서 Apache-2.0으로 전환 중**이다. 새 기여는 Apache-2.0,
동의를 받지 못한 기존 기여는 MIT로 남는다. 우리 문서는 MIT라고만 적었다.

명세는 이미 `2026-07-28`까지 나와 있다.

| 영역 | 명세에 있는 것 | JUNVIS |
|---|---|---|
| 서버 | **tools** | ✅ 20개 |
| 서버 | **resources** | ❌ |
| 서버 | **prompts** | ❌ |
| 서버 | **discover** (2026-07-28 신규) | ❌ |
| 클라이언트 | **sampling** | ❌ |
| 클라이언트 | elicitation, roots | ❌ |

우리 `mcp_server/main.py`에는 `on_list_tools`와 `on_call_tool` 둘뿐이다.

### 놓치고 있는 것 셋

**resources — Context Pack은 이름부터가 resource다.**
지금은 `junvis_project_context`라는 **도구를 호출해야** 컨텍스트가 온다.
resource로 노출하면 Claude Code가 파일처럼 붙일 수 있다.

**prompts — 슬래시 명령이 된다.**
"릴스 만들기"를 prompt로 노출하면 Claude Code에서 `/junvis:reel`처럼 뜬다.
지금은 사용자가 도구 이름을 알아야 한다.

**sampling — 이게 크다.**
서버가 **클라이언트의 LLM에게** 완성을 요청하는 기능이다. JUNVIS가 Claude Code
안에서 MCP 서버로 돌 때는 `claude -p` 프로세스를 새로 띄울 필요 없이 이미 열려
있는 세션의 모델을 쓸 수 있다는 뜻이다. 우리가 방금 씨름한 기동 비용이 0이 된다.

단, `junvis listen`처럼 독립 실행할 때는 클라이언트가 없으므로 해당 없다.
**두 경로가 다르다는 것을 알고 설계해야 한다.**

---

## 8. OpenJarvis — 특정하지 못했다

원래 브리프의 "OpenJarvis (agent framework/memory/tool/plugin/scheduler/
learning)"에 해당하는 저장소를 **확정하지 못했다.** 그 이름의 프로젝트가 여럿
있고 어느 것을 가리키는지 알 수 없다.

`docs/01-ANALYSIS.md`가 이 프로젝트에 대해 적은 내용(Event Bus, 플러그인 경계)은
**무엇을 근거로 쓴 것인지 확인되지 않는다.** 그 항목은 신뢰하지 않는 것이 맞다.

정확한 저장소 주소를 알려주시면 같은 깊이로 조사한다.

---

## 9. 그래서 무엇을 할 것인가

읽은 것을 전부 구현하자는 뜻이 아니다. **지금 아픈 것부터** 순서를 매긴다.

### 지금 바로 (실사용을 막고 있다)

| # | 할 일 | 근거 | 크기 |
|---|---|---|---|
| 1 | **Ollama `keep_alive: 30m`** | 판정기를 Ollama로 되돌렸다. 5분 후 재적재 비용이 타임아웃을 부른다 | 몇 줄 |
| 2 | **판정기 게이트** — 호출어/창/TTS 중일 때만 호출 | 그들 명세가 우리가 겪은 90초 멈춤을 그대로 설명한다 | 작다 |
| 3 | **정지 명령** ("그만", "됐어") | 지금은 긴 브리핑을 끊을 방법이 없다 | 작다 |
| 4 | **호출어 퍼지 매칭** (토큰별 0.78) | "자비수"로 들리면 못 깨어난다 | 작다 |

### 그다음 (구조가 나아진다)

| # | 할 일 | 근거 |
|---|---|---|
| 5 | **에코 잘라내기** — 버리지 말고 살리기 | 지금은 JUNVIS 말을 끊을 수 없다 |
| 6 | **`partial_ratio` 도입** | 손으로 만든 접두사 비교의 일반형 |
| 7 | **Mem0식 2단계 자동 기억** | 대화가 생겼으니 붙일 자리가 생겼다. Outbox로 비동기 |
| 8 | **MCP resources + prompts** | Context Pack을 파일처럼, 릴스를 슬래시 명령으로 |

### 크게 다시 볼 것

**Transcript-First로 갈 것인가.** 롤링 버퍼 + 질의 추출은 우리 띄어쓰기·
말더듬 문제를 구조적으로 없앤다. 규칙 라우팅도 그대로 유지된다 — LLM은 질의를
**뽑기만** 하고 실행은 여전히 규칙이 정한다.

다만 이건 voice feature를 다시 쓰는 일이다. 위 1~4번을 먼저 하고, 그래도
남는 불편이 있는지 며칠 써 본 뒤에 정하는 것이 맞다.

**민감정보 필터.** ScreenPipe에 `redact` 크레이트가 따로 있는 이유가 있다.
우리 Trace와 기억에도 같은 구멍이 있다. 급하지 않지만 잊으면 안 된다.

---

## 10. 조사 방법과 한계

```bash
git clone --depth 1 https://github.com/mem0ai/mem0
git clone --depth 1 https://github.com/browser-use/browser-use
git clone --depth 1 https://github.com/isair/jarvis
git clone --depth 1 https://github.com/OpenInterpreter/open-interpreter
git clone --depth 1 https://github.com/mediar-ai/screenpipe
git clone --depth 1 https://github.com/modelcontextprotocol/python-sdk
git clone --depth 1 https://github.com/modelcontextprotocol/modelcontextprotocol
```

**읽은 것**: 라이선스 원문, 디렉터리 구조, 설계 문서(`listening.spec.md`,
`DESIGN.md`, `docs/exec.md`), 프롬프트 원문(`mem0/configs/prompts.py`),
핵심 모듈의 시그니처와 주석.

**읽지 않은 것**: 각 저장소의 구현 세부. 6027 파일짜리 저장소를 전부 읽지는
않았다. 위의 판단은 **설계 문서와 인터페이스**에 근거한 것이고, 실제 구현이
문서와 다를 수 있다.

**확인하지 못한 것**: OpenJarvis(§8). 그리고 여기서 인용한 수치(에너지 배수
2.0, 퍼지 0.78, partial_ratio 70, min_salvage_words 3)는 **그들의 하드웨어에서
맞춘 값**이다. 우리가 그대로 쓸 근거는 없고, 출발점으로만 쓴다.
