"""V3: 판정·정제 로직. 오디오 I/O 자체는 이 저장소에서 검증되지 않는다."""

from __future__ import annotations

import io
import json

from junvis.core.model.echo import EchoAdapter
from junvis.core.model.ports import ModelRole
from junvis.features.voice.infrastructure.audio import StdinSource, clean_transcript
from junvis.features.voice.infrastructure.intent_judge import (
    JUDGE_SCHEMA,
    LlmIntentJudge,
)
from junvis.features.voice.infrastructure.tts import MacSayTts, NullTts, default_tts


# -- Intent Judge ------------------------------------------------------------


def judge_with(payload) -> tuple[LlmIntentJudge, EchoAdapter]:
    model = EchoAdapter([payload if isinstance(payload, str) else json.dumps(payload)])
    return LlmIntentJudge(model), model


def test_positive_verdict() -> None:
    judge, _ = judge_with({"is_command": True, "reason": "브리핑 요청"})
    assert judge.is_command("오늘 브리핑") is True


def test_negative_verdict() -> None:
    judge, _ = judge_with({"is_command": False, "reason": "혼잣말"})
    assert judge.is_command("어 잠깐만") is False


def test_uses_the_fast_model_deterministically() -> None:
    """판정에 큰 모델을 부르면 말 한마디마다 몇 초씩 기다리게 된다."""
    judge, model = judge_with({"is_command": True})
    judge.is_command("브리핑")

    sent = model.calls[0]
    assert sent.role is ModelRole.FAST
    assert sent.temperature == 0.0
    assert sent.schema == JUDGE_SCHEMA
    assert "브리핑" in sent.prompt


def test_code_fenced_response_is_handled() -> None:
    judge, _ = judge_with('```json\n{"is_command": false}\n```')
    assert judge.is_command("음...") is False


def test_unreadable_response_fails_open() -> None:
    """사용자를 무시하는 것이 잘못 실행하는 것보다 나쁜 실패다."""
    for garbage in ["죄송합니다", "[]", "{}", '{"other": 1}']:
        judge, _ = judge_with(garbage)
        assert judge.is_command("브리핑") is True


# -- 받아쓰기 정제 -----------------------------------------------------------


def test_multiline_transcript_is_joined() -> None:
    assert clean_transcript(" 오늘 \n 브리핑 \n\n") == "오늘 브리핑"


def test_silence_hallucinations_are_dropped() -> None:
    """조용한 방에서 JUNVIS가 혼자 '감사합니다'에 반응하면 안 된다."""
    for noise in ["감사합니다", " 시청해주셔서 감사합니다. ", "[음악]", "Thank you for watching"]:
        assert clean_transcript(noise) == ""


def test_real_speech_containing_thanks_is_kept() -> None:
    assert clean_transcript("자비스 감사합니다 브리핑 부탁해") != ""


def test_empty_transcript() -> None:
    assert clean_transcript("   \n  ") == ""


# -- 입력 소스 ---------------------------------------------------------------


def test_stdin_source_yields_one_utterance_per_line() -> None:
    stream = io.StringIO("자비스 브리핑\n\n  \n프로젝트 목록\n")
    texts = [u.text for u in StdinSource(stream).listen()]
    assert texts == ["자비스 브리핑", "프로젝트 목록"]


# -- TTS ---------------------------------------------------------------------


def test_null_tts_records_instead_of_speaking() -> None:
    tts = NullTts()
    assert tts.speak("안녕하세요") is True
    assert tts.speak("   ") is False
    assert tts.spoken == ["안녕하세요"]


def test_mac_say_is_a_no_op_off_macos() -> None:
    # 테스트 환경은 Linux다. 플랫폼 검사가 subprocess 호출 자체를 막는다.
    assert MacSayTts().speak("안녕") is False


def test_default_tts_picks_null_off_macos() -> None:
    assert isinstance(default_tts(), NullTts)


def test_audible_distinguishes_accepted_from_heard() -> None:
    """NullTts의 True는 '받아들였다'이지 '소리가 났다'가 아니다.

    파이프라인은 이걸로 끊기면 안 되지만, `junvis say`는 사실대로
    말해야 한다.
    """
    assert NullTts().audible is False
    assert MacSayTts().audible is True
