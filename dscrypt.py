#!/usr/bin/env python3
"""Offline file encryption using the standard age format through pyrage."""
from __future__ import annotations

import argparse
import ntpath
import os
import shutil
import stat
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import BinaryIO, Iterable

try:
    import pyrage
    from pyrage import x25519
except ImportError as exc:  # pragma: no cover - exercised on an unprovisioned host
    pyrage = None
    x25519 = None

VERSION = "0.3.0"
ARCHIVE_MARKER = b"DSCRYPT-TAR-V1\n"
CHUNK_SIZE = 1024 * 1024


class ToolError(Exception):
    """A user-facing command error."""


def require_pyrage() -> None:
    if pyrage is None or x25519 is None:
        raise ToolError("未安装 pyrage。请离线安装与 Python/CPU 匹配的 pyrage 依赖。")


def secure_chmod(path: Path, mode: int = 0o600) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def same_path_or_file(source: Path, target: Path) -> bool:
    try:
        return source.resolve() == target.resolve() or (
            path_exists(target) and os.path.samefile(source, target)
        )
    except OSError:
        return source.resolve() == target.resolve()


def atomic_target(path: Path, force: bool, *, allow_directory: bool = False) -> tuple[Path, Path]:
    if path_exists(path):
        if not force:
            raise ToolError(f"目标已存在：{path}；如需覆盖请使用 --force")
        if path.is_dir():
            if allow_directory:
                raise ToolError("--force 不会递归删除已有目录，请先移走目标目录")
            raise ToolError("不能用 --force 将文件覆盖为目录或删除已有目录")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    secure_chmod(temporary)
    return temporary, path


def publish_file(temporary: Path, final: Path, force: bool) -> None:
    if force:
        os.replace(temporary, final)
        return
    try:
        os.link(temporary, final)
    except FileExistsError as exc:
        raise ToolError(f"目标已存在：{final}；如需覆盖请使用 --force") from exc
    finally:
        temporary.unlink(missing_ok=True)


