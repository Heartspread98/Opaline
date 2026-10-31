#!/usr/bin/env bash
# Build a separate test app. Never invoke deploy.sh or make_pages_repo.sh here:
# their defaults target the installed Opaline app and upstream's Pages URL.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOLS="${LEGACY_TOOLS:-$HOME/legacy-ios9/toolchain}"
export BUILD="${LAYOUT_BUILD:-$REPO/build/layout-test}"
export LOG_DIR="$BUILD/logs"
export RUN="$BUILD/run"
export SDK="${SDK:-$TOOLS/xc12/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS14.5.sdk}"
RUNTIME="${RUNTIME:-$TOOLS/xc12/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift-5.0/iphoneos}"
if [ "${1:-}" = "--check" ]; then
    failed=0
    for tool in darling ldid python3; do
        command -v "$tool" >/dev/null || { echo "MISSING tool: $tool"; failed=1; }
    done
    for path in "$SDK" "$RUNTIME"; do
        [ -d "$path" ] || { echo "MISSING directory: $path"; failed=1; }
    done
    echo "Target: armv7-apple-ios9.3; Apple Swift 5.4.2 under Darling"
    exit "$failed"
fi
[ $# -eq 0 ] || { echo "usage: $0 [--check]" >&2; exit 2; }
bash "$0" --check
VERSION="0.1.0~layout.$(date -u +%Y%m%d%H%M%S)"
export BUNDLE_ID=com.heartspread98.opaline.layouttest
export BUNDLE_DISPLAY_NAME="Opaline Test"
export BUNDLE_URL_SCHEME=opaline-layout-test
export BUNDLE_BUILD="$VERSION"
export LAYOUT_TEST=1
export ENTITLEMENTS="$REPO/scripts/legacy/LayoutTest.entitlements"
bash "$REPO/scripts/legacy/build.sh"
python3 "$REPO/scripts/legacy/make_bundle.py" --build "$BUILD" --runtime "$RUNTIME"
# Keep the signed executable named Opaline; only the app directory changes.
python3 "$REPO/scripts/legacy/package_layout_test.py" \
    --app "$BUILD/staging/Opaline.app" --version "$VERSION" \
    --output "$BUILD/repo/debs"
python3 "$REPO/scripts/legacy/make_repo.py" --root "$BUILD/repo"
python3 "$REPO/scripts/legacy/verify_layout_repo.py" --root "$BUILD/repo"
touch "$BUILD/repo/.nojekyll"
echo "Local candidate ready: $BUILD/repo (device validation still required)"
