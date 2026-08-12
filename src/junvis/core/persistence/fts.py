"""FTS5 질의 정제.

사용자 입력을 그대로 `MATCH`에 넘기면 따옴표 하나로 질의가 깨진다.
이 정제를 feature마다 복사해 두면 한쪽만 고쳐지는 날이 온다. 사용자 입력을
다루는 코드는 한 곳에 있어야 한다.
"""

from __future__ import annotations

import re

#: FTS5 문법 문자를 버리고 토큰만 남긴다. 한글·영숫자와 `.` `+` `#` `-`만 통과.
_TOKEN = re.compile(r"[\w가-힣.+#-]+", re.UNICODE)


def fts_expression(query: str) -> str | None:
    """안전한 FTS5 식으로 바꾼다. 쓸 토큰이 없으면 None.

    `AND`가 아니라 `OR`인 이유: 개인 규모의 검색은 정밀도보다 재현율이
    중요하다. 찾는 것이 안 나오는 편이 관련 없는 것이 섞이는 것보다 나쁘다.
    접미 `*`로 접두 검색을 허용한다.
    """
    tokens = _TOKEN.findall(query or "")
    if not tokens:
        return None
    return " OR ".join(f'"{token}"*' for token in tokens)
