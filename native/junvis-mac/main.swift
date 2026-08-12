import AVFoundation
import Foundation
import Speech

/// `junvis-mac` — JUNVIS가 Python으로 닿지 못하는 것만 맡는다.
///
///   listen     상시 대기. 받아쓰기와 박수를 JSON Lines로 뱉는다
///   calendar   오늘 일정 (EventKit)
///   calibrate  주변 소음을 재서 박수 임계값을 제안한다
///   check      권한 상태
///
/// 인자 파싱을 직접 한다. swift-argument-parser를 쓰면 네트워크 없이
/// 빌드할 수 없고, 우리에게 필요한 것은 플래그 네 개뿐이다.

struct Options {
    var wakeWords: [String] = ["준비스", "자비스", "junvis", "jarvis"]
    var requiredClaps = 2
    var locale = "ko-KR"
    var clapThreshold: Double?

    static func parse(_ arguments: [String]) -> Options {
        var options = Options()
        var index = 0
        while index < arguments.count {
            let flag = arguments[index]
            let value: String? = index + 1 < arguments.count ? arguments[index + 1] : nil
            switch flag {
            case "--wake":
                if let value = value {
                    options.wakeWords = value.split(separator: ",").map {
                        $0.trimmingCharacters(in: .whitespaces)
                    }.filter { !$0.isEmpty }
                }
                index += 2
            case "--clap":
                if let value = value, let count = Int(value) { options.requiredClaps = count }
                index += 2
            case "--locale":
                if let value = value { options.locale = value }
                index += 2
            case "--clap-threshold":
                if let value = value, let level = Double(value) { options.clapThreshold = level }
                index += 2
            default:
                index += 1
            }
        }
        return options
    }
}

func makeDetector(_ options: Options) -> ClapDetector {
    var detector = ClapDetector()
    detector.requiredClaps = options.requiredClaps
    if let threshold = options.clapThreshold {
        detector.minimumLevel = threshold
    }
    return detector
}

func runListen(_ options: Options) {
    AudioListener.requestPermissions { problem in
        if let problem = problem {
            emit(.error(message: problem))
            exit(1)
        }
    }
    // 권한 콜백이 끝날 시간을 준다. 여기서 바로 시작하면 탭이 거부된다.
    Thread.sleep(forTimeInterval: 0.5)

    let listener = AudioListener(
        locale: Locale(identifier: options.locale),
        detector: makeDetector(options)
    )
    do {
        try listener.start()
    } catch {
        emit(.error(message: "마이크를 열지 못했습니다: \(error)"))
        exit(1)
    }

    emit(.ready(wakeWords: options.wakeWords))

    // SIGTERM을 받으면 깨끗하게 내려간다. Python이 프로세스를 정리한다.
    signal(SIGTERM) { _ in exit(0) }
    signal(SIGINT) { _ in exit(0) }
    RunLoop.main.run()
}

func runCalibrate(_ options: Options) {
    log("5초간 조용히 있어 주세요. 주변 소음을 잽니다…")
    let listener = AudioListener(
        locale: Locale(identifier: options.locale),
        detector: makeDetector(options)
    )
    do {
        try listener.start()
    } catch {
        log("마이크를 열지 못했습니다: \(error)")
        exit(1)
    }
    Thread.sleep(forTimeInterval: 5)
    listener.stop()
    let suggested = listener.suggestedThreshold
    log(String(format: "제안 임계값: %.4f", suggested))
    log("사용법: junvis-mac listen --clap-threshold \(String(format: "%.4f", suggested))")
}

func runCheck() {
    let speech = SFSpeechRecognizer.authorizationStatus()
    let microphone = AVCaptureDevice.authorizationStatus(for: .audio)
    log("음성 인식: \(speech == .authorized ? "허용됨" : "허용 안 됨 (\(speech.rawValue))")")
    log("마이크    : \(microphone == .authorized ? "허용됨" : "허용 안 됨 (\(microphone.rawValue))")")
    log("")
    log("허용되지 않은 항목은 시스템 설정 → 개인정보 보호 및 보안 에서 켜세요.")
    log("터미널에서 처음 실행하면 터미널 앱에 권한이 붙습니다.")
}

func runUsage() {
    log(
        """
        junvis-mac — JUNVIS 네이티브 헬퍼

          listen [--wake 준비스,자비스] [--clap 2] [--locale ko-KR]
                 [--clap-threshold 0.05]
                                상시 대기. JSON Lines를 stdout으로
          calendar              오늘 일정 (JSON)
          calibrate             주변 소음을 재서 박수 임계값 제안
          check                 권한 상태
        """
    )
}

let arguments = Array(CommandLine.arguments.dropFirst())
let options = Options.parse(arguments)

switch arguments.first {
case "listen":
    runListen(options)
case "calendar":
    CalendarQuery.today()
case "calibrate":
    runCalibrate(options)
case "check":
    runCheck()
default:
    runUsage()
    exit(2)
}
