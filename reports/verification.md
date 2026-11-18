# 验收报告

## 结论

在本次 Linux x86_64 / CPython 3.11.15 环境中，冻结源码通过完整回归、官方 age 双向互通、目录并发 no-clobber 检查和 128 MiB 文件往返基准，可以进入打包流程。不能据此宣称“完美”或宣称所有平台已验证。

## 固定版本与哈希

测试前记录与测试后复核一致：

- `dscrypt.py`: `f6c9582fe561d7eb9603331d67a395fae4b22818a5311aa04d181d7c1e920726`
- `pyproject.toml`: `32fb33aedfe5bf97461554045cd56680a5ef364d00b52d5471acbfd132336093`
- `requirements.txt`: `026ed7e95cdc26e4da7198e170906a234e4983edd90c09c1335d86065a855ce`
- `README.md`: `50d69870185fb0d7de0e3e9156f5b0b09aea25c1392af82f985a9d8515bbfd0c`

## 测试环境

- Linux x86_64，CPython 3.11.15，`pyrage 1.4.0`。
- 官方 `age v1.3.2` Linux amd64 发布包，SHA-256：`cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10`，下载后在测试同一临时目录中校验并执行。

## 完整回归

命令：

```text
.venv-cp311/bin/python -m unittest discover -s tests -v
```

实际执行时通过环境变量启用官方互通测试：

```text
DSCRYPT_TEST_AGE=<同一临时目录>/age .venv-cp311/bin/python -m unittest discover -s tests -v
```

结果：**23 项通过，0 项跳过，0 项失败**。

覆盖范围包括：

- `pyrage` 实现与官方 age 双向互通。
- 空文件、任意二进制、以旧 marker 开头的普通文件、有效 tar.gz 内容作为普通文件时的原字节还原。
- 多层目录、中文和空格路径、Armor、旧目录格式显式解包。
- 错误私钥、截断/篡改密文、无效收件公钥、无效 UTF-8 私钥。
- 路径穿越、绝对路径、盘符、反斜杠、Windows 非法字符、保留名、尾部点/空格、大小写冲突、链接和特殊文件拒绝。
- 同路径、硬链接、符号链接、FIFO、输出在源目录内、身份私钥保护。
- 无 `--force` 原子 no-clobber，以及 `--force` 失败时保留原目标。
- 目录发布前并发创建目标目录的确定性 `mkdir` 竞态：目标未被覆盖。

## 大文件基准

命令：

```text
.venv-cp311/bin/python tests/benchmark_stream.py
```

结果：

- 明文大小：134,217,728 字节（128 MiB）。
- 往返 SHA-256：一致。
- 加密峰值 RSS：20,296 KiB，耗时 0.22 秒。
- 解密峰值 RSS：22,512 KiB，耗时 0.35 秒。

这是当前 Linux x86_64 宿主的单次 GNU time 测量；不等同于所有平台的性能保证。目录模式使用临时归档文件，目录归档的磁盘空间和内存特征不能由该普通文件基准代表。

## 未验证项与限制

- 尚未在真实 aarch64、Windows、macOS 机器上运行 CLI；对应离线 wheel 已准备并校验不等于真机验证。
- 尚未验证不同 glibc 版本、Windows 文件系统行为和 macOS 权限/路径行为。
- 目录加密/解密可能使用临时明文归档文件；邮件附件的文件名、主题、正文、大小和时间等元数据仍可能暴露，age 密文不能保证邮件策略不拦截。
- 结论是“当前测试范围内通过并可进入打包”，不是“完美使用”或跨平台实机兼容性证明。
