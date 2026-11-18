import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "dscrypt.py")]
sys.path.insert(0, str(ROOT))
import dscrypt


class DscryptTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(CLI + list(args), text=True, capture_output=True, check=False)

    def test_help_and_version(self):
        self.assertEqual(self.run_cli("--help").returncode, 0)
        self.assertEqual(self.run_cli("--version").stdout.strip(), "dscrypt 0.3.0")

    def test_safe_extract_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "bad.tar.gz"
            outside = root / "escaped.txt"
            with tarfile.open(archive_path, "w:gz") as archive:
                data = b"unsafe"
                info = tarfile.TarInfo("../escaped.txt")
                info.size = len(data)
                import io
                archive.addfile(info, io.BytesIO(data))
            with self.assertRaisesRegex(dscrypt.ToolError, "路径穿越"):
                dscrypt.safe_extract(archive_path, root / "out")
            self.assertFalse(outside.exists())

    def test_directory_archive_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "note.txt").write_text("hello", encoding="utf-8")
            archive_path = root / "bundle.tar.gz"
            with archive_path.open("wb") as stream:
                dscrypt.make_tar_stream(source, stream)
            output = root / "out"
            dscrypt.safe_extract(archive_path, output)
            self.assertEqual((output / "source" / "note.txt").read_text(encoding="utf-8"), "hello")


if __name__ == "__main__":
    unittest.main()
