#!/usr/bin/env bash
# 네이티브 헬퍼 `junvis-mac`을 빌드해 PATH에 놓는다.
#
# **SwiftPM을 쓰지 않는다.** Command Line Tools에 딸려 오는 SwiftPM은
# PackageDescription 라이브러리와 버전이 어긋나면 `Invalid manifest`로
# 죽는다(실제로 겪었다). 의존성이 하나도 없는 파일 다섯 개짜리 도구에
# 패키지 매니저는 얻는 것 없이 깨질 곳만 늘린다. swiftc로 직접 컴파일한다.
#
# Swift 코드는 Linux에서 작성됐다. 빌드가 깨지면 오류 메시지를 그대로
# 보내주면 된다 — 계약(JSON Lines)이 고정돼 있으므로 Swift만 고치면
# Python 쪽은 그대로 동작한다. (docs/08-NATIVE-HELPER.md)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${HERE}/native/junvis-mac"
INSTALL_DIR="${JUNVIS_BIN_DIR:-${HOME}/.local/bin}"
BINARY="${SOURCE_DIR}/junvis-mac"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "네이티브 헬퍼는 macOS 전용입니다." >&2
    exit 1
fi

if ! command -v swiftc >/dev/null 2>&1; then
    echo "Swift를 찾지 못했습니다. Command Line Tools를 설치하세요:" >&2
    echo "  xcode-select --install" >&2
    exit 1
fi

echo "빌드 중… ($(swiftc --version 2>/dev/null | head -1))"

# 시스템 프레임워크만 링크한다. 내려받는 것이 없으므로 오프라인에서도 된다.
# Info.plist는 실행 파일 안에 심는다 — 이것이 없으면 macOS가 마이크 권한을
# 물어보지 않고 그냥 거부한다.
swiftc \
    -O \
    -o "${BINARY}" \
    "${SOURCE_DIR}"/*.swift \
    -framework AVFoundation \
    -framework Speech \
    -framework EventKit \
    -Xlinker -sectcreate \
    -Xlinker __TEXT \
    -Xlinker __info_plist \
    -Xlinker "${SOURCE_DIR}/Info.plist"

if [[ ! -x "${BINARY}" ]]; then
    echo "빌드는 끝났는데 실행 파일이 없습니다: ${BINARY}" >&2
    exit 1
fi

mkdir -p "${INSTALL_DIR}"
cp "${BINARY}" "${INSTALL_DIR}/junvis-mac"
echo "설치했습니다: ${INSTALL_DIR}/junvis-mac"

if ! command -v junvis-mac >/dev/null 2>&1; then
    echo
    echo "PATH에 없습니다. 셸 설정에 추가하세요:"
    echo "  export PATH=\"${INSTALL_DIR}:\$PATH\""
fi

echo
echo "다음 단계:"
echo "  junvis-mac check       # 권한 확인"
echo "  junvis-mac calibrate   # 박수 임계값 측정"
echo "  junvis listen --native # JUNVIS에 붙여서 확인"
