"""Deterministic no-clobber regression tests for concurrent target creation."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pyrage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dscrypt


class PublicationRaceTests(unittest.TestCase):
    def test_competing_empty_directory_is_not_overwritten(self):
        import tarfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            identity = pyrage.x25519.Identity.generate()
            key = root / 'key'; key.write_text(str(identity) + '\n', encoding='ascii')
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode='w:gz') as tf:
                entry = tarfile.TarInfo('file'); entry.size = 1
                tf.addfile(entry, io.BytesIO(b'x'))
            cipher = root / 'cipher'; cipher.write_bytes(pyrage.encrypt(archive.getvalue(), [identity.to_public()]))
            target = root / 'target'
            original = Path.mkdir
            inode = []
            def competing_directory(path, *args, **kwargs):
                if path == target:
                    original(path, *args, **kwargs)
                    inode.append(path.stat().st_ino)
                return original(path, *args, **kwargs)
            args = SimpleNamespace(input=str(cipher), output=str(target), identity=str(key), directory=True, legacy_directory=False, force=False)
            with patch.object(Path, 'mkdir', competing_directory), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises((dscrypt.ToolError, OSError)):
                    dscrypt.decrypt(args)
            self.assertTrue(inode)
            self.assertEqual(target.stat().st_ino, inode[0])
            self.assertEqual(list(target.iterdir()), [])

    def test_competing_target_is_not_overwritten(self):
        for operation in ('keygen', 'encrypt'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                target = root / 'target'
                source = root / 'source'; source.write_bytes(b'file data')
                recipient = str(pyrage.x25519.Identity.generate().to_public())
                original = dscrypt.atomic_target
                def competing_create(path, force, **kwargs):
                    temporary, final = original(path, force, **kwargs)
                    final.write_bytes(b'created by another process')
                    return temporary, final
                args = SimpleNamespace(output=str(target), input=str(source), recipient=recipient, force=False, armor=False, age_suffix=False)
                with patch.object(dscrypt, 'atomic_target', side_effect=competing_create), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises((dscrypt.ToolError, FileExistsError)):
                        getattr(dscrypt, operation)(args)
                self.assertEqual(target.read_bytes(), b'created by another process')
                self.assertEqual({p.name for p in root.iterdir()}, {'source', 'target'})


if __name__ == '__main__':
    unittest.main()
