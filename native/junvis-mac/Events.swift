import Foundation

/// stdout으로 나가는 JSON Lines. Python이 읽는 유일한 통로다.
///
/// 이 형식이 계약이다(docs/08-NATIVE-HELPER.md §1). 필드를 바꾸면
/// `src/junvis/features/voice/infrastructure/native_source.py`와
/// 그 테스트도 함께 바뀌어야 한다.
enum Event {
    case ready(wakeWords: [String])
    case transcript(text: String, confidence: Double)
    case clap(count: Int)
    case error(message: String)

    var payload: [String: Any] {
        let now = ISO8601DateFormatter().string(from: Date())
        switch self {
        case .ready(let wakeWords):
            return ["type": "ready", "wake_words": wakeWords, "at": now]
        case .transcript(let text, let confidence):
            return [
                "type": "transcript",
                "text": text,
                "confidence": confidence,
                "at": now,
            ]
        case .clap(let count):
            return ["type": "clap", "count": count, "at": now]
        case .error(let message):
            return ["type": "error", "message": message, "at": now]
        }
    }
}

/// 줄 단위로 즉시 내보낸다. 버퍼에 갇히면 실시간이 아니다.
func emit(_ event: Event) {
    guard
        let data = try? JSONSerialization.data(
            withJSONObject: event.payload, options: [.withoutEscapingSlashes]
        ),
        let line = String(data: data, encoding: .utf8)
    else { return }
    print(line)
    fflush(stdout)
}

/// 사람이 읽을 메시지는 stderr로. stdout은 계약 전용이다.
func log(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}
