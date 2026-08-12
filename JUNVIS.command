#!/usr/bin/env bash
# 더블클릭 한 번으로 JUNVIS를 최신화하고 실행한다.
#
# Finder에서 이 파일을 더블클릭하면 터미널이 열리고 이 스크립트가 돈다.
# 그래서 시작 디렉터리가 홈이다 — 무조건 스크립트 위치로 옮겨야 한다.
#
# 이 파일이 지키는 원칙: **사용자의 작업을 절대 지우지 않는다.**
# 수정 중인 파일이 있으면 git pull을 건너뛰고 그 사실을 말한다.
# 조용히 stash 하는 도구는 한 번 신뢰를 잃으면 끝이다.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE}"

VENV="${HERE}/.venv"
STAMP="${VENV}/.junvis-installed"
JUNVIS="${VENV}/bin/junvis"

BOLD=$'\033[1m'
DIM=$'\033[2m'
WARN=$'\033[33m'
FAIL=$'\033[31m'
OFF=$'\033[0m'

say() { printf '%s\n' "$*"; }
step() { printf '\n%s%s%s\n' "${BOLD}" "$*" "${OFF}"; }
note() { printf '  %s%s%s\n' "${DIM}" "$*" "${OFF}"; }
warn() { printf '  %s%s%s\n' "${WARN}" "$*" "${OFF}"; }
fail() { printf '  %s%s%s\n' "${FAIL}" "$*" "${OFF}"; }

hold() {
    printf '\n%s엔터를 누르면 창을 닫습니다.%s ' "${DIM}" "${OFF}"
    read -r _ || true
}

# -- 1. 최신화 ---------------------------------------------------------------

update() {
    step "1. 코드 최신화"

    if ! command -v git >/dev/null 2>&1; then
        warn "git이 없습니다. 최신화를 건너뜁니다."
        return
    fi

    local branch
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || {
        warn "git 저장소가 아닙니다. 최신화를 건너뜁니다."
        return
    }

    # 추적되지 않는 파일은 막지 않는다. 스크린샷 하나 남겨 뒀다고 영영
    # 최신화가 안 되면 안 된다. 충돌하면 git이 알아서 거부한다.
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warn "수정 중인 파일이 있어 최신화를 건너뜁니다 (작업을 지우지 않습니다)."
        note "정리하려면: git stash  또는  git checkout ."
        return
    fi

    note "브랜치: ${branch}"
    # 오프라인이어도 실행은 계속돼야 한다. 최신화는 편의지 전제가 아니다.
    if git pull --ff-only origin "${branch}" 2>&1 | sed 's/^/  /'; then
        :
    else
        warn "최신화하지 못했습니다 (네트워크?). 지금 있는 코드로 계속합니다."
    fi
}

# -- 2. 설치 -----------------------------------------------------------------

python_bin() {
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "${candidate}" >/dev/null 2>&1; then
            printf '%s' "${candidate}"
            return 0
        fi
    done
    return 1
}

install() {
    step "2. 실행 환경"

    if [[ ! -x "${VENV}/bin/python" ]]; then
        local python
        python="$(python_bin)" || {
            fail "Python을 찾지 못했습니다. https://www.python.org 에서 3.11 이상을 설치하세요."
            hold
            exit 1
        }
        note "가상환경을 만듭니다 (${python})"
        "${python}" -m venv "${VENV}" || {
            fail "가상환경을 만들지 못했습니다."
            hold
            exit 1
        }
        rm -f "${STAMP}"
    fi

    # pyproject가 바뀌었을 때만 다시 설치한다. 매번 하면 시작이 느려진다.
    if [[ ! -f "${STAMP}" || "${HERE}/pyproject.toml" -nt "${STAMP}" || ! -x "${JUNVIS}" ]]; then
        note "의존성을 설치합니다… (처음 한 번은 조금 걸립니다)"
        if install_package; then
            touch "${STAMP}"
        else
            fail "설치에 실패했습니다. 위 메시지를 그대로 보내주세요."
            hold
            exit 1
        fi
    fi

    # 이 창 안에서만 PATH를 넓힌다. 이렇게 해야 `junvis setup`이 junvis-mcp를
    # 찾고, 아래 메뉴가 junvis-mac을 찾는다. 셸 설정은 건드리지 않는다.
    export PATH="${VENV}/bin:${HOME}/.local/bin:${PATH}"
    note "준비됨: ${JUNVIS}"
}

install_package() {
    # uv가 있으면 uv로. 이 가상환경이 uv로 만들어졌다면 pip이 아예 없다.
    if command -v uv >/dev/null 2>&1; then
        VIRTUAL_ENV="${VENV}" uv pip install --quiet -e "${HERE}" && return 0
    fi
    if ! "${VENV}/bin/python" -m pip --version >/dev/null 2>&1; then
        "${VENV}/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi
    "${VENV}/bin/python" -m pip install --quiet -e "${HERE}"
}

# -- 3. 실행 -----------------------------------------------------------------

#: 네이티브 헬퍼가 있으면 상시 대기·박수를, 없으면 있는 것으로 듣는다.
listen_flags() {
    if command -v "${JUNVIS_MAC_BIN:-junvis-mac}" >/dev/null 2>&1; then
        printf '%s' "--native"
    fi
}

menu() {
    local flags
    flags="$(listen_flags)"

    step "3. 무엇을 할까요"
    if [[ -n "${flags}" ]]; then
        say "  1) 듣기 — 호출어 또는 박수 두 번   ${DIM}(기본)${OFF}"
    else
        say "  1) 듣기 — 호출어로 시작            ${DIM}(기본)${OFF}"
        note "   박수 두 번을 쓰려면: ./scripts/build-mac.sh"
    fi
    say "  2) 오늘 브리핑"
    say "  3) 상태 점검"
    say "  4) 직접 입력 (마이크 없이 텍스트로)"
    say "  5) 그냥 종료"
    printf '\n선택 [1]: '

    local choice
    read -r choice || choice=5
    echo

    case "${choice:-1}" in
        1) "${JUNVIS}" listen ${flags} ;;
        2) "${JUNVIS}" brief ;;
        3) "${JUNVIS}" setup ;;
        4) "${JUNVIS}" listen --stdin ;;
        5) return 0 ;;
        *) warn "모르는 선택입니다: ${choice}" ;;
    esac
}

clear
say "${BOLD}JUNVIS${OFF}  ${DIM}${HERE}${OFF}"

update
install
menu
hold
