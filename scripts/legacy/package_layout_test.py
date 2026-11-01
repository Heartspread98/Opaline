#!/usr/bin/env python3
"""Package a signed armv7 test bundle without overwriting installed Opaline.

This validates structure, not signature trust, linking or device playback.
No placeholder/stub mode exists in this distribution command.
"""
import argparse
import gzip
import io
import plistlib
import re
import struct
import tarfile
from pathlib import Path

PACKAGE = "com.heartspread98.opaline.layouttest"
APP_DIR = "OpalineLayoutTest.app"


def macho_info(data):
    if len(data) < 28:
        raise ValueError("truncated Mach-O")
    magic, cpu, subtype, kind, count, total, _ = struct.unpack_from("<7I", data)
    if magic != 0xfeedface or cpu != 12 or subtype & 0xffffff != 9:
        raise ValueError("expected thin 32-bit ARMv7 Mach-O (not arm64/armv7s/stub)")
    end = 28 + total
    if end > len(data):
        raise ValueError("truncated load commands")
    offset, minimum, signed, deps, rpaths = 28, None, False, [], []
    for _ in range(count):
        if offset + 8 > end:
            raise ValueError("invalid load command count")
        cmd, size = struct.unpack_from("<2I", data, offset)
        if size < 8 or offset + size > end:
            raise ValueError("invalid load command size")
        if cmd == 0x25 and size >= 16:  # LC_VERSION_MIN_IPHONEOS
            minimum = struct.unpack_from("<I", data, offset + 8)[0]
        if cmd == 0x1d and size >= 16:  # LC_CODE_SIGNATURE, structural only
            start, length = struct.unpack_from("<2I", data, offset + 8)
            signed = length > 0 and start >= end and start + length <= len(data)
        if cmd in (0xc, 0x80000018, 0x8000001f, 0x8000001c):
            relative = struct.unpack_from("<I", data, offset + 8)[0]
            if not 12 <= relative < size:
                raise ValueError("invalid dependency string")
            value = data[offset + relative:offset + size].split(b"\0", 1)[0].decode()
            (rpaths if cmd == 0x8000001c else deps).append(value)
        offset += size
    if offset != end or minimum is None or minimum > 0x00090300 or not signed:
        raise ValueError("requires iOS <=9.3 load command and embedded signature")
    return {"kind": kind, "minimum": minimum, "deps": deps, "rpaths": rpaths}


def validate_app(app):
    with (app / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    if info.get("CFBundleIdentifier") != PACKAGE:
        raise ValueError("refusing original/shared bundle identifier")
    if info.get("CFBundleExecutable") != "Opaline":
        raise ValueError("unexpected executable")
    if info.get("MinimumOSVersion") != "9.3":
        raise ValueError("unexpected minimum iOS version")
    if info.get("UIRequiredDeviceCapabilities") != ["armv7"]:
        raise ValueError("armv7 capability required")
    schemes = [scheme for item in info.get("CFBundleURLTypes", [])
               for scheme in item.get("CFBundleURLSchemes", [])]
    if schemes != ["opaline-layout-test"]:
        raise ValueError("test app must use an isolated URL scheme")
    # Refuse symlinks rather than package paths that could escape the bundle.
    if any(p.is_symlink() for p in app.rglob("*")):
        raise ValueError("symlinks are not supported in the test bundle")
    pending, checked = [app / "Opaline"], set()
    while pending:
        path = pending.pop()
        if path in checked:
            continue
        checked.add(path)
        result = macho_info(path.read_bytes())
        if result["kind"] != (2 if path == app / "Opaline" else 6):
            raise ValueError("unexpected executable/dylib file type")
        if path == app / "Opaline" and "@executable_path/Frameworks" not in result["rpaths"]:
            raise ValueError("missing bundled Swift runtime search path")
        for dep in result["deps"]:
            if dep.startswith("@rpath/"):
                name = dep[len("@rpath/"):]
                if "/" in name or name in ("", ".", ".."):
                    raise ValueError("unsupported runtime dependency path")
                runtime = app / "Frameworks" / name
                if not runtime.is_file():
                    raise ValueError("missing bundled runtime: " + name)
                pending.append(runtime)
            elif not dep.startswith(("/System/Library/", "/usr/lib/")):
                raise ValueError("unsupported dependency: " + dep)
    # Inspect even unreferenced dylibs; an arm64 runtime must never slip in.
    for path in (app / "Frameworks").glob("*.dylib"):
        macho_info(path.read_bytes())
    return info


def tar_gz(entries, directory_entries=False):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        added_directories = set()
        for name, data, mode in entries:
            if directory_entries:
                parts = name.split("/")
                for depth in range(1, len(parts)):
                    directory = "/".join(parts[:depth]) + "/"
                    if directory in added_directories:
                        continue
                    item = tarfile.TarInfo(directory)
                    item.type = tarfile.DIRTYPE
                    item.mode, item.uid, item.gid, item.mtime = 0o755, 0, 0, 0
                    archive.addfile(item)
                    added_directories.add(directory)
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.uid, item.gid, item.mtime = len(data), mode, 0, 0, 0
            archive.addfile(item, io.BytesIO(data))
    return gzip.compress(buffer.getvalue(), mtime=0)


def ar(entries):
    out = bytearray(b"!<arch>\n")
    for name, data in entries:
        header = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
        out.extend(header.encode("ascii"))
        out.extend(data)
        if len(data) & 1:
            out.extend(b"\n")
    return bytes(out)


def package(app, version, output):
    if not re.fullmatch(r"[0-9][A-Za-z0-9.+~]*", version):
        raise ValueError("invalid Debian version")
    info = validate_app(app)
    if info.get("OpalineLayoutPackageVersion") != version:
        raise ValueError("bundle build stamp does not match package version")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,2}", info.get("CFBundleVersion", "")):
        raise ValueError("CFBundleVersion must be numeric, not a Debian prerelease string")
    files = []
    for path in sorted(app.rglob("*")):
        if path.is_file():
            rel = path.relative_to(app).as_posix()
            mode = 0o755 if rel == "Opaline" or path.suffix == ".dylib" else 0o644
            files.append((f"Applications/{APP_DIR}/{rel}", path.read_bytes(), mode))
    size = (sum(len(data) for _, data, _ in files) + 1023) // 1024
    control = (
        f"Package: {PACKAGE}\nName: Opaline Layout Test (iOS 9)\nVersion: {version}\n"
        "Architecture: iphoneos-arm\nSection: Multimedia\nPriority: optional\n"
        "Depends: firmware (>= 9.3), firmware (<< 10.0)\n"
        f"Installed-Size: {size}\nMaintainer: Heartspread98\n"
        "Author: Opaline contributors\n"
        "Homepage: https://github.com/Heartspread98/Opaline\n"
        "Description: Experimental iOS 9 player layout fix\n"
        " Separate app and data paths; device playback verification required.\n"
    ).encode()
    refresh = b"#!/bin/sh\nuicache 2>/dev/null || true\nexit 0\n"
    raw = ar([("debian-binary", b"2.0\n"),
              ("control.tar.gz", tar_gz([("control", control, 0o644),
                                        ("postinst", refresh, 0o755),
                                        ("postrm", refresh, 0o755)])),
              ("data.tar.gz", tar_gz(files, directory_entries=True))])
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{PACKAGE}_{version}_iphoneos-arm.deb"
    destination.write_bytes(raw)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(package(args.app, args.version, args.output))
    except (ValueError, OSError, struct.error) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
