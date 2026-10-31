"""Distribution integration tests with SYNTHETIC Mach-O fixtures, never real apps."""
import importlib.util
import io
import plistlib
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from make_repo import ar_members
from package_layout_test import PACKAGE, package, validate_app
from verify_layout_repo import verify

HERE = Path(__file__).resolve().parent
VERSION = "0.1.0~layout.20261101"


def fixture_binary(kind=2, cpu=12, subtype=9, minimum=0x90300, dependency=None):
    """Header + load commands only. These bytes cannot execute on any device."""
    commands = [struct.pack("<4I", 0x25, 16, minimum, 0)]
    for cmd, text in [(0x8000001c, "@executable_path/Frameworks")]:
        payload = text.encode() + b"\0"
        payload += b"\0" * (-len(payload) % 4)
        commands.append(struct.pack("<3I", cmd, 12 + len(payload), 12) + payload)
    if dependency:
        payload = dependency.encode() + b"\0"
        payload += b"\0" * (-len(payload) % 4)
        commands.append(struct.pack("<6I", 0xc, 24 + len(payload), 24, 0, 0, 0) + payload)
    size = sum(map(len, commands)) + 16
    commands.append(struct.pack("<4I", 0x1d, 16, 28 + size, 4))
    return struct.pack("<7I", 0xfeedface, cpu, subtype, kind, len(commands), size, 0) + b"".join(commands) + b"FAKE"


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "staging/Opaline.app"
        self.app.mkdir(parents=True)
        self.info = {"CFBundleIdentifier": PACKAGE, "CFBundleExecutable": "Opaline",
                     "CFBundleVersion": VERSION, "MinimumOSVersion": "9.3",
                     "UIRequiredDeviceCapabilities": ["armv7"],
                     "CFBundleURLTypes": [{"CFBundleURLSchemes": ["opaline-layout-test"]}]}
        self.save_info()
        (self.app / "Opaline").write_bytes(fixture_binary())

    def save_info(self):
        (self.app / "Info.plist").write_bytes(plistlib.dumps(self.info))

    def stage_repo(self):
        repo = self.root / "repo"
        deb = package(self.app, VERSION, repo / "debs")
        subprocess.run([sys.executable, str(HERE / "make_repo.py"), "--root", str(repo)],
                       check=True, capture_output=True)
        return repo, deb

    def test_archive_indexes_and_isolated_payload(self):
        repo, deb = self.stage_repo()
        self.assertEqual(verify(repo), 1)
        members = dict(ar_members(deb.read_bytes()))
        with tarfile.open(fileobj=io.BytesIO(members["control.tar.gz"]), mode="r:gz") as archive:
            control = archive.extractfile("control").read().decode()
            self.assertNotIn("Conflicts:", control)
            self.assertNotIn("Replaces:", control)
            self.assertEqual(archive.getmember("postinst").mode, 0o755)

    def test_rejects_original_bundle_and_scheme(self):
        for key, value in [("CFBundleIdentifier", "com.verback.YTLite"),
                           ("CFBundleURLTypes", [{"CFBundleURLSchemes": ["opaline"]}])]:
            old = self.info[key]
            self.info[key] = value
            self.save_info()
            with self.assertRaises(ValueError):
                validate_app(self.app)
            self.info[key] = old

    def test_rejects_stub_arm64_armv7s_new_os_and_unsigned(self):
        for data in [b"stub\n", fixture_binary(cpu=0x100000c), fixture_binary(subtype=11),
                     fixture_binary(minimum=0xa0000), fixture_binary()[:-4]]:
            (self.app / "Opaline").write_bytes(data)
            with self.assertRaises(ValueError):
                validate_app(self.app)

    def test_requires_transitive_armv7_runtime(self):
        (self.app / "Opaline").write_bytes(fixture_binary(dependency="@rpath/libswiftCore.dylib"))
        with self.assertRaises((ValueError, OSError)):
            validate_app(self.app)
        runtime = self.app / "Frameworks"
        runtime.mkdir()
        (runtime / "libswiftCore.dylib").write_bytes(fixture_binary(kind=6))
        validate_app(self.app)
        (runtime / "libswiftCore.dylib").write_bytes(fixture_binary(kind=6, cpu=0x100000c))
        with self.assertRaises(ValueError):
            validate_app(self.app)

    def test_detects_deb_and_release_tampering(self):
        repo, deb = self.stage_repo()
        deb.write_bytes(deb.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "size/checksum"):
            verify(repo)
        repo, _ = self.stage_repo()
        (repo / "Packages.gz").write_bytes(b"changed")
        with self.assertRaises((ValueError, OSError)):
            verify(repo)

    def test_version_must_match_bundle(self):
        with self.assertRaises(ValueError):
            package(self.app, "0.1.1", self.root / "out")

    def test_bundle_generator_isolates_identity(self):
        spec = importlib.util.spec_from_file_location("make_bundle", HERE / "make_bundle.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.BUNDLE_ID = PACKAGE
        module.build_plist(self.app, "0.1.0")
        info = plistlib.loads((self.app / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleIdentifier"], PACKAGE)
        self.assertEqual(info["CFBundleURLTypes"][0]["CFBundleURLSchemes"], ["opaline-layout-test"])


if __name__ == "__main__":
    unittest.main()
