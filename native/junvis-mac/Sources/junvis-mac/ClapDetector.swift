import Foundation

/// 박수 두 번을 찾는다.
///
/// 오탐이 이 기능의 전부다. 문 닫는 소리, 키보드, 책상 두드림이 전부
/// 비슷한 모양이라, 다음 세 가지를 **모두** 만족해야 박수로 본다.
///
/// 1. 조용하다가 급격히 커진다 (onset)
/// 2. 그 피크가 **짧다** — 길면 말소리나 문소리다
/// 3. 두 번째 피크가 150~600ms 뒤에 온다 — 너무 빠르면 울림, 느리면 딴 소리
///
/// 임계값은 환경마다 다르다. `junvis-mac calibrate`가 주변 소음을 재서
/// 값을 제안한다. 여기 기본값은 출발점일 뿐이며 **실제 하드웨어에서
/// 맞춰야 한다**(docs/08-NATIVE-HELPER.md §3).
struct ClapDetector {
    /// 이 배수 이상으로 커지면 onset으로 본다(주변 소음 대비).
    var onsetRatio: Double = 8.0
    /// 절대 하한. 조용한 방에서 소음 기준선이 0에 가까워도 헛것을 잡지 않게.
    var minimumLevel: Double = 0.05
    /// 피크가 이보다 길면 박수가 아니다.
    var maximumPeakSeconds: Double = 0.12
    /// 두 박수 사이의 허용 간격.
    var minimumGapSeconds: Double = 0.15
    var maximumGapSeconds: Double = 0.60
    /// 몇 번을 부름으로 볼지.
    var requiredClaps: Int = 2

    /// 지수 이동 평균으로 추적하는 주변 소음.
    private var noiseFloor: Double = 0.01
    private var peakStartedAt: Double?
    private var clapTimes: [Double] = []

    /// 버퍼 하나의 RMS와 그 시각(초)을 넣는다. 박수 묶음이 완성되면 개수를 돌려준다.
    mutating func feed(level: Double, at time: Double) -> Int? {
        let threshold = max(noiseFloor * onsetRatio, minimumLevel)

        if level >= threshold {
            if peakStartedAt == nil {
                peakStartedAt = time
            }
            // 피크 동안에는 소음 기준선을 갱신하지 않는다. 박수 소리로
            // 기준선이 올라가면 두 번째 박수를 놓친다.
            return nil
        }

        defer { noiseFloor = noiseFloor * 0.95 + level * 0.05 }

        guard let start = peakStartedAt else { return nil }
        peakStartedAt = nil

        let duration = time - start
        guard duration <= maximumPeakSeconds else {
            // 길게 이어진 소리는 박수가 아니다. 묶음을 버린다.
            clapTimes.removeAll()
            return nil
        }

        if let previous = clapTimes.last {
            let gap = start - previous
            if gap < minimumGapSeconds {
                return nil  // 울림. 같은 박수로 본다
            }
            if gap > maximumGapSeconds {
                clapTimes = []  // 너무 늦었다. 새 묶음으로 시작
            }
        }

        clapTimes.append(start)
        if clapTimes.count >= requiredClaps {
            let count = clapTimes.count
            clapTimes.removeAll()
            return count
        }
        return nil
    }

    /// 조용한 구간이 길면 묶음을 버린다.
    mutating func expire(at time: Double) {
        if let last = clapTimes.last, time - last > maximumGapSeconds {
            clapTimes.removeAll()
        }
    }

    var suggestedThreshold: Double {
        max(noiseFloor * onsetRatio, minimumLevel)
    }
}

/// 오디오 버퍼의 RMS. 진폭의 제곱평균제곱근이 소리 크기에 가장 가깝다.
func rootMeanSquare(_ samples: UnsafePointer<Float>, count: Int) -> Double {
    guard count > 0 else { return 0 }
    var total: Double = 0
    for index in 0..<count {
        let value = Double(samples[index])
        total += value * value
    }
    return (total / Double(count)).squareRoot()
}
