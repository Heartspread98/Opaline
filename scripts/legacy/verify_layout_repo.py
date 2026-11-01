#!/usr/bin/env python3
"""Verify a local flat Cydia repo; does not prove HTTPS/device compatibility."""
import argparse
import bz2
import gzip
import hashlib
import io
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from make_repo import ar_members, control_of
from package_layout_test import APP_DIR, PACKAGE, validate_app


def verify(root):
    packages = (root / "Packages").read_bytes()
    if not packages.strip():
        raise ValueError("empty Packages")
    for name, decompress in (("Packages.gz", gzip.decompress), ("Packages.bz2", bz2.decompress)):
        if decompress((root / name).read_bytes()) != packages:
            raise ValueError("compressed index mismatch: " + name)
    release = (root / "Release").read_text(encoding="utf-8")
    if "Architectures: iphoneos-arm\n" not in release:
        raise ValueError("wrong repository architecture")
    expected = {"Packages", "Packages.gz", "Packages.bz2"}
    hashes, section = {}, None
    for line in release.splitlines():
        if line and not line.startswith(" "):
            section = line.rstrip(":")
        elif section == "SHA256":
            checksum, length, name = line.split()
            hashes[name] = (checksum, int(length))
    if set(hashes) != expected:
        raise ValueError("Release must hash all three indexes")
    for name in expected:
        data = (root / name).read_bytes()
        if hashes[name] != (hashlib.sha256(data).hexdigest(), len(data)):
            raise ValueError("Release checksum mismatch: " + name)
    count = 0
    for stanza in packages.decode().strip().split("\n\n"):
        fields, key = {}, None
        for line in stanza.splitlines():
            if line.startswith((" ", "\t")) and key:
                fields[key] += "\n" + line
            else:
                key, value = line.split(": ", 1)
                fields[key] = value
        if fields.get("Package") != PACKAGE or fields.get("Architecture") != "iphoneos-arm":
            raise ValueError("unexpected package identity/architecture")
        if any(key in fields for key in ("Conflicts", "Replaces", "Provides")):
            raise ValueError("test must not replace original Opaline")
        rel = PurePosixPath(fields["Filename"])
        if rel.is_absolute() or ".." in rel.parts or rel.parts[0] != "debs":
            raise ValueError("unsafe Filename")
        deb = root.joinpath(*rel.parts)
        raw = deb.read_bytes()
        if int(fields["Size"]) != len(raw) or fields["SHA256"] != hashlib.sha256(raw).hexdigest():
            raise ValueError("package size/checksum mismatch")
        control = control_of(deb)
        if any(fields.get(key) != value for key, value in control.items()):
            raise ValueError("Packages differs from embedded control")
        members = dict(ar_members(raw))
        if members.get("debian-binary") != b"2.0\n":
            raise ValueError("unsupported Debian archive")
        # Extract only files under the isolated app, after checking every path.
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            with tarfile.open(fileobj=io.BytesIO(members["data.tar.gz"]), mode="r:gz") as archive:
                seen_directories = set()
                for member in archive.getmembers():
                    path = PurePosixPath(member.name)
                    if path.is_absolute() or not path.parts or ".." in path.parts:
                        raise ValueError("payload would touch another app")
                    if member.uid != 0 or member.gid != 0:
                        raise ValueError("payload must be root-owned")
                    dest = stage.joinpath(*path.parts)
                    if member.isdir():
                        if (path.parts != ("Applications",)
                                and path.parts[:2] != ("Applications", APP_DIR)):
                            raise ValueError("payload directory would touch another app")
                        if member.size != 0 or member.mode & 0o777 != 0o755:
                            raise ValueError("invalid payload directory permissions")
                        if path in seen_directories:
                            raise ValueError("duplicate payload directory")
                        if len(path.parts) > 1 and PurePosixPath(*path.parts[:-1]) not in seen_directories:
                            raise ValueError("missing parent directory entry")
                        dest.mkdir()
                        seen_directories.add(path)
                        continue
                    if path.parts[:2] != ("Applications", APP_DIR) or not member.isfile():
                        raise ValueError("unexpected payload member type/path")
                    if any(PurePosixPath(*path.parts[:depth]) not in seen_directories
                           for depth in range(1, len(path.parts))):
                        raise ValueError("missing directory entry before file")
                    dest.write_bytes(archive.extractfile(member).read())
                    if dest.name == "Opaline" and member.mode & 0o111 != 0o111:
                        raise ValueError("executable permissions missing")
            app = stage / "Applications" / APP_DIR
            info = validate_app(app)
            if info["OpalineLayoutPackageVersion"] != fields["Version"]:
                raise ValueError("bundle/package version mismatch")
        count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(f"Verified {verify(args.root)} isolated test package(s), indexes and SHA256 hashes.")
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, str(error) + "\n")
