# JUNVIS — 네이티브 헬퍼 (`junvis-mac`) 설계

> 단계: **설계 + 뼈대**
> 상태: **Swift는 쓰지 않는 길로 갔다.** 실제 맥에서 Apple 툴체인이
> 깨져 있어 컴파일 자체가 불가능했고, 같은 프레임워크를 PyObjC로
> Python에서 그대로 부를 수 있다는 것이 답이었다. §7 참고.
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
| **PyObjC 어댑터**(`AppleSpeechSource`) | ✅ 실제 경로 — 컴파일 불필요 |
| **박수 감지**(`ClapDetector`, Python) | ✅ 12개 테스트로 검증 |
| Swift 소스 | ⚠️ 남겨 둠, 컴파일 불가(§7) |
| 실제 박수 감지 정확도 | ❌ 하드웨어에서 맞춰야 함 |

맥에서 할 일:

```bash
uv pip install -e ".[mac]"      # 맥 내장 음성 인식
junvis listen --native          # 이름을 부르거나 박수 두 번
```


---

## 7. Swift를 포기한 이유 — 그리고 더 나은 길

실제 맥에서 두 번 시도했고 두 번 다 **우리 코드에 닿기도 전에** 죽었다.

**1차 (SwiftPM).**

```
error: 'junvis-mac': Invalid manifest
Undefined symbols: PackageDescription.Package.__allocating_init(…)
```

**2차 (swiftc 직접).**

```
error: failed to build module 'CoreFoundation'; this SDK is not supported
by the compiler (SDK는 swiftlang-6.0.3.1.5로 빌드됐는데, 컴파일러는
swiftlang-6.0.3.1.10). Please select a toolchain which matches the SDK.
error: redefinition of module 'SwiftBridging'
```

같은 `CommandLineTools` 폴더 안에서 컴파일러와 SDK 버전이 어긋나 있고,
`SwiftBridging` 모듈이 두 modulemap에 중복 정의돼 있다. Apple 툴체인 설치가
망가진 것이지 우리 코드의 문제가 아니다. **`main.swift` 첫 줄인
`import AVFoundation`에서 멈췄다.**

### 판단

여기서 툴체인을 고치는 데 시간을 더 쓸 수도 있었다. 그러지 않았다.

우리가 Swift에서 쓰려던 것 — `SFSpeechRecognizer`, `AVAudioEngine` — 은
전부 **Objective-C 프레임워크**다. PyObjC는 이것들을 Python에서 그대로
부른다. 컴파일러가 전혀 필요 없다.

```bash
uv pip install -e ".[mac]"     # 이게 전부다
junvis listen --native
```

얻은 것이 회피만은 아니다.

- **깨질 곳이 하나 줄었다.** 툴체인 버전, SDK 정합성, 링커 플래그가 전부 사라졌다.
- **박수 감지가 검증 가능해졌다.** Swift의 `ClapDetector`는 이 저장소에서
  한 줄도 시험할 수 없었다. Python으로 옮기니 문 닫는 소리·말소리·울림·
  2초 간격을 구분하는 규칙을 **12개 테스트로 실제로 검증**한다. 컴파일도
  못 해 본 코드가 오탐 규칙을 들고 있는 것보다 훨씬 낫다.
- **`AudioSourcePort` 덕분에 도메인은 그대로다.** 구현 하나를 갈아 끼웠을 뿐이다.

### Swift 헬퍼는 버리지 않는다

`native/junvis-mac/`은 남겨 둔다. 화면 캡처(ScreenCaptureKit)·접근성처럼
**PyObjC로도 어려운** 것들이 오면 그때 필요하다. 그때는 툴체인부터 고쳐야
한다 — 이 두 오류가 뜨면 다음을 실행한다.

```bash
sudo rm -rf /Library/Developer/CommandLineTools
sudo xcode-select --install
```

`junvis listen --native`는 PyObjC를 먼저 찾고, 없으면 `junvis-mac` 바이너리를
찾는다. 둘 중 되는 것을 쓴다.
