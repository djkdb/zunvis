# JUNVIS — 네이티브 헬퍼 (`junvis-mac`) 설계

> 단계: **설계 + 뼈대**
> 상태: **Swift 코드는 컴파일 확인되지 않았다.** 이 저장소는 Linux다.
> 대신 Python 쪽과 그 사이의 계약은 전부 검증됐다.

---

## 0. 왜 Swift가 필요한가

Python으로는 닿지 않는 것이 셋 있다.

| 원하는 것 | Python으로 안 되는 이유 |
|---|---|
| 상시 대기 마이크 | 오디오 스트림을 계속 붙잡고 있어야 한다 |
| **박수 두 번** | 말이 아니다. Whisper에 넣으면 텍스트가 안 나온다 |
| 빠른 캘린더 조회 | AppleScript는 수 초 걸린다. EventKit은 즉시 |

특히 박수는 구조가 다르다. 지금 파이프라인은 `마이크 → Whisper → 텍스트 →
호출어 찾기`인데, 박수는 텍스트가 되지 않는다. **원본 오디오의 진폭을 직접
봐야** 한다.

---

## 1. 계약이 코드보다 중요하다

Swift를 여기서 컴파일할 수 없으므로, 값어치는 **경계를 정확히 못 박는 데**
있다. 헬퍼는 stdout에 **JSON Lines**를 뱉고, Python은 그것만 읽는다.

```
{"type":"ready","wake_words":["준비스","자비스"]}
{"type":"transcript","text":"준비스 오늘 브리핑","confidence":0.92}
{"type":"clap","count":2}
{"type":"error","message":"마이크 권한이 없습니다"}
```

이 계약 덕분에:
- Swift에 오타가 있어도 **Python 쪽 통합은 이미 검증돼 있다**
- 헬퍼를 다른 것으로 바꿔도(예: Rust, 또는 그냥 테스트용 스크립트) Python은 그대로다
- 실제로 `tests/features/voice/`가 **가짜 헬퍼 프로세스**로 전 경로를 돌린다

---

## 2. 박수를 어떻게 "부름"으로 다루는가

새 도메인 개념을 만들지 않는다. **박수 두 번 = 이름을 부른 것**으로 본다.

```
박수 짝짝  →  Utterance("준비스")  →  기존 게이트가 그대로 처리
           →  "네?" 하고 후속 발화 창이 열림
           →  이어서 "오늘 브리핑" (호출어 없이)
```

`HandleUtterance`가 이미 "호출어만 부른 경우"를 다루고 있으므로 코드를
한 줄도 고치지 않는다. 이것이 게이트를 도메인에 둔 값어치다.

---

## 3. 박수 감지 방법

AVAudioEngine의 입력 탭에서 버퍼마다 RMS를 재고, 이런 모양을 찾는다.

```
조용함 → 급격한 피크(짧음) → 조용함 → 급격한 피크 → 조용함
         ↑ 120ms 이내            ↑ 150~600ms 간격
```

**오탐이 이 기능의 전부다.** 문 닫는 소리, 키보드, 책상 두드림이 전부 비슷하다.
그래서:

- 피크는 **짧아야** 한다(120ms 초과 = 말소리나 문소리)
- 두 피크 **사이가 조용해야** 한다
- 임계값은 환경마다 다르므로 `--clap-threshold`로 조절한다
- `junvis-mac calibrate`가 주변 소음을 재서 값을 제안한다

이 수치들은 **실제 하드웨어에서 맞춰야 한다.** 여기서 고른 기본값은 출발점일 뿐이다.

---

## 4. 명령

```bash
junvis-mac listen --wake 준비스,자비스 --clap 2   # JSON Lines 스트림
junvis-mac calendar --day today                   # 오늘 일정 JSON
junvis-mac calibrate                              # 소음 측정, 임계값 제안
junvis-mac check                                  # 권한 상태
```

## 5. 권한

macOS는 처음 쓸 때 물어본다. `junvis-mac check`가 무엇이 필요한지 알려준다.

| 기능 | 권한 |
|---|---|
| 마이크 | 마이크 |
| 받아쓰기 | 음성 인식 |
| 캘린더 | 캘린더 (전체 접근) |

터미널에서 실행하면 **터미널 앱**에 권한이 붙는다. launchd로 돌릴 때
다시 물어볼 수 있다.

---

## 6. 지금 상태와 다음

| 부분 | 상태 |
|---|---|
| JSON Lines 계약 | ✅ 확정 |
| Python 쪽(`NativeHelperSource`) | ✅ 구현·테스트 완료 |
| 가짜 헬퍼로 전 경로 통합 테스트 | ✅ |
| CLI 연결(`junvis listen --native`, `junvis setup`) | ✅ |
| Swift 소스 | ⚠️ 작성됨, **컴파일 미확인** |
| 실제 박수 감지 정확도 | ❌ 하드웨어에서 맞춰야 함 |

맥에서 할 일:

```bash
./scripts/build-mac.sh          # 빌드 (오류가 나면 그 메시지를 보내주세요)
junvis-mac check                # 권한
junvis-mac calibrate            # 임계값
junvis listen --native          # 붙여서 확인
```

빌드가 깨지면 그건 예상된 일이다. 계약이 고정되어 있으므로 Swift만 고치면 된다.

### SwiftPM을 쓰지 않는 이유

처음에는 `Package.swift`로 `swift build`를 했다. 실제 맥에서 이렇게 죽었다.

```
error: 'junvis-mac': Invalid manifest
Undefined symbols for architecture arm64:
  "PackageDescription.Package.__allocating_init(name:defaultLocalization:…)"
```

Command Line Tools에 딸려 오는 SwiftPM과 `PackageDescription` 라이브러리의
버전이 어긋나면 매니페스트를 링크하지 못한다. **Swift 코드와는 아무 상관이
없는 실패다** — 빌드 시스템이 자기 자신을 빌드하지 못한 것이다.

의존성이 하나도 없는 파일 다섯 개짜리 도구에 패키지 매니저는 얻는 것 없이
깨질 곳만 늘린다. `swiftc`로 직접 컴파일한다.

```bash
swiftc -O -o junvis-mac native/junvis-mac/*.swift \
    -framework AVFoundation -framework Speech -framework EventKit \
    -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist \
    -Xlinker native/junvis-mac/Info.plist
```

`Info.plist`를 실행 파일 안에 심는 것이 중요하다. 사용 설명 문자열이 없으면
macOS는 마이크 권한을 **물어보지도 않고 거부한다.**

같은 이유로 Swift 5.7의 축약 옵셔널 바인딩(`if let value {`)도 쓰지 않는다.
`if let value = value {`로 풀어 쓰면 옛 툴체인에서도 컴파일된다. 이 한 줄
차이로 빌드가 갈리는데, 얻는 것은 글자 수뿐이다.
