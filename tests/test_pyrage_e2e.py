"""End-to-end regression checks for the pyrage CLI (no external age required)."""
import io
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import pyrage

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / 'dscrypt.py')]
MARKER = b'DSCRYPT-TAR-V1\n'


class PyrageEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='dscrypt-tests-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.key = self.root / 'private.key'
        self.identity = pyrage.x25519.Identity.generate()
        self.key.write_text(str(self.identity) + '\n', encoding='ascii')
        self.recipient = str(self.identity.to_public())

    def cli(self, *args, success=True):
        env = dict(os.environ, PATH=str(self.root))
        p = subprocess.run(CLI + [str(a) for a in args], env=env, capture_output=True, text=True, timeout=30)
        if success:
            self.assertEqual(p.returncode, 0, (args, p.stdout, p.stderr))
        else:
            self.assertNotEqual(p.returncode, 0, (args, p.stdout, p.stderr))
        self.assertNotIn(str(self.identity), p.stdout + p.stderr)
        return p

    def encrypt(self, source, target, *opts, success=True):
        return self.cli('encrypt', '-i', source, '-o', target, '-r', self.recipient, *opts, success=success)

    def decrypt(self, source, target, *opts, success=True, identity=None):
        return self.cli('decrypt', '-i', source, '-o', target, '--identity', identity or self.key, *opts, success=success)

    def tar_bytes(self, name='folder/note.txt', payload=b'hello', kind=tarfile.REGTYPE, link=''):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as tf:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.linkname = link
            item.size = len(payload) if kind == tarfile.REGTYPE else 0
            tf.addfile(item, io.BytesIO(payload) if item.size else None)
        return out.getvalue()

    def test_keygen_and_pubkey_without_age(self):
        key = self.root / '生成 key.txt'
        self.cli('keygen', '-o', key)
        self.assertTrue(key.is_file())
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
        p = self.cli('pubkey', '--identity', key)
        self.assertTrue(p.stdout.strip().startswith('age1'))
        self.assertNotIn('AGE-SECRET-KEY-', p.stdout + p.stderr)

    def test_output_suffix_is_opt_in_and_decrypt_ignores_extension(self):
        src = self.root / '原始 文档.bin'
        src.write_bytes(b'payload bytes')
        plain_named = self.root / 'output.dat'
        self.encrypt(src, plain_named)
        self.assertTrue(plain_named.is_file())
        self.assertTrue(plain_named.read_bytes().startswith(b'age-encryption.org/v1\n'))
        restored = self.root / 'restored.dat'
        self.decrypt(plain_named, restored)
        self.assertEqual(restored.read_bytes(), b'payload bytes')
        self.cli('inspect', '-i', plain_named)
        self.encrypt(src, self.root / 'named.dat', '--age-suffix')
        self.assertTrue((self.root / 'named.dat.age').is_file())
        already = self.root / 'already.age'
        self.encrypt(src, already, '--age-suffix')
        self.assertTrue(already.is_file())
        self.assertFalse((self.root / 'already.age.age').exists())
        upper = self.root / 'upper.AGE'
        self.encrypt(src, upper, '--age-suffix')
        self.assertTrue(upper.is_file())
        self.assertFalse((self.root / 'upper.AGE.age').exists())

    def test_suffix_applied_before_overwrite_and_same_file_checks(self):
        src = self.root / 'source'; src.write_bytes(b'secret')
        base = self.root / 'cipher'; final = self.root / 'cipher.age'
        final.write_bytes(b'existing')
        self.encrypt(src, base, '--age-suffix', success=False)
        self.assertEqual(final.read_bytes(), b'existing')
        self.assertFalse(base.exists())
        self.encrypt(src, base, '--age-suffix', '--force')
        restored = self.root / 'restore'; self.decrypt(final, restored)
        self.assertEqual(restored.read_bytes(), b'secret')
        collision = self.root / 'collision.age'; collision.write_bytes(b'keep')
        self.encrypt(collision, self.root / 'collision', '--age-suffix', '--force', success=False)
        self.assertEqual(collision.read_bytes(), b'keep')
        folder = self.root / 'folder'; folder.mkdir()
        self.encrypt(folder, folder / 'out', '--age-suffix', success=False)
        self.assertFalse((folder / 'out.age').exists())

    def test_binary_empty_marker_and_valid_tar_are_always_files(self):
        samples = [b'', bytes(range(256)), MARKER + b'not gzip', MARKER + self.tar_bytes(), self.tar_bytes()]
        for i, payload in enumerate(samples):
            with self.subTest(case=i):
                src = self.root / f'中文 输入 {i}.bin'
                cipher = self.root / f'密文 {i}.age'
                restored = self.root / f'还原 {i}.bin'
                src.write_bytes(payload)
                self.encrypt(src, cipher)
                self.assertTrue(cipher.read_bytes().startswith(b'age-encryption.org/v1\n'))
                self.assertEqual(pyrage.decrypt(cipher.read_bytes(), [self.identity]), payload)
                self.decrypt(cipher, restored)
                self.assertTrue(restored.is_file())
                self.assertEqual(restored.read_bytes(), payload)

    def test_directory_and_default_raw_tar(self):
        folder = self.root / '目录 空格'
        (folder / '多层' / '空').mkdir(parents=True)
        (folder / '多层' / '文件.txt').write_text('中文\n', encoding='utf-8')
        enc = self.root / 'folder.age'
        self.encrypt(folder, enc)
        raw = self.root / 'raw.tar.gz'
        self.decrypt(enc, raw)
        with tarfile.open(raw, 'r:gz') as tf:
            self.assertTrue(any(x.endswith('文件.txt') for x in tf.getnames()))
        out = self.root / 'unpacked'
        before = set(self.root.iterdir())
        self.decrypt(enc, out, '--directory')
        self.assertEqual(set(self.root.iterdir()) - before, {out}, 'successful extraction left temporary files')
        matches = list(out.rglob('文件.txt'))
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].read_text(encoding='utf-8'), '中文\n')
        self.assertEqual(len(list(out.rglob('空'))), 1)

    def test_legacy_directory_is_explicit(self):
        data = MARKER + self.tar_bytes()
        enc = self.root / 'old.age'
        enc.write_bytes(pyrage.encrypt(data, [self.identity.to_public()]))
        raw = self.root / 'raw'
        self.decrypt(enc, raw)
        self.assertEqual(raw.read_bytes(), data)
        out = self.root / 'legacy'
        self.decrypt(enc, out, '--legacy-directory')
        self.assertEqual((out / 'folder' / 'note.txt').read_bytes(), b'hello')

    def test_malicious_archive_rejected_and_no_target(self):
        cases = [('../escape', tarfile.REGTYPE, ''), ('/absolute', tarfile.REGTYPE, ''), ('C:/drive', tarfile.REGTYPE, ''), ('dir\\\\file', tarfile.REGTYPE, ''), ('dir/CON.txt', tarfile.REGTYPE, ''), ('link', tarfile.SYMTYPE, '../escape'), ('hard', tarfile.LNKTYPE, '../escape'), ('fifo', tarfile.FIFOTYPE, '')]
        for i, (name, kind, link) in enumerate(cases):
            with self.subTest(name=name):
                enc = self.root / f'bad-{i}.age'
                enc.write_bytes(pyrage.encrypt(self.tar_bytes(name=name, kind=kind, link=link), [self.identity.to_public()]))
                out = self.root / f'bad-{i}'
                self.decrypt(enc, out, '--directory', success=False)
                self.assertFalse(out.exists())
        self.assertFalse((self.root / 'escape').exists())

    def test_wrong_key_and_corrupt_preserve_forced_target_and_cleanup(self):
        source = self.root / 'source'
        source.write_bytes(os.urandom(100000))
        enc = self.root / 'source.age'
        self.encrypt(source, enc)
        target = self.root / 'existing'
        target.write_bytes(b'unchanged')
        wrong = self.root / 'wrong.key'
        wrong.write_text(str(pyrage.x25519.Identity.generate()) + '\n', encoding='ascii')
        before = set(self.root.iterdir())
        self.decrypt(enc, target, '--force', identity=wrong, success=False)
        self.assertEqual(target.read_bytes(), b'unchanged')
        self.assertEqual(set(self.root.iterdir()), before)
        original = enc.read_bytes()
        for i, damaged in enumerate((original[:-1], original[:-32], original[:-1] + bytes([original[-1] ^ 1]))):
            with self.subTest(case=i):
                enc.write_bytes(damaged)
                self.decrypt(enc, target, '--force', success=False)
                self.assertEqual(target.read_bytes(), b'unchanged')
                self.assertEqual(set(self.root.iterdir()), before)

    def test_overwrite_and_force(self):
        src = self.root / 'source'; src.write_bytes(b'data')
        enc = self.root / 'file.age'; enc.write_bytes(b'old ciphertext')
        self.encrypt(src, enc, success=False)
        self.assertEqual(enc.read_bytes(), b'old ciphertext')
        self.encrypt(src, enc, '--force')
        out = self.root / 'out'; out.write_bytes(b'old plaintext')
        self.decrypt(enc, out, success=False)
        self.assertEqual(out.read_bytes(), b'old plaintext')
        self.decrypt(enc, out, '--force')
        self.assertEqual(out.read_bytes(), b'data')

    def test_reject_same_path_hardlinks_and_directory_output_inside_input(self):
        src = self.root / 'source'; src.write_bytes(b'untouched')
        self.encrypt(src, src, '--force', success=False)
        self.assertEqual(src.read_bytes(), b'untouched')
        hard = self.root / 'hard'; os.link(src, hard)
        self.encrypt(src, hard, '--force', success=False)
        self.assertEqual(src.read_bytes(), b'untouched')
        folder = self.root / 'folder'; folder.mkdir(); (folder / 'file').write_bytes(b'data')
        self.encrypt(folder, folder / 'out.age', success=False)
        self.assertFalse((folder / 'out.age').exists())

    @unittest.skipUnless(hasattr(os, 'symlink'), 'requires symlinks')
    def test_source_symlink_and_directory_symlink_rejected(self):
        src = self.root / 'source'; src.write_bytes(b'data')
        link = self.root / 'link'; link.symlink_to(src)
        self.encrypt(link, self.root / 'link.age', success=False)
        folder = self.root / 'folder'; folder.mkdir(); (folder / 'link').symlink_to(src)
        self.encrypt(folder, self.root / 'folder.age', success=False)

    def test_windows_unsafe_archive_and_input_names(self):
        for i, name in enumerate(('folder/file:name', 'folder/trailing.', 'folder/trailing ', 'folder/bad?name', 'folder/bad*name')):
            with self.subTest(name=name):
                enc = self.root / f'winbad-{i}.age'
                enc.write_bytes(pyrage.encrypt(self.tar_bytes(name=name), [self.identity.to_public()]))
                target = self.root / f'winbad-{i}'
                self.decrypt(enc, target, '--directory', success=False)
                self.assertFalse(target.exists())
                folder = self.root / f'source-{i}'; folder.mkdir()
                (folder / name.split('/')[-1]).write_bytes(b'data')
                self.encrypt(folder, self.root / f'source-{i}.age', success=False)

    def test_archive_case_collision_rejected(self):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:gz') as tf:
            for name in ('folder/Readme', 'folder/README'):
                entry = tarfile.TarInfo(name); entry.size = 1
                tf.addfile(entry, io.BytesIO(b'x'))
        enc = self.root / 'collision.age'
        enc.write_bytes(pyrage.encrypt(output.getvalue(), [self.identity.to_public()]))
        target = self.root / 'collision'
        self.decrypt(enc, target, '--directory', success=False)
        self.assertFalse(target.exists())

    def test_non_utf8_identity_has_clean_error(self):
        broken = self.root / 'invalid.key'; broken.write_bytes(b'\xff\xfe')
        result = self.cli('pubkey', '--identity', broken, success=False)
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn('UnicodeDecodeError', result.stderr)

    def test_decrypt_cannot_overwrite_identity(self):
        enc = self.root / 'cipher.age'
        enc.write_bytes(pyrage.encrypt(b'data', [self.identity.to_public()]))
        before = self.key.read_bytes()
        self.decrypt(enc, self.key, '--force', success=False)
        self.assertEqual(self.key.read_bytes(), before)
        hard = self.root / 'identity-hard'; os.link(self.key, hard)
        self.decrypt(enc, hard, '--force', success=False)
        self.assertEqual(self.key.read_bytes(), before)

    def test_existing_directory_is_not_destroyed_even_with_force(self):
        enc = self.root / 'archive.age'
        enc.write_bytes(pyrage.encrypt(self.tar_bytes(), [self.identity.to_public()]))
        out = self.root / 'existing'; out.mkdir()
        sentinel = out / 'keep'; sentinel.write_bytes(b'important')
        self.decrypt(enc, out, '--directory', '--force', success=False)
        self.assertEqual(sentinel.read_bytes(), b'important')

    def test_invalid_recipient_force_does_not_clobber_output(self):
        src = self.root / 'source'; src.write_bytes(b'data')
        output = self.root / 'existing'; output.write_bytes(b'important')
        before = set(self.root.iterdir())
        self.cli('encrypt', '-i', src, '-o', output, '-r', 'not-a-recipient', '--force', success=False)
        self.assertEqual(output.read_bytes(), b'important')
        self.assertEqual(set(self.root.iterdir()), before)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'requires POSIX FIFO')
    def test_fifo_input_is_rejected_without_blocking(self):
        fifo = self.root / 'pipe'; os.mkfifo(fifo)
        self.encrypt(fifo, self.root / 'pipe.age', success=False)

    def test_armored_ciphertext(self):
        src = self.root / 'source'; src.write_bytes(b'armored')
        enc = self.root / 'armored.age'; self.encrypt(src, enc, '--armor')
        self.assertTrue(enc.read_bytes().startswith(b'-----BEGIN AGE ENCRYPTED FILE-----'))
        out = self.root / 'out'; self.decrypt(enc, out)
        self.assertEqual(out.read_bytes(), b'armored')


if __name__ == '__main__':
    unittest.main()
