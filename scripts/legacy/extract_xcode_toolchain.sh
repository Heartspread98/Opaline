#!/usr/bin/env bash
# Extract only compiler/runtime and iPhoneOS SDK from a user-downloaded Apple XIP.
# Run inside WSL as the build user. No system Xcode install, no license acceptance.
set -euo pipefail
XIP="${1:?usage: extract_xcode_toolchain.sh /path/to/Xcode_12.5.1.xip}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="${LEGACY_TOOLS:-$HOME/legacy-ios9/toolchain}/xc12"
[ -f "$XIP" ] || { echo "Missing XIP: $XIP" >&2; exit 1; }
command -v bsdtar >/dev/null
command -v cpio >/dev/null
# Never merge with an incomplete or different pre-existing installation.
[ ! -e "$DEST" ] || { echo "Destination already exists: $DEST" >&2; exit 1; }
mkdir -p "$DEST"
echo "Extracting compiler, runtime and iPhoneOS SDK into $DEST"
cd "$DEST"
bsdtar -xOf "$XIP" Content \
    | python3 "$REPO/scripts/legacy/pbzx_stream.py" \
    | cpio --extract --make-directories --no-absolute-filenames --preserve-modification-time \
        'Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/*' \
        './Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/*' \
        'Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/*' \
        './Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/*'
test -x "$DEST/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc"
test -d "$DEST/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS14.5.sdk"
echo "Extraction finished. Compiler execution is the next gate."
