#!/usr/bin/env bash
# JUNVIS 스냅샷 자동 갱신을 launchd에 등록한다 (M12).
#
# 자체 상주 데몬을 띄우지 않는다. macOS에는 이미 launchd가 있고,
# 재부팅·로그아웃·절전 복귀를 OS가 알아서 처리해 준다.
set -euo pipefail

LABEL="com.zun.junvis.refresh"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
INTERVAL_SECONDS="${JUNVIS_REFRESH_INTERVAL:-21600}"  # 기본 6시간
LOG_DIR="${JUNVIS_HOME:-${HOME}/.junvis}/logs"

usage() {
    cat <<'EOF'
사용법: install-launchd.sh [--uninstall] [--interval 초]

  (인자 없음)   6시간마다 `junvis refresh`를 돌리도록 등록한다
  --uninstall   등록을 해제한다
  --interval N  갱신 주기를 N초로 지정한다
EOF
}

uninstall() {
    if [[ -f "${PLIST}" ]]; then
        launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
        rm -f "${PLIST}"
        echo "해제했습니다: ${LABEL}"
    else
        echo "등록되어 있지 않습니다."
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --uninstall) uninstall; exit 0 ;;
        --interval)  INTERVAL_SECONDS="$2"; shift 2 ;;
        -h|--help)   usage; exit 0 ;;
        *)           echo "알 수 없는 인자: $1" >&2; usage; exit 1 ;;
    esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "launchd는 macOS 전용입니다. (JUNVIS는 macOS를 최우선으로 설계합니다)" >&2
    exit 1
fi

JUNVIS_BIN="$(command -v junvis || true)"
if [[ -z "${JUNVIS_BIN}" ]]; then
    echo "junvis 실행 파일을 찾지 못했습니다. 먼저 `uv pip install -e .` 를 실행하세요." >&2
    exit 1
fi

mkdir -p "${HOME}/Library/LaunchAgents" "${LOG_DIR}"

cat > "${PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${JUNVIS_BIN}</string>
        <string>refresh</string>
    </array>

    <key>StartInterval</key>
    <integer>${INTERVAL_SECONDS}</integer>

    <!-- 등록 직후 한 번 돌려 첫 스냅샷을 만든다 -->
    <key>RunAtLoad</key>
    <true/>

    <!-- 배터리로 동작 중일 때는 미루게 둔다 -->
    <key>LowPriorityIO</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/refresh.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/refresh.error.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST}"

echo "등록했습니다: ${LABEL}"
echo "  주기 : ${INTERVAL_SECONDS}초마다 'junvis refresh'"
echo "  로그 : ${LOG_DIR}/refresh.log"
echo "  해제 : $0 --uninstall"
