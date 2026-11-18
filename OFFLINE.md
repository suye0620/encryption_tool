# 离线安装与验收

本包包含 dscrypt 源码、回归测试，以及 pyrage 1.4.0 的四个官方 wheel：

- Linux aarch64，glibc 2.17 或更新版本；不适用于 Alpine/musl。
- Linux x86_64，glibc 2.17 或更新版本。
- Windows x86_64。
- macOS Intel / Apple Silicon（universal2）。

这些 wheel 标记为 `cp310-abi3`，可用于 CPython 3.11；不是只能用于 Python 3.10。
本包不包含 Python 解释器，目标机器须预先安装 CPython 3.11。
运行只依赖 pyrage，无需 age、age-keygen、Rust、C 编译器或办公文档解析库。
既有业务环境的 27 项依赖不属于加密工具依赖，因此未打入本包。

## 安装

解压到新的目录，确保目标位置仅允许本人写入。

Linux / macOS：

```sh
python3.11 install_offline.py
.venv/bin/python dscrypt.py --help
.venv/bin/python -m unittest discover -s tests -v
```

Windows PowerShell：

```powershell
py -3.11 install_offline.py
.\.venv\Scripts\python.exe dscrypt.py --help
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

安装器先核对 wheel 的 SHA-256，再创建新的虚拟环境，仅通过本地 wheelhouse 安装，使用 `--no-index`，不会访问软件源。
环境目录已存在时安装器拒绝覆盖，可通过 `--venv 新路径` 另建环境。
Linux 发行版若缺少 venv/ensurepip，需要从发行版离线安装介质补齐，或使用已有 uv：

```sh
uv venv --python /已安装的/python3.11 --no-python-downloads .venv
uv pip install --python .venv/bin/python --no-index --find-links wheelhouse pyrage==1.4.0
uv pip check --python .venv/bin/python
```

## 密钥与跨平台流程

先在外部可信设备生成私钥，并导出公钥：

```sh
.venv/bin/python dscrypt.py keygen -o identity.txt
.venv/bin/python dscrypt.py pubkey --identity identity.txt
```

仅将输出的 `age1...` 公钥带入内网。不要将私钥带入内网，不要将私钥和密文放进同一封邮件。
Windows 使用 `.venv\Scripts\python.exe` 替换上述解释器路径。

加密单文件，文件内容可以是任意字节：

```sh
.venv/bin/python dscrypt.py encrypt -i 文档.docx -o attachment.age -r age1你的公钥
```

外部解密：

```sh
.venv/bin/python dscrypt.py decrypt -i attachment.age -o restored.docx --identity identity.txt
```

目录加密与显式解包：

```sh
.venv/bin/python dscrypt.py encrypt -i 文档目录 -o bundle.age -r age1你的公钥
.venv/bin/python dscrypt.py decrypt -i bundle.age -o restored --identity identity.txt --directory
```

默认 `decrypt` 只还原原始字节，不猜测文件类型。对目录密文不加 `--directory` 时，输出的是标准 tar.gz；可以交给普通归档工具处理。0.2 版带私有前缀的目录密文须使用 `--legacy-directory`。普通文件即便以旧前缀开头，也能默认逐字节还原。

## 目标机器验收

1. 断网安装成功，导入 pyrage 无错误。
2. 执行所附回归测试；无官方 age 时相关可选互通测试可能跳过，应查看具体输出。
3. 用目标机公钥加密空文件、真实文档和包含中文路径的目录。
4. 将密文传到实际 Windows/macOS 设备解密，比较原文件与还原文件 SHA-256。
5. 用较大文件检查实际内存和磁盘占用；解密目录需要临时磁盘空间。

宿主 Linux x86_64 的验证不能替代 aarch64、Windows 或 macOS 真机验收。随包提供目标 wheel 只证明依赖已备齐，不代表已完成跨平台实机测试。加密保护附件内容，不保证邮件网关允许传输加密附件。
