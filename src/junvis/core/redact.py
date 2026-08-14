"""남기기 전에 비밀을 지운다.

ScreenPipe에 `screenpipe-redact` 크레이트가 따로 있는 이유가 있다(docs/10 §6).
**다 기록하면 비밀도 같이 기록된다.**

JUNVIS에도 같은 구멍이 있었다. Trace는 모든 유스케이스의 입력을 남기고,
자동 기억은 대화에서 사실을 뽑는다. 그 길로 이런 것이 들어온다.

- 프로젝트를 스캔하다 `.env`의 내용을 읽는다
- 대화 중에 "이 키 좀 봐줘, sk-ant-..." 하고 말한다
- 릴스 주제에 API 주소와 토큰이 섞여 들어간다

한 번 SQLite에 들어가면 백업에도, digest에도, 프롬프트에도 실린다.

## 무엇을 하지 않는가

**완벽한 탐지를 노리지 않는다.** 그건 불가능하고, 시도하면 오탐으로 멀쩡한
글자를 지운다. 모양이 뚜렷한 것 — 접두사가 정해진 토큰, 개인키 블록,
`KEY=값` 꼴 — 만 잡는다.

지운 자리는 비우지 않고 `[비밀]`로 바꾼다. 흔적이 남아야 사용자가 무슨 일이
있었는지 안다.
"""

from __future__ import annotations

import re

PLACEHOLDER = "[비밀]"

#: 접두사가 뚜렷한 토큰들. 길이 하한을 두어 짧은 우연을 피한다.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Anthropic·OpenAI·Google·Slack·GitHub 계열
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{16,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # Bearer 토큰
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),
    # 개인키 블록. 여러 줄을 통째로 지운다.
    re.compile(
        r"-----BEGIN[^-]{0,40}PRIVATE KEY-----.*?-----END[^-]{0,40}PRIVATE KEY-----",
        re.DOTALL,
    ),
    # URL에 박힌 자격증명
    re.compile(r"(?<=://)[^\s/:@]+:[^\s/@]+(?=@)"),
)

#: `KEY=값` 꼴. 이름이 비밀스러우면 값만 지운다.
_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|APIKEY|API_KEY|ACCESS_KEY|"
    r"PRIVATE_KEY|CREDENTIAL)[A-Z0-9_]*)\s*[=:]\s*(\"[^\"]+\"|'[^']+'|\S+)"
)

#: 이보다 짧은 값은 지우지 않는다. "TOKEN=1" 같은 예시까지 가릴 이유가 없다.
MIN_SECRET_LENGTH = 8


def redact(text: str) -> str:
    """비밀로 보이는 것을 `[비밀]`로 바꾼다. 아니면 그대로 돌려준다."""
    if not text:
        return text

    cleaned = text
    for pattern in _PATTERNS:
        cleaned = pattern.sub(PLACEHOLDER, cleaned)
    return _ASSIGNMENT.sub(_mask_value, cleaned)


def looks_secret(text: str) -> bool:
    """지울 것이 있는가. 저장 자체를 거를 때 쓴다."""
    return redact(text) != text


def _mask_value(match: re.Match[str]) -> str:
    name, value = match.group(1), match.group(2).strip("\"'")
    if len(value) < MIN_SECRET_LENGTH:
        return match.group(0)
    return f"{name}={PLACEHOLDER}"
