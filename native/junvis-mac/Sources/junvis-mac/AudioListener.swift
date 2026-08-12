import AVFoundation
import Foundation
import Speech

/// 마이크를 붙잡고 두 가지를 동시에 본다: 받아쓰기와 박수.
///
/// 같은 오디오 탭에서 갈라지는 것이 중요하다. 마이크를 두 번 열면
/// macOS가 하나를 거부한다.
final class AudioListener {
    private let engine = AVAudioEngine()
    private let recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var detector: ClapDetector
    private var elapsed: Double = 0
    private var lastEmitted = ""

    init(locale: Locale, detector: ClapDetector) {
        self.recognizer = SFSpeechRecognizer(locale: locale)
        self.detector = detector
    }

    /// 권한을 먼저 받는다. 없으면 무엇이 없는지 알려주고 끝낸다.
    static func requestPermissions(completion: @escaping (String?) -> Void) {
        SFSpeechRecognizer.requestAuthorization { status in
            guard status == .authorized else {
                completion("음성 인식 권한이 없습니다 (시스템 설정 → 개인정보 보호 → 음성 인식)")
                return
            }
            AVCaptureDevice.requestAccess(for: .audio) { granted in
                completion(granted ? nil : "마이크 권한이 없습니다 (시스템 설정 → 개인정보 보호 → 마이크)")
            }
        }
    }

    func start() throws {
        guard let recognizer, recognizer.isAvailable else {
            throw HelperError.message("이 언어의 음성 인식을 쓸 수 없습니다")
        }

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        // 온디바이스로 못박는다. 개인 기억이 애플 서버로 나가면 안 된다.
        request.requiresOnDeviceRecognition = true
        self.request = request

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        let sampleRate = format.sampleRate

        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            guard let self else { return }
            self.request?.append(buffer)
            self.inspect(buffer: buffer, sampleRate: sampleRate)
        }

        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            guard let self else { return }
            if let error {
                emit(.error(message: "받아쓰기 실패: \(error.localizedDescription)"))
                return
            }
            guard let result, result.isFinal else { return }
            self.emitTranscript(result)
        }

        engine.prepare()
        try engine.start()
    }

    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        request?.endAudio()
        task?.cancel()
    }

    var suggestedThreshold: Double { detector.suggestedThreshold }

    // -- 내부 ---------------------------------------------------------------

    private func inspect(buffer: AVAudioPCMBuffer, sampleRate: Double) {
        guard let channel = buffer.floatChannelData?[0] else { return }
        let frames = Int(buffer.frameLength)
        let level = rootMeanSquare(channel, count: frames)

        elapsed += Double(frames) / sampleRate
        detector.expire(at: elapsed)
        if let count = detector.feed(level: level, at: elapsed) {
            emit(.clap(count: count))
        }
    }

    private func emitTranscript(_ result: SFSpeechRecognitionResult) {
        let text = result.bestTranscription.formattedString.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !text.isEmpty, text != lastEmitted else { return }
        lastEmitted = text

        // 세그먼트 신뢰도의 평균. 무음에서 만들어낸 헛것을 Python이 거를 수 있게 한다.
        let segments = result.bestTranscription.segments
        let confidence =
            segments.isEmpty
            ? 1.0
            : Double(segments.map { $0.confidence }.reduce(0, +)) / Double(segments.count)

        emit(.transcript(text: text, confidence: confidence))
    }
}

enum HelperError: Error {
    case message(String)
}
