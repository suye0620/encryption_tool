# dscrypt

`dscrypt` 是一个跨平台的文件加密命令行工具，支持 Linux、macOS 和 Windows。它通过 `pyrage` 调用标准 age 实现，不自创密码学算法或密文格式；全部操作在本地完成，无需联网。生成的密文使用标准 age 格式，可由官方 age 工具以及其他兼容实现解密，各平台只需持有同一私钥。

## 运行依赖

运行时需要 Python 3.10+ 和固定版本 `pyrage==1.4.0`。本项目不再调用 `age` 或 `age-keygen` 外部可执行文件，也不需要它们出现在 `PATH`。

```bash
python3 -m pip install --no-index --find-links ./wheelhouse pyrage==1.4.0
python3 dscrypt.py --help
```

在无网络的机器上部署时，先在联网机器上下载并校验与目标平台匹配的 wheel 及其依赖，连同项目代码和 SHA-256 清单一并转移。`pyrage` 含原生组件，wheel 必须与目标系统和架构匹配，不能跨架构复制。

如需免装 Python 的单文件可执行程序，可在各目标平台用 PyInstaller 打包，步骤见 [BUILD_EXECUTABLE.md](BUILD_EXECUTABLE.md)。

## 使用

生成私钥并导出公钥：

```bash
python3 dscrypt.py keygen -o identity.txt
python3 dscrypt.py pubkey --identity identity.txt
```

私钥文件会以 `0600` 权限写入；不要把私钥和密文通过同一渠道传输。

加密普通文件：

```bash
python3 dscrypt.py encrypt -i report.docx -o report.docx.age -r 'age1...'
```

加密整个目录：

```bash
python3 dscrypt.py encrypt -i private_dir -o private_dir.age -r 'age1...'
```

输出文件名完全由 `-o` 指定，默认不追加 `.age`；需要时加 `--age-suffix` 自动追加，已以 `.age` 结尾（不分大小写）时不重复追加。解密和 `inspect` 按密文内容识别，不依赖文件扩展名。

目录会分块制作标准 `tar.gz`，暂存于 Python 的 `TemporaryFile` 后交给 pyrage 加密；普通文件加密直接读取输入流。目录归档和解密暂存可能写入磁盘，自动清理不等于安全擦除。请在可信、空间充足的临时存储上运行；Linux/macOS 可通过 `TMPDIR` 指定临时目录。也可使用 `--armor` 输出 ASCII Armor 文本。

解密普通文件必须按默认模式执行，原始字节会直接还原：

```bash
python3 dscrypt.py decrypt --identity identity.txt -i report.docx.age -o report.docx
```

解密目录归档必须显式指定 `--directory`，工具会拒绝符号链接、硬链接、特殊文件、路径穿越和路径冲突：

```bash
python3 dscrypt.py decrypt --directory --identity identity.txt \
  -i private_dir.age -o restored
```

旧版本带 `DSCRYPT-TAR-V1` 前缀的目录密文只在明确指定 `--legacy-directory` 时支持：

```bash
python3 dscrypt.py decrypt --legacy-directory --identity identity.txt \
  -i old-private_dir.age -o restored
```

`--force` 只用于普通文件输出替换；目录解密要求目标完全不存在，不会删除已有文件或目录。认证或解包失败不发布最终目标。输入输出同路径、同一文件的硬链接，以及把输出放在待加密目录内，都会被拒绝。输出不能覆盖解密私钥；归档路径拒绝绝对路径、反斜杠、盘符、`..`、非法 Windows 字符和保留名。无 `--force` 的文件发布依赖文件系统硬链接支持；不支持时会明确失败，不会退化为可能覆盖文件的写法。操作期间不要让其他进程修改输入、输出父目录或私钥。POSIX 私钥权限为 `0600`；Windows 应另行检查用户目录 ACL。

完整离线安装步骤见 [OFFLINE.md](OFFLINE.md)。离线安装只需 wheelhouse 中的 pyrage wheel 和目标机上已装好的 CPython 3.11。

## 兼容性

密文使用标准 age 格式。`pyrage`、官方 `age` 和其他兼容 age 实现可以互通；跨平台解密时只需准备同一私钥。`inspect` 只显示密文大小和标准格式判断，不会尝试推断原文件类型：

```bash
python3 dscrypt.py inspect -i report.docx.age
```

## 安全边界

age 密文可阻止没有私钥的一方读取文件内容；密文本身不包含原文件名和类型等元数据。文件名、大小、时间等可见信息不在加密范围内，传输渠道仍可能按自身策略处理或拦截加密文件。私钥、加密前的终端、临时文件和备份也需要另行保护。
