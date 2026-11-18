# dscrypt

`dscrypt` 是一个面向 Linux aarch64 内网环境的离线文件加密命令行工具。它通过 `pyrage` 调用标准 age 实现，不自创密码学算法或密文格式；生成的密文可由官方 age 工具以及其他兼容实现解密。

## 运行依赖

运行时需要 Python 3.10+ 和固定版本 `pyrage==1.4.0`。本项目不再调用 `age` 或 `age-keygen` 外部可执行文件，也不需要它们出现在 `PATH`。

```bash
python3 -m pip install --no-index --find-links ./wheelhouse pyrage==1.4.0
python3 dscrypt.py --help
```

离线部署时，应在联网准备机下载并校验适配目标 Python 3.11、Linux aarch64、glibc 版本的 wheel 及其依赖，连同项目代码和 SHA-256 清单带入内网。当前开发验证覆盖 CPython 3.11/Linux x86-64；Linux aarch64、Windows 和 macOS 仍需在对应平台验收。`pyrage` 含原生组件，不能把 x86-64 wheel 直接复制到 aarch64。

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

完整离线安装步骤见 [OFFLINE.md](OFFLINE.md)。离线包包含四个经过 SHA-256 校验的 pyrage wheel，目标机仍须预先安装 CPython 3.11；不包含 Python 解释器和业务环境中无关的文档处理依赖。

## 兼容性

密文使用标准 age 格式。`pyrage`、官方 `age` 和其他兼容 age 实现可以互通；跨平台解密时只需准备同一私钥。`inspect` 只显示密文大小和标准格式判断，不会尝试推断原文件类型：

```bash
python3 dscrypt.py inspect -i report.docx.age
```

## 安全边界

age 密文可阻止没有私钥的常规邮件解析器直接读取附件明文，但不能保证邮件系统不识别或拒收加密附件。附件名、邮件主题、正文、大小和时间等元数据仍可能暴露；私钥、加密前后的终端、临时文件和备份也需要另行保护。请遵守组织的邮件和安全策略。
