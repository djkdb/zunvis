# JUNVIS — Daily Brief 설계

> 단계: **설계** (세 번째 Bounded Context)
> 선행: Project Brain(MVP), Creator Mode
> 목표: 하루를 시작할 때 지금 무엇이 중요한지 한 화면으로 안다

---

## 0. 스케줄러를 만들지 않는다

브리프는 "매일 시작할 때 브리핑한다"고 요구한다. 여기서 `ScheduledJob`
애그리게이트와 스케줄러 도메인을 만들 수도 있었지만, **만들지 않는다.**

1단계 분석의 결론이 이미 그렇게 정해뒀다 — *"스케줄러: 자체 구현 + launchd.
macOS 네이티브가 더 안정적, 파이썬 상주 데몬 회피."* macOS에는 이미 launchd가
있고, 그것을 흉내 낸 두 번째 스케줄러는 재부팅·절전 복귀·로그인 시점을
다시 틀리게 처리할 뿐이다.

따라서 이 Context가 하는 일은 **조립**이다. *언제* 부를지는 OS가 정한다.

## 0-1. Briefing은 애그리게이트가 아니다

Briefing에는 생애주기가 없다. 상태가 바뀌지도, 불변식을 지킬 것도 없다.
매번 현재 사실로부터 새로 계산되는 **읽기 모델**이다. 그래서 저장하지 않고
테이블도 만들지 않는다. 도메인이 갖는 것은 데이터가 아니라 **조립 규칙**이다.

---

## 1. 도메인의 핵심: 우선순위가 도메인 규칙이다

브리프의 마지막 문장이 이 Context의 전부다.

> 모든 제안은 사용자의 장기 목표(개발, 프로젝트, ZUN 브랜드 성장)를 기준으로
> 우선순위를 판단한다.

그래서 "무엇을 먼저 보여줄지"가 표현 계층의 정렬 로직이 아니라 **도메인 규칙**이다.

### 섹션 우선순위

| 순위 | 섹션 | 근거 |
|---|---|---|
| 1 | 오늘 일정 | 시간 제약이 있다. 놓치면 되돌릴 수 없는 유일한 항목 |
| 2 | 멈춰 있는 작업 | 커밋되지 않은 변경. 잊으면 잃는다 |
| 3 | 해야 할 작업 | 프로젝트 TODO |
| 4 | GitHub 이슈 | 열린 이슈 |
| 5 | ZUN 콘텐츠 | 업로드 공백이 길수록 위로 올라온다 |
| 6 | 대기 중인 아이디어 | 아직 손대지 않은 제안 |
| 7 | 진행 중인 프로젝트 | 최근 손댄 것들 |
| 8 | AI 소식 | 브랜드 주제로 거른 것만 |
| 9 | 작업 습관 | Trace에서 나온 관찰 |

### 긴급도는 계산된다

`INFO < NOTICE < ATTENTION < URGENT`

- **콘텐츠 공백**: ZUN 브랜드 성장이 장기 목표이므로, 마지막 업로드 이후
  경과일이 늘면 긴급도가 올라간다. 3일 NOTICE / 7일 ATTENTION / 14일 URGENT.
- **멈춘 작업**: 커밋되지 않은 변경이 있으면 ATTENTION.
- 긴급도가 URGENT인 항목이 있으면 그 섹션이 **한 단계 위로** 올라온다.
  장기 목표가 오늘의 잡무를 이기는 유일한 통로다.

---

## 2. 수집 — Port로만 만난다

`brief`는 `project_brain`도 `creator`도 임포트하지 않는다. 자기 입력 형태를
스스로 정의하고, 조립 루트가 어댑터로 채운다(계약 8·9번이 강제).

| Port | 채우는 것 | 어댑터 |
|---|---|---|
| `ProjectDigestPort` | 프로젝트·TODO·이슈·작업 상태 | `project_brain` 유스케이스 |
| `ContentDigestPort` | 제안·초안·마지막 업로드일 | `creator` 유스케이스 |
| `InterestsPort` | 뉴스를 거를 관심 주제 | `creator`의 BrandVoice |
| `CalendarPort` | 오늘 일정 | macOS Calendar (AppleScript) |
| `HabitPort` | 작업 시간대·자주 쓰는 도구·실패율 | **Trace** |
| `NewsPort` | AI 소식 | Hacker News (Algolia API) |

**Trace가 여기서 쓰인다.** 설계 §5.2에서 "Trace는 로그가 아니라 개인화의
원재료"라고 했던 것이 처음으로 현금화되는 지점이다.

### 없어도 되는 것들

캘린더·뉴스는 각각 macOS 권한과 네트워크를 요구한다. 둘 다 **없으면 그 섹션이
빠질 뿐** 브리핑 전체가 실패하지 않는다. 오프라인은 정상 상태 중 하나다.

---

## 3. 인터페이스

```bash
junvis brief              # 오늘의 브리핑
junvis brief --notify     # macOS 알림으로 요약 한 줄 (launchd가 쓴다)
```

MCP 도구 `junvis_daily_brief` — Claude Code가 하루를 시작할 때 부른다.

launchd 에이전트 두 개:
- `com.zun.junvis.refresh` — 6시간마다 스냅샷 갱신 (이미 있음)
- `com.zun.junvis.brief` — 평일 오전 9시 브리핑 + 알림 (추가)

---

## 4. 구현 순서

| # | 태스크 | 완료 기준 |
|---|---|---|
| B1 | `ProjectSummary`에 TODO·이슈 텍스트 추가 | 기존 테스트 통과 유지 |
| B2 | brief domain — 조립 규칙과 긴급도 | 순수 단위 테스트로 우선순위 검증 |
| B3 | brief application — `ComposeBriefing` | Fake Port로 전 조합 검증 |
| B4 | brief infrastructure — 습관·캘린더·뉴스 | Trace 분석은 실제 SQLite로 |
| B5 | 배선 — MCP·CLI·어댑터 | 통합 테스트로 전 섹션 확인 |
| B6 | launchd + 알림 | 스크립트에 브리핑 에이전트 추가 |

## 5. 하지 않는 것

- **스케줄러 도메인.** launchd가 한다.
- **Briefing 저장.** 읽기 모델이다.
- **Google Calendar API.** macOS Calendar.app이 이미 구독 캘린더를 들고 있다.
- **뉴스 요약 생성.** 제목과 링크만. LLM으로 매일 아침 요약을 돌리는 것은
  비용 대비 가치가 낮다.
