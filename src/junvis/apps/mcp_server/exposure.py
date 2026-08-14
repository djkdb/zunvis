"""도구 말고도 내놓는 것 — 리소스와 프롬프트.

MCP를 도구로만 쓰고 있었다(docs/10 §7). 명세에는 셋이 있고 각자 하는 일이
다르다.

| | 무엇인가 | 누가 고르는가 |
|---|---|---|
| tool | 모델이 부르는 함수 | 모델 |
| resource | 붙일 수 있는 읽을거리 | **사람** |
| prompt | 시작점이 되는 문장 | **사람** |

지금까지는 Claude Code가 `junvis_project_context`를 **도구로 부를 생각을
해야** 컨텍스트가 갔다. 리소스로 내놓으면 사람이 파일처럼 붙인다. Context
Pack은 이름부터가 resource다.

프롬프트도 마찬가지다. "릴스 만들기"를 노출하면 슬래시 명령으로 뜬다.
사용자가 도구 이름을 외울 필요가 없어진다.
"""

from __future__ import annotations

import logging

from junvis.apps.container import Junvis

logger = logging.getLogger(__name__)

SCHEME = "junvis"

#: Context Pack에 실을 토큰 예산. 리소스로 붙는 것이라 도구보다 넉넉하게.
RESOURCE_BUDGET = 3000


def list_projects_as_resources(container: Junvis) -> list[tuple[str, str, str]]:
    """(uri, 이름, 설명) 목록. 프로젝트 하나가 리소스 하나다."""
    resources = []
    for summary in container.projects.list_all():
        purpose = summary.purpose or "목적이 적혀 있지 않습니다"
        stack = ", ".join(summary.tech_stack[:4])
        detail = f"{purpose}{f' · {stack}' if stack else ''}"
        resources.append(
            (f"{SCHEME}://project/{summary.slug}", summary.name, detail)
        )
    return resources


def read_project_resource(container: Junvis, uri: str) -> str:
    """`junvis://project/<slug>` → Context Pack 마크다운."""
    slug = _slug_from(uri)
    if not slug:
        raise ValueError(f"읽을 수 없는 주소입니다: {uri}")
    return container.projects.load_context(slug, budget_tokens=RESOURCE_BUDGET).to_markdown()


def _slug_from(uri: str) -> str:
    prefix = f"{SCHEME}://project/"
    return uri[len(prefix) :].strip("/") if uri.startswith(prefix) else ""


#: 프롬프트 하나 = (이름, 설명, 인자 이름들, 본문 만드는 함수)
#:
#: 본문은 **명령이 아니라 요청**이다. Claude Code가 이걸 받아서 우리 도구를
#: 부르게 된다 — 여기서 직접 실행하지 않는다. 프롬프트는 시작점이지
#: 실행 경로가 아니다.
PROMPTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "reel",
        "ZUN 브랜드 릴스 기획을 만든다",
        ("subject",),
    ),
    (
        "brief",
        "오늘 챙길 것을 우선순위대로 정리한다",
        (),
    ),
    (
        "project_review",
        "프로젝트 하나를 CTO 시선으로 점검한다",
        ("slug",),
    ),
)


def build_prompt(name: str, arguments: dict[str, str]) -> str:
    """프롬프트 본문. JUNVIS 도구를 쓰라고 이름을 짚어 준다."""
    if name == "reel":
        subject = arguments.get("subject", "").strip()
        target = f'"{subject}" 주제로' if subject else "대기 중인 제안 중 하나로"
        return (
            f"{target} ZUN 브랜드 릴스 기획을 만들어 주세요.\n"
            "`junvis_content_create` 도구를 쓰면 훅·장면·대본·캡션·해시태그가"
            " 한 번에 나옵니다. 만들기 전에 `junvis_brand_voice`로 톤을,"
            " `junvis_recall`로 제가 기억시킨 규칙을 확인해 주세요."
        )
    if name == "brief":
        return (
            "오늘 무엇부터 하면 좋을지 알려 주세요.\n"
            "`junvis_daily_brief` 도구가 멈춰 있는 작업·아이디어·프로젝트를"
            " 우선순위대로 모아 줍니다. 그걸 보고 **가장 먼저 할 일 하나**를"
            " 골라 이유와 함께 말해 주세요."
        )
    if name == "project_review":
        slug = arguments.get("slug", "").strip()
        which = f"`{slug}` 프로젝트를" if slug else "프로젝트 하나를"
        return (
            f"{which} CTO 시선으로 점검해 주세요.\n"
            "`junvis_project_context`로 목적·스택·최근 커밋·TODO·이슈를 먼저"
            " 가져오세요. 그다음 지금 가장 큰 위험 하나와 다음 한 걸음을"
            " 짚어 주세요. 코드를 고치지는 마세요."
        )
    raise ValueError(f"알 수 없는 프롬프트: {name}")
