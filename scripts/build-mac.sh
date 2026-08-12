#!/usr/bin/env bash
# 네이티브 헬퍼 `junvis-mac`을 빌드해 PATH에 놓는다.
#
# 이 저장소는 Linux에서 개발됐다. Swift 코드는 **컴파일 확인되지 않았다**.
# 빌드가 깨지면 그건 예상된 일이며, 계약(JSON Lines)이 고정돼 있으므로
# Swift만 고치면 Python 쪽은 그대로 동작한다.
# (docs/08-NATIVE-HELPER.md)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="${HERE}/native/junvis-mac"
INSTALL_DIR="${JUNVIS_BIN_DIR:-${HOME}/.local/bin}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "네이티브 헬퍼는 macOS 전용입니다." >&2
    exit 1
fi

if ! command -v swift >/dev/null 2>&1; then
    echo "Swift를 찾지 못했습니다. Xcode 또는 Command Line Tools를 설치하세요:" >&2
    echo "  xcode-select --install" >&2
    exit 1
fi

echo "빌드 중… (${PACKAGE_DIR})"
cd "${PACKAGE_DIR}"
swift build -c release

BINARY="$(swift build -c release --show-bin-path)/junvis-mac"
if [[ ! -x "${BINARY}" ]]; then
    echo "빌드는 됐는데 실행 파일을 찾지 못했습니다: ${BINARY}" >&2
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
