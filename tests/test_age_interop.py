"""Optional independent age CLI interoperability checks.

Set DSCRYPT_TEST_AGE to a verified official age executable to enable these tests.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pyrage

ROOT = Path(__file__).resolve().parents[1]
AGE = os.environ.get('DSCRYPT_TEST_AGE')


@unittest.skipUnless(AGE and Path(AGE).is_file(), 'set DSCRYPT_TEST_AGE to official age binary')
class OfficialAgeInteropTests(unittest.TestCase):
    def test_official_age_both_directions(self):
        with tempfile.TemporaryDirectory(prefix='dscrypt-age-interop-') as temp:
            root = Path(temp)
            identity = pyrage.x25519.Identity.generate()
            key = root / 'key'; key.write_text(str(identity) + '\n', encoding='ascii')
            recipient = str(identity.to_public())
            data = bytes(range(256)) * 2048
            source = root / 'source'; source.write_bytes(data)
            env = dict(os.environ, PATH=str(root))
            def run(args):
                p = subprocess.run([str(x) for x in args], env=env, capture_output=True, timeout=30)
                self.assertEqual(p.returncode, 0, (p.returncode, p.stderr.decode(errors='replace')))
            our_age = root / 'our.age'
            run([sys.executable, ROOT / 'dscrypt.py', 'encrypt', '-i', source, '-o', our_age, '-r', recipient])
            official_plain = root / 'official-plain'
            run([AGE, '-d', '-i', key, '-o', official_plain, our_age])
            self.assertEqual(official_plain.read_bytes(), data)
            official_age = root / 'official.age'
            run([AGE, '-r', recipient, '-o', official_age, source])
            our_plain = root / 'our-plain'
            run([sys.executable, ROOT / 'dscrypt.py', 'decrypt', '-i', official_age, '-o', our_plain, '--identity', key])
            self.assertEqual(our_plain.read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
