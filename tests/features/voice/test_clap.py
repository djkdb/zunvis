"""박수 감지 — 오탐이 이 기능의 전부다.

Swift에 있을 때는 한 줄도 검증할 수 없었다. Python으로 옮긴 값어치가
여기 있다: 문 닫는 소리와 박수를 구분하는 규칙을 실제로 시험한다.
"""

from __future__ import annotations

from junvis.features.voice.infrastructure.clap import ClapDetector, root_mean_square

#: 버퍼 하나의 길이(초). 44.1kHz에서 1024 프레임이면 대략 이 정도다.
TICK = 0.023
QUIET = 0.01
LOUD = 0.9


def feed(detector: ClapDetector, pattern: list[tuple[float, float]]) -> list[int]:
    """(크기, 지속 시간) 목록을 흘려 넣고 감지된 묶음을 모은다."""
    found: list[int] = []
    now = 0.0
    for level, seconds in pattern:
        elapsed = 0.0
        while elapsed < seconds:
            now += TICK
            elapsed += TICK
            detector.expire(now)
            count = detector.feed(level, now)
            if count is not None:
                found.append(count)
    return found


def clap(gap: float = 0.3, *, peak: float = 0.05) -> list[tuple[float, float]]:
    return [(LOUD, peak), (QUIET, gap)]


def test_two_claps_are_detected() -> None:
    detector = ClapDetector()

    assert feed(detector, [(QUIET, 1.0), *clap(), *clap()]) == [2]


def test_one_clap_is_not_enough() -> None:
    """한 번은 부름이 아니다. 손뼉 한 번은 일상에서 너무 자주 난다."""
    detector = ClapDetector()

    assert feed(detector, [(QUIET, 1.0), *clap()]) == []


def test_a_long_bang_is_not_a_clap() -> None:
    """문 닫는 소리. 크지만 길다."""
    detector = ClapDetector()

    pattern = [(QUIET, 1.0), (LOUD, 0.5), (QUIET, 0.3), (LOUD, 0.5), (QUIET, 0.3)]

    assert feed(detector, pattern) == []


def test_speech_is_not_a_clap() -> None:
    """말소리는 크기가 이어진다. 짧은 피크가 아니다."""
    detector = ClapDetector()

    speech = [(0.3, 0.4), (0.15, 0.2), (0.35, 0.5), (0.1, 0.3)] * 3

    assert feed(detector, [(QUIET, 1.0), *speech]) == []


def test_an_echo_right_after_a_clap_is_the_same_clap() -> None:
    """울리는 방. 100ms 뒤의 반사음을 두 번째 박수로 세면 안 된다."""
    detector = ClapDetector()

    pattern = [(QUIET, 1.0), *clap(gap=0.08), *clap(gap=0.3)]
    # 첫 박수 + 울림(무시) + 진짜 두 번째 = 묶음 하나
    assert feed(detector, pattern) == [2]


def test_claps_too_far_apart_are_not_a_pair() -> None:
    """2초 간격은 부름이 아니라 그냥 두 번의 소리다."""
    detector = ClapDetector()

    assert feed(detector, [(QUIET, 1.0), *clap(gap=2.0), *clap(gap=0.3)]) == []


def test_a_third_clap_starts_a_new_group() -> None:
    """묶음이 완성되면 비운다. 세 번째가 두 번째 묶음을 만들면 안 된다."""
    detector = ClapDetector()

    pattern = [(QUIET, 1.0), *clap(), *clap(), *clap()]

    assert feed(detector, pattern) == [2]


def test_four_claps_are_two_groups() -> None:
    detector = ClapDetector()

    pattern = [(QUIET, 1.0), *clap(), *clap(), *clap(), *clap()]

    assert feed(detector, pattern) == [2, 2]


def test_the_noise_floor_follows_a_loud_room() -> None:
    """카페처럼 시끄러운 곳에서는 기준선이 올라가 잔소리를 무시한다."""
    detector = ClapDetector()
    feed(detector, [(0.04, 5.0)])

    assert detector.noise_floor > 0.03
    assert detector.threshold > detector.minimum_level


def test_the_noise_floor_does_not_rise_during_a_peak() -> None:
    """박수 소리로 기준선이 올라가면 두 번째 박수를 놓친다."""
    detector = ClapDetector()
    feed(detector, [(QUIET, 2.0)])
    quiet_floor = detector.noise_floor

    feed(detector, [(LOUD, 0.05)])

    assert detector.noise_floor == quiet_floor


def test_required_claps_can_be_three() -> None:
    two = ClapDetector(required_claps=3)
    assert feed(two, [(QUIET, 1.0), *clap(), *clap()]) == []

    three = ClapDetector(required_claps=3)
    assert feed(three, [(QUIET, 1.0), *clap(), *clap(), *clap()]) == [3]


def test_root_mean_square() -> None:
    assert root_mean_square([]) == 0.0
    assert root_mean_square([0.0, 0.0]) == 0.0
    assert root_mean_square([1.0, -1.0]) == 1.0
    assert round(root_mean_square([0.5, -0.5, 0.5, -0.5]), 6) == 0.5
