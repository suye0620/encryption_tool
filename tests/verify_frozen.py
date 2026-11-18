"""Verify a frozen dscrypt executable using existing E2E cases and a 128 MiB round trip."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    binary = Path(sys.argv[1]).resolve()
    expected = digest(ROOT / 'dscrypt.py')
    for name in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'LD_LIBRARY_PATH'):
        os.environ.pop(name, None)
    with tempfile.TemporaryDirectory(prefix='dscrypt-frozen-') as temp:
        work = Path(temp)
        exe = work / 'dscrypt'
        shutil.copy2(binary, exe)
        os.environ['PATH'] = str(work)
        os.chdir(work)
        env = dict(os.environ)
        result = subprocess.run([str(exe), '--version'], env=env, capture_output=True, text=True, check=True)
        print(result.stdout.strip(), flush=True)
        spec = importlib.util.spec_from_file_location('frozen_e2e', ROOT / 'tests/test_pyrage_e2e.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.CLI = [str(exe)]
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful() or result.skipped:
            return 1
        def run(*args):
            return subprocess.run([str(exe), *map(str, args)], env=env, capture_output=True, text=True, check=True, timeout=180)
        key = work / 'private.key'
        run('keygen', '-o', key)
        public = run('pubkey', '--identity', key).stdout.strip()
        source = work / 'source.bin'
        with source.open('wb') as stream:
            for _ in range(128):
                stream.write(os.urandom(1024 * 1024))
        encrypted, restored = work / 'cipher.age', work / 'restored.bin'
        run('encrypt', '-i', source, '-o', encrypted, '-r', public)
        run('decrypt', '-i', encrypted, '-o', restored, '--identity', key)
        assert digest(source) == digest(restored), '128 MiB SHA-256 mismatch'
        print('128 MiB frozen executable round trip: SHA-256 matched', flush=True)
    assert digest(ROOT / 'dscrypt.py') == expected, 'Source changed during verification'
    print('source_sha256=' + expected)
    print('binary_sha256=' + digest(binary))
    print('binary_bytes=' + str(binary.stat().st_size))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
