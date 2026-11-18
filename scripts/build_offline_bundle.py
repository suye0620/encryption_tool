#!/usr/bin/env python3
"""Package only explicit public project files; never include keys or venvs."""
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "dist" / "dscrypt-0.3.0-offline.zip"

def main():
    paths = [ROOT / name for name in (
        "dscrypt.py", "README.md", "OFFLINE.md", "pyproject.toml",
        "requirements.txt", "install_offline.py", "scripts/prepare_offline.py",
        "tests/benchmark_stream.py",
        "scripts/build_offline_bundle.py", "wheelhouse/SHA256SUMS", "wheelhouse/provenance.json",
    )]
    paths.extend(sorted((ROOT / "wheelhouse").glob("pyrage-1.4.0-*.whl")))
    paths.extend(sorted((ROOT / "tests").glob("test_*.py")))
    paths.extend(sorted((ROOT / "reports").glob("*.md")))
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Missing or unsafe packaging input: " + str(path))
    if len(list((ROOT / "wheelhouse").glob("pyrage-1.4.0-*.whl"))) != 4:
        raise RuntimeError("Expected exactly four platform wheels")
    DEST.parent.mkdir(exist_ok=True)
    sums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n" for p in paths)
    with zipfile.ZipFile(DEST, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in paths:
            output.write(path, arcname="dscrypt-0.3.0/" + path.relative_to(ROOT).as_posix())
        output.writestr("dscrypt-0.3.0/SHA256SUMS", sums)
    digest = hashlib.sha256(DEST.read_bytes()).hexdigest()
    DEST.with_suffix(".zip.sha256").write_text(f"{digest}  {DEST.name}\n", encoding="ascii")
    print(DEST)
    print("bytes:", DEST.stat().st_size)
    print("SHA256:", digest)
    print("packaged files:", len(paths) + 1)

if __name__ == "__main__":
    main()
