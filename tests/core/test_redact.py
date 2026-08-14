"""남기기 전에 비밀을 지운다 (docs/10 §6).

한 번 SQLite에 들어가면 백업에도, digest에도, 프롬프트에도 실린다.
"""

from __future__ import annotations

import pytest

from junvis.core.redact import PLACEHOLDER, looks_secret, redact


@pytest.mark.parametrize(
    "text",
    [
        "키는 sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456 입니다",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_11ABCDEFG0abcdefghijklmnop",
        "xoxb-1234567890-abcdefghij",
        "AIzaSyA1234567890abcdefghijklmnopqrstu",
        "AKIAIOSFODNN7EXAMPLE",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "https://zun:hunter2secret@example.com/repo.git",
    ],
)
def test_secrets_are_removed(text: str) -> None:
    assert PLACEHOLDER in redact(text)
    assert looks_secret(text)


def test_a_private_key_block_goes_whole() -> None:
    """여러 줄이라도 통째로 지운다. 한 줄만 남아도 의미가 없다."""
    text = (
        "설정입니다\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA1234\nabcd5678\n"
        "-----END RSA PRIVATE KEY-----\n"
        "여기까지"
    )
    cleaned = redact(text)

    assert "MIIEowIBAAKCAQEA1234" not in cleaned
    assert "BEGIN RSA PRIVATE KEY" not in cleaned
    assert "설정입니다" in cleaned and "여기까지" in cleaned


def test_assignments_keep_the_name_and_lose_the_value() -> None:
    """이름은 남겨야 무슨 일이 있었는지 안다."""
    cleaned = redact('GITHUB_TOKEN="abcdefghijklmnop"\nDB_PASSWORD=supersecret123')

    assert "GITHUB_TOKEN" in cleaned
    assert "abcdefghijklmnop" not in cleaned
    assert "supersecret123" not in cleaned


def test_short_values_are_left_alone() -> None:
    """`TOKEN=1` 같은 예시까지 가릴 이유가 없다."""
    assert redact("TOKEN=1") == "TOKEN=1"


@pytest.mark.parametrize(
    "text",
    [
        "오늘 브리핑 좀 보여줘",
        "릴스 썸네일은 세 단어 이하로",
        "https://github.com/djkdb/zunvis 를 등록해줘",
        "sk-",
        "이 프로젝트는 Python으로 만들었다",
        "커밋 a1b2c3d 확인해줘",
    ],
)
def test_ordinary_text_is_untouched(text: str) -> None:
    """오탐으로 멀쩡한 글자를 지우면 기억이 망가진다."""
    assert redact(text) == text
    assert not looks_secret(text)


def test_empty_is_safe() -> None:
    assert redact("") == ""
