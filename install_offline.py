#!/usr/bin/env python3
"""Offline installation into a fresh venv; never contacts a package index."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description="验证本地 wheel 并离线安装 pyrage；需已有 CPython 3.11")
    parser.add_argument("--venv", default=str(ROOT / ".venv"))
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        parser.error("请使用 CPython 3.11 运行本安装器")
    target = Path(args.venv).absolute()
    if target.exists():
        parser.error("虚拟环境路径已存在，请指定新的 --venv 路径")
    wheels = ROOT / "wheelhouse"
    for line in (wheels / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        if Path(name).name != name:
            raise ValueError("非法 wheel 清单路径")
        if hashlib.sha256((wheels / name).read_bytes()).hexdigest() != digest:
            raise ValueError("wheel 校验失败：" + name)
    venv.EnvBuilder(with_pip=True).create(target)
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "--isolated", "install", "--no-index", "--no-cache-dir", "--only-binary=:all:", "--find-links", str(wheels), "pyrage==1.4.0"], check=True)
    subprocess.run([str(python), "-m", "pip", "--isolated", "check"], check=True)
    subprocess.run([str(python), str(ROOT / "dscrypt.py"), "--version"], check=True)
    print("离线安装完成。解释器：", python)
    print("运行：", python, ROOT / "dscrypt.py", "--help")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("安装失败：", exc, file=sys.stderr)
        raise SystemExit(2)
