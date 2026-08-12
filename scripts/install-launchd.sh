#!/usr/bin/env bash
# JUNVIS의 정기 작업을 launchd에 등록한다.
#
#   com.zun.junvis.refresh  — N시간마다 프로젝트 스냅샷 갱신
#   com.zun.junvis.brief    — 평일 아침 브리핑 + 알림
#
# 자체 상주 데몬을 띄우지 않는다. macOS에는 이미 launchd가 있고,
# 재부팅·로그아웃·절전 복귀를 OS가 알아서 처리해 준다.
# (docs/01-ANALYSIS.md §8, docs/04-DAILY-BRIEF.md §0)
set -euo pipefail

AGENTS_DIR="${HOME}/Library/LaunchAgents"
REFRESH_LABEL="com.zun.junvis.refresh"
BRIEF_LABEL="com.zun.junvis.brief"

INTERVAL_SECONDS="${JUNVIS_REFRESH_INTERVAL:-21600}"  # 기본 6시간
BRIEF_HOUR="${JUNVIS_BRIEF_HOUR:-9}"
BRIEF_MINUTE="${JUNVIS_BRIEF_MINUTE:-0}"
LOG_DIR="${JUNVIS_HOME:-${HOME}/.junvis}/logs"

usage() {
    cat <<'EOF'
사용법: install-launchd.sh [옵션]

  (인자 없음)      스냅샷 갱신 + 아침 브리핑을 모두 등록한다
  --uninstall      등록을 모두 해제한다
  --interval N     스냅샷 갱신 주기를 N초로 (기본 21600 = 6시간)
  --brief-hour H   브리핑 시각 (0-23, 기본 9)
  --brief-minute M 브리핑 분 (기본 0)
  --refresh-only   스냅샷 갱신만 등록한다
  --brief-only     브리핑만 등록한다
EOF
}

bootout() {
    launchctl bootout "gui/$(id -u)/$1" 2>/dev/null || true
}

uninstall() {
    local removed=0
    for label in "${REFRESH_LABEL}" "${BRIEF_LABEL}"; do
        if [[ -f "${AGENTS_DIR}/${label}.plist" ]]; then
            bootout "${label}"
            rm -f "${AGENTS_DIR}/${label}.plist"
            echo "해제했습니다: ${label}"
            removed=1
        fi
    done
    [[ ${removed} -eq 0 ]] && echo "등록되어 있지 않습니다."
    return 0
}

INSTALL_REFRESH=1
INSTALL_BRIEF=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --uninstall)    uninstall; exit 0 ;;
        --interval)     INTERVAL_SECONDS="$2"; shift 2 ;;
        --brief-hour)   BRIEF_HOUR="$2"; shift 2 ;;
        --brief-minute) BRIEF_MINUTE="$2"; shift 2 ;;
        --refresh-only) INSTALL_BRIEF=0; shift ;;
        --brief-only)   INSTALL_REFRESH=0; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              echo "알 수 없는 인자: $1" >&2; usage; exit 1 ;;
    esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "launchd는 macOS 전용입니다. (JUNVIS는 macOS를 최우선으로 설계합니다)" >&2
    exit 1
fi

JUNVIS_BIN="$(command -v junvis || true)"
if [[ -z "${JUNVIS_BIN}" ]]; then
    echo 'junvis 실행 파일을 찾지 못했습니다. 먼저 `uv pip install -e .` 를 실행하세요.' >&2
    exit 1
fi

mkdir -p "${AGENTS_DIR}" "${LOG_DIR}"

# $1=label  $2=로그 이름  $3...=ProgramArguments 뒤에 붙일 스케줄 XML
write_plist() {
    local label="$1" logname="$2" args_xml="$3" schedule_xml="$4"
    cat > "${AGENTS_DIR}/${label}.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${label}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${JUNVIS_BIN}</string>
${args_xml}
    </array>

${schedule_xml}

    <!-- 배터리로 동작 중일 때는 미루게 둔다 -->
    <key>LowPriorityIO</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/${logname}.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/${logname}.error.log</string>
</dict>
</plist>
EOF
    bootout "${label}"
    launchctl bootstrap "gui/$(id -u)" "${AGENTS_DIR}/${label}.plist"
}

if [[ ${INSTALL_REFRESH} -eq 1 ]]; then
    write_plist "${REFRESH_LABEL}" "refresh" \
        "        <string>refresh</string>" \
        "    <key>StartInterval</key>
    <integer>${INTERVAL_SECONDS}</integer>

    <!-- 등록 직후 한 번 돌려 첫 스냅샷을 만든다 -->
    <key>RunAtLoad</key>
    <true/>"
    echo "등록했습니다: ${REFRESH_LABEL} (${INTERVAL_SECONDS}초마다)"
fi

if [[ ${INSTALL_BRIEF} -eq 1 ]]; then
    # 평일(월~금)에만. 주말 아침까지 알림이 오면 그건 비서가 아니라 알람이다.
    schedule="    <key>StartCalendarInterval</key>
    <array>"
    for weekday in 1 2 3 4 5; do
        schedule+="
        <dict>
            <key>Weekday</key><integer>${weekday}</integer>
            <key>Hour</key><integer>${BRIEF_HOUR}</integer>
            <key>Minute</key><integer>${BRIEF_MINUTE}</integer>
        </dict>"
    done
    schedule+="
    </array>"

    write_plist "${BRIEF_LABEL}" "brief" \
        "        <string>brief</string>
        <string>--notify</string>" \
        "${schedule}"
    printf '등록했습니다: %s (평일 %02d:%02d)\n' "${BRIEF_LABEL}" "${BRIEF_HOUR}" "${BRIEF_MINUTE}"
fi

echo "  로그 : ${LOG_DIR}/"
echo "  해제 : $0 --uninstall"
