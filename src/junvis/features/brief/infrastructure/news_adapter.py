"""AI 소식을 가져온다 — 사용자의 브랜드 주제로 거른 것만.

브리프의 요구는 "AI 최신 소식(개발과 콘텐츠 제작에 도움이 되는 내용 중심)"이다.
그래서 일반 뉴스 피드를 그대로 붓지 않고, ZUN 브랜드가 다루는 주제와 겹치는
것만 남긴다.

요약은 만들지 않는다. 매일 아침 LLM으로 헤드라인을 요약하는 것은 비용 대비
가치가 낮고, 제목과 링크만으로 열지 말지는 충분히 판단할 수 있다.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from junvis.features.brief.domain.digests import NewsItem

logger = logging.getLogger(__name__)

#: 한 번의 요청으로 프론트페이지를 받는다.
API_URL = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50"
TIMEOUT_SECONDS = 6
SOURCE = "Hacker News"

#: 기본 필터. 단어 단위로 비교하므로 짧은 토큰도 안전하다.
#: "model"·"tool"처럼 AI 맥락 밖에서도 흔한 단어는 일부러 뺐다 —
#: "concurrency model"이 AI 소식으로 올라오면 섹션이 쓸모없어진다.
DEFAULT_KEYWORDS = (
    "ai",
    "llm",
    "llms",
    "gpt",
    "claude",
    "anthropic",
    "openai",
    "gemini",
    "agent",
    "agents",
    "agentic",
    "mcp",
    "ollama",
    "prompt",
    "prompting",
    "rag",
    "embedding",
    "embeddings",
    "transformer",
    "transformers",
    "inference",
    "copilot",
)

#: 단어 추출기. 한글과 영숫자만 남긴다.
_WORD = re.compile(r"[a-z0-9가-힣]+")


class HackerNewsAdapter:
    def __init__(self, *, api_url: str = API_URL, timeout: int = TIMEOUT_SECONDS) -> None:
        self._api_url = api_url
        self._timeout = timeout

    def headlines(
        self, interests: tuple[str, ...], *, limit: int = 5
    ) -> tuple[NewsItem, ...]:
        payload = self._fetch()
        if payload is None:
            return ()
        keywords = self._keywords(interests)
        picked: list[NewsItem] = []
        for hit in payload.get("hits", []):
            title = str(hit.get("title") or "").strip()
            if not title or not self._matches(title, keywords):
                continue
            picked.append(
                NewsItem(
                    title=title,
                    url=str(hit.get("url") or "")
                    or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                    source=SOURCE,
                )
            )
            if len(picked) >= limit:
                break
        return tuple(picked)

    @staticmethod
    def _keywords(interests: tuple[str, ...]) -> tuple[str, ...]:
        """브랜드 주제를 검색어로 쓰되, 기본 AI 키워드도 함께 본다.

        브랜드 주제만 쓰면 한국어 주제("바이브 코딩")가 영어 헤드라인과
        겹치지 않아 매일 빈 섹션이 된다.
        """
        cleaned = tuple(t.strip().lower() for t in interests if t and t.strip())
        return tuple(dict.fromkeys((*cleaned, *DEFAULT_KEYWORDS)))

    @staticmethod
    def _matches(title: str, keywords: tuple[str, ...]) -> bool:
        """단어 경계로 비교한다.

        부분 문자열로 비교하면 "ai"가 "maintain"에, "agent"가 "agentless"에
        걸린다. 여러 단어로 된 관심 주제("바이브 코딩")만 부분 일치를 쓴다.
        """
        lowered = title.lower()
        words = set(_WORD.findall(lowered))
        for keyword in keywords:
            if " " in keyword:
                if keyword in lowered:
                    return True
            elif keyword in words:
                return True
        return False

    def _fetch(self) -> dict | None:
        request = urllib.request.Request(self._api_url, method="GET")
        request.add_header("User-Agent", "junvis")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            logger.debug("뉴스 조회 실패: %s", exc)
            return None
