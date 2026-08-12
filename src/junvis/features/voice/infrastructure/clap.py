"""박수 두 번을 찾는다.

Swift에 있던 것을 Python으로 옮겼다. 신호 처리는 순수 계산이라 언어를
가리지 않는데, Swift에 두면 이 저장소에서 **한 줄도 검증할 수 없었다.**
컴파일조차 못 한 코드가 오탐 규칙을 들고 있는 것은 좋지 않다.

오탐이 이 기능의 전부다. 문 닫는 소리, 키보드, 책상 두드림이 전부 비슷한
모양이라 다음 세 가지를 **모두** 만족해야 박수로 본다.

1. 조용하다가 급격히 커진다 (onset)
2. 그 피크가 **짧다** — 길면 말소리나 문소리다
3. 두 번째 피크가 150~600ms 뒤에 온다 — 너무 빠르면 울림, 느리면 딴 소리
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClapDetector:
    #: 주변 소음 대비 이 배수 이상으로 커지면 onset으로 본다.
    onset_ratio: float = 8.0
    #: 절대 하한. 조용한 방에서 기준선이 0에 가까워도 헛것을 잡지 않게.
    minimum_level: float = 0.05
    #: 피크가 이보다 길면 박수가 아니다.
    maximum_peak_seconds: float = 0.12
    #: 두 박수 사이의 허용 간격.
    minimum_gap_seconds: float = 0.15
    maximum_gap_seconds: float = 0.60
    #: 몇 번을 부름으로 볼지.
    required_claps: int = 2

    #: 지수 이동 평균으로 추적하는 주변 소음.
    _noise_floor: float = field(default=0.01, init=False)
    _peak_started_at: float | None = field(default=None, init=False)
    _clap_times: list[float] = field(default_factory=list, init=False)

    @property
    def threshold(self) -> float:
        return max(self._noise_floor * self.onset_ratio, self.minimum_level)

    @property
    def noise_floor(self) -> float:
        return self._noise_floor

    def feed(self, level: float, at: float) -> int | None:
        """버퍼 하나의 RMS와 그 시각(초). 묶음이 완성되면 개수를 돌려준다."""
        if level >= self.threshold:
            if self._peak_started_at is None:
                self._peak_started_at = at
            # 피크 동안에는 소음 기준선을 갱신하지 않는다. 박수 소리로
            # 기준선이 올라가면 두 번째 박수를 놓친다.
            return None

        self._noise_floor = self._noise_floor * 0.95 + level * 0.05

        start = self._peak_started_at
        if start is None:
            return None
        self._peak_started_at = None

        if at - start > self.maximum_peak_seconds:
            # 길게 이어진 소리는 박수가 아니다. 묶음을 버린다.
            self._clap_times.clear()
            return None

        if self._clap_times:
            gap = start - self._clap_times[-1]
            if gap < self.minimum_gap_seconds:
                return None  # 울림. 같은 박수로 본다
            if gap > self.maximum_gap_seconds:
                self._clap_times.clear()  # 너무 늦었다. 새 묶음으로

        self._clap_times.append(start)
        if len(self._clap_times) >= self.required_claps:
            count = len(self._clap_times)
            self._clap_times.clear()
            return count
        return None

    def expire(self, at: float) -> None:
        """조용한 구간이 길면 묶음을 버린다."""
        if self._clap_times and at - self._clap_times[-1] > self.maximum_gap_seconds:
            self._clap_times.clear()


def root_mean_square(samples) -> float:
    """오디오 버퍼의 크기. 진폭의 제곱평균제곱근이 소리 크기에 가장 가깝다."""
    total = 0.0
    count = 0
    for value in samples:
        total += value * value
        count += 1
    return (total / count) ** 0.5 if count else 0.0