def within(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((str(root), str(candidate))) == str(root)
    except ValueError:
        return False


def validate_input(source: Path) -> None:
    if not path_exists(source):
        raise ToolError(f"输入不存在：{source}")
    if source.is_symlink():
        raise ToolError("不接受符号链接作为输入")
    mode = source.stat().st_mode
    if not (source.is_file() or source.is_dir()):
        raise ToolError("只支持普通文件或目录，不支持设备、套接字等特殊文件")
    if source.is_dir():
        archive_names: set[str] = set()
        _safe_member_name(source.name)
        for root, dirs, files in os.walk(source, followlinks=False):
            root_path = Path(root)
            for name in dirs + files:
                child = root_path / name
                if child.is_symlink():
                    raise ToolError(f"输入目录包含符号链接：{child}")
                child_mode = child.stat().st_mode
                if not (stat.S_ISDIR(child_mode) or stat.S_ISREG(child_mode)):
                    raise ToolError(f"输入目录包含特殊文件：{child}")
                relative = child.relative_to(source).as_posix()
                normalized = _safe_member_name(f"{source.name}/{relative}").casefold()
                if normalized in archive_names:
                    raise ToolError("输入目录包含 Windows 大小写冲突路径")
                archive_names.add(normalized)
    elif not stat.S_ISREG(mode):
        raise ToolError("只支持普通文件")


def make_tar_stream(source: Path, output: BinaryIO) -> None:
    with tarfile.open(fileobj=output, mode="w|gz") as archive:
        archive.add(source, arcname=source.name, recursive=True, filter=_tar_filter)


def _tar_filter(member: tarfile.TarInfo) -> tarfile.TarInfo:
    if member.issym() or member.islnk() or not (member.isdir() or member.isreg()):
        raise ToolError("输入目录包含链接或特殊文件，拒绝打包")
    return member


def safe_extract(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        seen: set[str] = set()
        for member in archive:
            name = _safe_member_name(member.name)
            key = name.casefold()
            if not name or key in seen:
                raise ToolError("目录归档包含重复或空路径")
            seen.add(key)
            if member.issym() or member.islnk() or not (member.isdir() or member.isreg()):
                raise ToolError("目录归档包含链接或特殊文件，拒绝解压")
            target = (destination / Path(*name.split("/"))).resolve()
            if not within(root, target):
                raise ToolError("目录归档包含路径穿越，拒绝解压")
            relative_parts = tuple(name.split("/"))
            cursor = destination
            for part in relative_parts[:-1]:
                cursor /= part
                if path_exists(cursor) and not cursor.is_dir():
                    raise ToolError("目录归档路径冲突，拒绝解压")
            if member.isdir():
                if path_exists(target) and not target.is_dir():
                    raise ToolError("目录归档路径冲突，拒绝解压")
                target.mkdir(parents=True, exist_ok=True)
                try:
                    os.chmod(target, stat.S_IMODE(member.mode) & 0o777)
                except OSError:
                    pass
                continue
            if path_exists(target) and target.is_dir():
                raise ToolError("目录归档路径冲突，拒绝解压")
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise ToolError(f"无法读取归档成员：{name}")
            with stream, target.open("wb") as output:
                shutil.copyfileobj(stream, output, length=CHUNK_SIZE)
            try:
                os.chmod(target, stat.S_IMODE(member.mode) & 0o777)
            except OSError:
                pass


def _safe_member_name(raw_name: str) -> str:
    if not raw_name or "\x00" in raw_name or "\\" in raw_name:
        raise ToolError("目录归档包含非法跨平台路径")
    drive, tail = ntpath.splitdrive(raw_name)
    if drive or raw_name.startswith("/"):
        raise ToolError("目录归档包含绝对路径，拒绝解压")
    parts = raw_name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ToolError("目录归档包含路径穿越，拒绝解压")
    for part in parts:
        if part.endswith((".", " ")) or any(char in part for char in '<>:"|?*'):
            raise ToolError("目录归档包含非法 Windows 文件名")
        stem = part.rstrip(" .").upper().split(".", 1)[0]
        if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            raise ToolError("目录归档包含 Windows 保留文件名")
    return "/".join(parts)


def publish_directory(source: Path, target: Path) -> None:
    try:
        target.mkdir()
    except FileExistsError as exc:
        raise ToolError("目录解密目标在发布前已存在，拒绝覆盖") from exc
    try:
        for child in source.iterdir():
            destination = target / child.name
            if path_exists(destination):
                raise ToolError("目录解密目标发生路径冲突，拒绝覆盖")
            os.rename(child, destination)
    except Exception:
        raise
    source.rmdir()


def _read_identity(path: Path):
    require_pyrage()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ToolError(f"无法读取私钥文件：{path}") from exc
    identities = []
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        try:
            identities.append(x25519.Identity.from_str(value))
        except Exception as exc:
            raise ToolError("私钥文件格式无效") from exc
    if not identities:
        raise ToolError("私钥文件为空")
    return identities


def _recipient(value: str):
    require_pyrage()
    try:
        return x25519.Recipient.from_str(value)
    except Exception as exc:
        raise ToolError("收件公钥格式无效") from exc


def _pyrage_error(action: str, exc: Exception) -> ToolError:
    return ToolError(f"{action}失败：请检查密钥、密文和输入文件")


def keygen(args: argparse.Namespace) -> None:
    require_pyrage()
    target = Path(args.output)
    if path_exists(target) and not args.force:
        raise ToolError(f"目标已存在：{target}；如需覆盖请使用 --force")
    if path_exists(target) and target.is_dir():
        raise ToolError("不能覆盖已有目录")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary, final = atomic_target(target, args.force)
    try:
        identity = x25519.Identity.generate()
        temporary.write_text(str(identity) + "\n", encoding="ascii")
        secure_chmod(temporary)
        publish_file(temporary, final, args.force)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(f"私钥已写入：{final}")
    print("请离线备份私钥，不要与密文通过同一渠道传输。")


def pubkey(args: argparse.Namespace) -> None:
    identities = _read_identity(Path(args.identity))
    print(str(identities[0].to_public()))


def _encrypt_stream(reader: BinaryIO, writer: BinaryIO, recipient, armored: bool) -> None:
    try:
        pyrage.encrypt_io(reader, writer, [recipient], armored=armored)
    except Exception as exc:
        raise _pyrage_error("加密", exc) from exc


def _decrypt_stream(reader: BinaryIO, writer: BinaryIO, identities) -> None:
    try:
        pyrage.decrypt_io(reader, writer, identities)
    except Exception as exc:
        raise _pyrage_error("解密", exc) from exc


def encrypt(args: argparse.Namespace) -> None:
    require_pyrage()
    source, target = Path(args.input), Path(args.output)
    validate_input(source)
    if same_path_or_file(source, target):
        raise ToolError("输入和输出不能是同一路径或同一文件的硬链接")
    if source.is_dir() and within(source.resolve(), target.resolve()):
        raise ToolError("输出不能放在待加密目录内部")
    temporary, final = atomic_target(target, args.force)
    try:
        with temporary.open("wb") as encrypted:
            if source.is_dir():
                with tempfile.TemporaryFile(mode="w+b") as archive:
                    make_tar_stream(source, archive)
                    archive.seek(0)
                    _encrypt_stream(archive, encrypted, _recipient(args.recipient), args.armor)
            else:
                with source.open("rb") as plain:
                    _encrypt_stream(plain, encrypted, _recipient(args.recipient), args.armor)
        secure_chmod(temporary)
        publish_file(temporary, final, args.force)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(f"已加密：{final}")


def decrypt(args: argparse.Namespace) -> None:
    require_pyrage()
    source, target = Path(args.input), Path(args.output)
    if not source.is_file() or source.is_symlink():
        raise ToolError(f"密文不存在或不是普通文件：{source}")
    if same_path_or_file(source, target):
        raise ToolError("输入和输出不能是同一路径或同一文件的硬链接")
    identity_path = Path(args.identity)
    if same_path_or_file(identity_path, target):
        raise ToolError("输出不能覆盖解密私钥")
    identities = _read_identity(identity_path)
    directory_mode = args.directory or args.legacy_directory
    if args.legacy_directory and not args.directory:
        directory_mode = True
    if directory_mode:
        if path_exists(target) and target.is_dir():
            raise ToolError("目标目录已存在；为避免递归删除，请先移走后再解密")
        if path_exists(target) and not args.force:
            raise ToolError(f"目标已存在：{target}；如需覆盖请使用 --force")
    if directory_mode and path_exists(target):
        raise ToolError("目录解密目标必须不存在；不会删除或覆盖已有目标")
    temporary, final = atomic_target(target, args.force, allow_directory=directory_mode)
    try:
        with tempfile.TemporaryFile(mode="w+b") as plain:
            with source.open("rb") as encrypted:
                _decrypt_stream(encrypted, plain, identities)
            plain.seek(0)
            if directory_mode:
                archive_fd, archive_name = tempfile.mkstemp(prefix="dscrypt-archive-")
                os.close(archive_fd)
                archive_path = Path(archive_name)
                try:
                    with archive_path.open("wb") as archive:
                        shutil.copyfileobj(plain, archive, length=CHUNK_SIZE)
                    with tempfile.TemporaryDirectory(prefix="dscrypt-extract-", dir=target.parent) as extracted:
                        extracted_path = Path(extracted)
                        if args.legacy_directory:
                            if not plain_marker(archive_path):
                                raise ToolError("不是旧版 DSCRYPT-TAR-V1 目录归档")
                            archive_path = strip_legacy_marker(archive_path)
                        safe_extract(archive_path, extracted_path)
                        publish_directory(extracted_path, final)
                finally:
                    archive_path.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)
            else:
                with temporary.open("wb") as output:
                    shutil.copyfileobj(plain, output, length=CHUNK_SIZE)
                secure_chmod(temporary)
                publish_file(temporary, final, args.force)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(f"已解密：{final}")


def plain_marker(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(len(ARCHIVE_MARKER)) == ARCHIVE_MARKER


def strip_legacy_marker(path: Path) -> Path:
    fd, name = tempfile.mkstemp(prefix="dscrypt-legacy-")
    os.close(fd)
    stripped = Path(name)
    try:
        with path.open("rb") as stream, stripped.open("wb") as output:
            stream.seek(len(ARCHIVE_MARKER))
            shutil.copyfileobj(stream, output, length=CHUNK_SIZE)
        path.unlink(missing_ok=True)
        return stripped
    except Exception:
        stripped.unlink(missing_ok=True)
        raise


def inspect(args: argparse.Namespace) -> None:
    source = Path(args.input)
    if not source.is_file():
        raise ToolError(f"密文不存在：{source}")
    with source.open("rb") as stream:
        prefix = stream.read(256)
    print("格式：age（由 pyrage 解析）")
    print(f"密文大小：{source.stat().st_size} 字节")
    if prefix.startswith(b"age-encryption.org/") or prefix.startswith(b"-----BEGIN AGE ENCRYPTED FILE-----"):
        print("这是 age 密文；原始文件名和 MIME 类型不写入密文头。")
    else:
        print("文件头不是标准 age 密文；请确认密文文件有效。")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="dscrypt", description="使用 pyrage 的离线文件加密工具")
    root.add_argument("--version", action="version", version=f"dscrypt {VERSION}")
    commands = root.add_subparsers(dest="command", required=True)
    command = commands.add_parser("keygen", help="生成 age 私钥")
    command.add_argument("-o", "--output", required=True)
    command.add_argument("--force", action="store_true")
    command.set_defaults(func=keygen)
    command = commands.add_parser("pubkey", help="从 age 私钥导出公钥")
    command.add_argument("--identity", required=True)
    command.set_defaults(func=pubkey)
    command = commands.add_parser("encrypt", help="加密文件或目录")
    command.add_argument("-i", "--input", required=True)
    command.add_argument("-o", "--output", required=True)
    command.add_argument("-r", "--recipient", required=True)
    command.add_argument("--armor", action="store_true", help="使用 ASCII Armor 输出")
    command.add_argument("--force", action="store_true")
    command.set_defaults(func=encrypt)
    command = commands.add_parser("decrypt", help="解密 age 文件；目录归档需显式指定 --directory")
    command.add_argument("-i", "--input", required=True)
    command.add_argument("-o", "--output", required=True)
    command.add_argument("--identity", required=True)
    command.add_argument("--directory", action="store_true", help="将明文作为 tar.gz 安全解包到目录")
    command.add_argument("--legacy-directory", action="store_true", help=argparse.SUPPRESS)
    command.add_argument("--force", action="store_true")
    command.set_defaults(func=decrypt)
    command = commands.add_parser("inspect", help="查看密文基本信息")
    command.add_argument("-i", "--input", required=True)
    command.set_defaults(func=inspect)
    return root


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(list(argv) if argv is not None else None)
    try:
        args.func(args)
        return 0
    except (ToolError, OSError, tarfile.TarError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
