# 本机可执行文件构建与验证

本次生成 dscrypt 0.3.0 的 Linux x86_64 单文件命令行程序。内置 CPython 与 pyrage，无需目标机器预装 Python、uv 或 age。主程序未修改。

## 环境和构建依赖

- 构建系统：Linux x86_64，glibc 2.35
- CPython 3.11.15；pyrage 1.4.0
- PyInstaller 6.22.3
- pyinstaller-hooks-contrib 2026.10
- altgraph 0.17.5；packaging 26.3；setuptools 84.2.1
- `uv pip check`：33 个包，全部依赖兼容。

从项目根目录运行：

```bash
uv pip install --python .venv-cp311/bin/python \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.10 \
  altgraph==0.17.5 packaging==26.3 setuptools==84.2.1

.venv-cp311/bin/python -m PyInstaller \
  --onefile --name dscrypt --collect-all pyrage \
  --distpath dist/linux-x86_64 --workpath build/linux-x86_64 \
  --specpath build dscrypt.py

.venv-cp311/bin/python tests/verify_frozen.py dist/linux-x86_64/dscrypt
```

## 离线构建环境（Linux x86_64）

从项目根目录执行以下命令。第一步使用 CPython 3.11 创建新虚拟环境并安装 pyrage。第二步用 uv 从本地构建依赖目录安装固定版本，并按清单校验 SHA-256。

```bash
python3.11 install_offline.py --venv .venv-build
uv --offline --no-cache --no-config pip install --python .venv-build/bin/python \
  --no-index --only-binary :all: --require-hashes \
  --find-links wheelhouse/pyinstaller-linux-x86_64 \
  -r wheelhouse/pyinstaller-linux-x86_64/requirements.txt
uv --offline --no-config pip check --python .venv-build/bin/python
```

随后用 `.venv-build/bin/python` 执行上面的 PyInstaller 和验收命令。离线构建需要预先准备 CPython 3.11、uv 和系统构建工具（例如 `objdump`，通常由 binutils 提供）。其他平台应准备对应的 PyInstaller wheel 和平台专用依赖。

## 使用

```bash
./dist/linux-x86_64/dscrypt --version
./dist/linux-x86_64/dscrypt --help
./dist/linux-x86_64/dscrypt keygen -o private.key
./dist/linux-x86_64/dscrypt pubkey --identity private.key
# 用上一条命令输出的公钥替换 age1...：
./dist/linux-x86_64/dscrypt encrypt -i input.pdf -o attachment.age -r age1...
./dist/linux-x86_64/dscrypt decrypt -i attachment.age -o restored.pdf --identity private.key
```

私钥必须备份；不要与密文一同发送。目录可直接 encrypt，解密目录时需要加 `--directory`。这是命令行程序，不是图形窗口应用。

## 本次验证结果

可执行文件复制到独立临时目录运行；子进程 PATH 仅包含临时目录，清除了 PYTHONHOME、PYTHONPATH、VIRTUAL_ENV 和 LD_LIBRARY_PATH。测试控制器使用项目 Python 和 pyrage 生成测试数据，但被测子进程直接执行独立 ELF，不调用系统 Python 或外部 age。未在彻底移除 Python 的新操作系统镜像中验证。

- 复用原端到端测试：17 项通过、0 跳过。
- 覆盖密钥生成、公钥导出、普通二进制/空文件/特殊前缀、目录、旧目录、Armor、恶意归档、错误私钥、截断与篡改密文、覆盖保护、链接与特殊文件拒绝、Windows 非法路径和大小写冲突。
- 独立程序另做 128 MiB 随机文件往返，SHA-256 一致。
- 测试前后主程序 SHA-256 一致。
- 本次未在冻结程序上重跑官方 age 命令行互通和 Python 内部 monkeypatch 竞态测试；这些属于此前同一源码的 23 项验收。
- 原始输出：`reports/frozen-linux-x86_64.log`。

产物：`dist/linux-x86_64/dscrypt`

大小：10,787,288 字节，约 10.3 MiB。

```text
主程序 SHA-256:
f6c9582fe561d7eb9603331d67a395fae4b22818a5311aa04d181d7c1e920726
可执行文件 SHA-256:
3a6791918c59e612519f70c5359cf2fa8693fdaa17955ca7716e619d3b75aac5
```

## 兼容性和使用边界

- 本次只验证当前 Linux x86_64 宿主，不能在 Windows、macOS 或 Linux aarch64 运行此 ELF。
- 打包包含 Python，但仍依赖系统动态加载器及 libc/libz 等库，不是完全静态程序。
- 构建宿主 glibc 为 2.35；没有证明旧系统的兼容下限。pyrage wheel 的 glibc 2.17 下限不能直接作为整个可执行程序的下限。
- 如需支持更旧 Linux，应在所支持的最旧兼容构建环境重建，并在目标系统实测。
- Windows/macOS/aarch64 应在各自平台与架构的构建环境安装 PyInstaller 后构建；macOS Intel 和 Apple Silicon 应分别构建，除非整个 Python 运行时和扩展均符合 universal2 要求。
- PyInstaller 单文件运行时会将内置运行时解包到临时目录，需要可写、可执行的临时存储；noexec 环境需配置合适的临时目录或改用 onedir 构建。
- 程序原有临时明文、邮件元数据与加密附件拦截边界仍然适用。
- 构建日志中的 `pyrage.x25519` 静态扫描警告对应 Rust 扩展动态导出的子模块；实际冻结程序密钥生成和加解密已通过验证。

Coze 未登录，本次产物尚未上传云盘。
