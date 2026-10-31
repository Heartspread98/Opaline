# iOS 9 player layout test

2026-11-01. Base: Joeviocoe/Opaline `legacy/ios9-integration`, commit
`183bd760aad022995f5d363587f7d33adf0e6e17`.

## What is known

The user's iPod touch 5 / iPad mini 1, iOS 9.3.5, play audio but lose video in
portrait. The supplied screenshots show no reserved portrait video area and a
tiny landscape video above the metadata. Images were inspected locally; personal
screenshots are not included in this public fork.

The cause is a hypothesis until device measurement. `LegacyUIKit.swift` emulates
both scroll layout guides by pinning them to the same edges. That does not
preserve the content/frame distinction of the real iOS 11 API. Watch now uses
the documented pre-iOS 11 pattern: content edges equal scroll edges, content
width equal scroll FRAME width, without a content-height/viewport-height tie.
Automatic scroll insets are disabled because the player already uses the top
layout guide. Layer bounds/position update without implicit CA animation; pinch
zoom's transform remains intact. Modern iOS keeps the native scroll guides.

Source: [Apple's scroll-view Auto Layout guide](https://developer.apple.com/library/archive/documentation/UserExperience/Conceptual/AutolayoutPG/WorkingwithScrollViews.html).

## Preservation of installed Opaline

Use **only** `build_layout_test.sh` for this experiment. The inherited
`deploy.sh`, `make_deb.sh`, `make_pages_repo.sh` and `publish-pages.sh` have
production app paths / package defaults / Joeviocoe URLs. Do not run them to
install this test. Merely changing the Debian package name is insufficient.

| Item | Layout test |
|---|---|
| Debian package / bundle ID | `com.heartspread98.opaline.layouttest` |
| App directory | `/Applications/OpalineLayoutTest.app` |
| Home-screen name | Opaline Test |
| Executable | Opaline |
| URL scheme | `opaline-layout-test` |
| Keychain service / group | separate test service / bundle ID |
| Data and caches | `OpalineLayoutTest/` under each shared storage root |
| Conflicts / Replaces / Provides | none |

An app under `/Applications` can share `/var/mobile/Library` with the original.
`LAYOUT_TEST_APP` therefore namespaces **all six explicit persistent/cache path
roots**, including downloads, local library, images, notification inbox and logs.
The original app's defaults are preserved when that flag is absent. Preferences
use the distinct bundle domain; there is no data migration. The test starts
with an empty library. Validate these assumptions on a device before relying
on coexistence. Back up the original library and keep its original .deb first.
Only remove the test package to roll back; do not remove original Opaline.

## Windows build route

Use WSL2 + Ubuntu + Darling + Apple's Xcode 12.5.1 toolchain/SDK files.
This does not install the Xcode IDE on Windows. The original build wrapper uses
Apple Swift 5.4.2 under Darling, with iPhoneOS14.5.sdk and deployment target
`armv7-apple-ios9.3`. `setup-env.sh` is Fedora/Qubes-specific; do not run its
package installation commands on Ubuntu. Obtain Apple files from the official
Apple Developer download site; no compiler/SDK binaries are committed here.

The current user's preferred host is Windows; Big Sur + Xcode 12.4 remains a
possible fallback, **not a verified build configuration for these sources**.
There is no need to install Codex on that machine. Current GitHub macOS runners
are not a substitute for the legacy compiler:
[Xcode 14 dropped armv7 and iOS 9/10 builds](https://developer.apple.com/documentation/xcode-release-notes/xcode-14-release-notes).

After the toolchain is installed in the layout expected by `darling-swiftc`,
use a Linux-native checkout under `/home` (not a path containing spaces):

```bash
git clone --branch fix/ios9-player-layout https://github.com/Heartspread98/Opaline.git
cd Opaline
bash scripts/legacy/build_layout_test.sh --check
bash scripts/legacy/build_layout_test.sh
```

The script explicitly sets both `LEGACY_IOS9` and `LAYOUT_TEST_APP`, builds,
bundles, signs, packages and verifies a local candidate under `build/layout-test`.
It does not install on a device or publish. `--check` is a prerequisite check,
not a compilation. `build.sh --dry-run` also is not a compilation.

## Verification status

| Check | Status |
|---|---|
| Source and screenshot inspection | complete |
| Python distribution integration tests | 7 passed locally |
| Python syntax, shell syntax, whitespace | passed locally |
| Swift typecheck / armv7 compile / link | pending toolchain setup |
| Modified real armv7 .deb | not produced yet |
| iPod / iPad install and playback | not tested |
| Live Pages source and Cydia refresh | not published / not tested |

Run `python3 scripts/legacy/test_layout_distribution.py -v`. Its Mach-O files
are **synthetic non-executable fixtures in temporary directories**, testing
archive structure, isolation, runtime dependencies, version stamps, corrupt
indexes and rejection of stubs/arm64/armv7s/newer OS binaries. They are never
distributed or offered as an installable app. Signature presence checks do not
verify cryptographic trust or successful launching. Modern SDK weak-linking,
runtime symbol availability and playback still require a real device.

Test builds log changed layout sizes under `[LayoutTest]`. Export using
Settings → Debug → Share Debug Log. The log path is the test's namespaced
cache root, not the original `Caches/Logs/opaline.log`.

## Device acceptance

Run separately on iPod touch 5 and iPad mini 1, iOS 9.3.5:

1. Confirm original Opaline launches and its subscriptions/downloads remain.
2. Install only the new ID; confirm both icons and both packages coexist.
3. Open a video directly in portrait, repeat with a second video and cold launch.
4. Expect a visible 16:9 area matching container width, not a zero-height box.
   Compare container/player/layer sizes in the log; collect constraint warnings.
5. Rotate portrait → landscape → portrait at least five times. On iPod check
   fullscreen separately; on iPad check the player + sidebar arrangement.
6. Test in-app mini-player / fullscreen reattachment and pinch zoom. The original
   fork says OS PiP is unavailable on armv7; do not assume the user's “PiP”
   describes system PiP rather than the app's mini-player.
7. Check long metadata, related-list scrolling, comments, next video, background
   audio and returning to foreground. Confirm the original library is unchanged.
8. Remove only the test package and verify original Opaline again.

Record device, OS, source commit, package version, install result, orientation
result, video ID and exported log. A successful compile does not close the bug.

## Pages / Cydia deployment

Flat APT hosting is technically suitable for GitHub Pages. `make_repo.py`
generates Packages, Packages.gz, Packages.bz2 and Release with index checksums.
`verify_layout_repo.py` checks package checksums, payload paths, identity,
Mach-O architecture and transitive bundled runtime presence. After a genuine
package exists, verify the complete tree before deploying it, add `.nojekyll`,
and keep only intended test .debs in `debs/`.

The intended project URL is `https://heartspread98.github.io/Opaline/`.
**It is not a working test source until Pages has actually deployed these files.**
Publish using a separate `gh-pages` branch or an explicit Pages workflow, never
the inherited force-push script with its default remote. Check HTTP 200 for all
three indexes, Release and each Filename URL, and compare downloaded bytes with
Packages SHA256. Finally refresh in the device's Cydia and perform the above
install checks. HTTP 200 on Windows does not prove iOS 9 TLS compatibility;
do not bypass certificate validation. This generates unsigned APT metadata;
Release.gpg/InRelease require a separately managed signing key if desired.

GitHub Free supports public Pages repositories; this fork is public. Pages
limits are 1 GB published size and a soft 100 GB/month bandwidth limit:
[GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
Preserve the GPLv3 license and corresponding modified source when distributing
Opaline binaries. No release or live Cydia source is implied by a passing CI
distribution check.
