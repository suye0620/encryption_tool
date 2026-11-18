"""Manual 128 MiB round-trip benchmark: .venv-cp311/bin/python tests/benchmark_stream.py.

Reports GNU time's maximum resident set size for each CLI process. Temporary
input, key, output and ciphertext live in a private temporary directory.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pyrage

ROOT = Path(__file__).resolve().parents[1]
TIME = '/usr/bin/time'
SIZE = 128 * 1024 * 1024


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.digest()


def main():
    if not Path(TIME).is_file():
        raise RuntimeError('GNU /usr/bin/time is required')
    with tempfile.TemporaryDirectory(prefix='dscrypt-benchmark-') as temp:
        root = Path(temp)
        if shutil.disk_usage(root).free < 450 * 1024 * 1024:
            raise RuntimeError('need at least 450 MiB of free temporary storage')
        source = root / 'source'
        block = os.urandom(1024 * 1024)
        with source.open('wb') as stream:
            for _ in range(128):
                stream.write(block)
        assert source.stat().st_size == SIZE
        ident = pyrage.x25519.Identity.generate()
        key = root / 'identity'; key.write_text(str(ident) + '\n', encoding='ascii'); key.chmod(0o600)
        ciphertext = root / 'encrypted.age'
        restored = root / 'restored'
        cli = [sys.executable, str(ROOT / 'dscrypt.py')]
        env = dict(os.environ, PATH=str(root))
        for label, args in (
            ('encrypt', ['encrypt', '-i', source, '-o', ciphertext, '-r', str(ident.to_public())]),
            ('decrypt', ['decrypt', '-i', ciphertext, '-o', restored, '--identity', key]),
        ):
            measurement = root / f'{label}.time'
            p = subprocess.run([TIME, '-f', '%M %e', '-o', str(measurement)] + cli + [str(a) for a in args], env=env, capture_output=True, text=True, timeout=600)
            if p.returncode:
                raise RuntimeError(f'{label} failed: {p.stderr}')
            kib, seconds = measurement.read_text().split()
            print(f'{label}: peak_rss_kib={kib} elapsed_seconds={seconds}')
        if digest(source) != digest(restored):
            raise AssertionError('SHA256 mismatch')
        print(f'round trip SHA-256 matched, plaintext_bytes={SIZE}')


if __name__ == '__main__':
    main()
