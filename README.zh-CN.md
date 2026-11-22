<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

# Shorin 的 Linux 指南知识库（kb-shorinwiki）

> <sub>本文档由 Anthropic 的 Claude Fable 5.2 生成。</sub>

这个仓库把 [shorinwiki](https://github.com/SHORiN-KiWATA/Shorin-ArchLinux-Guide) 打包成 [Miyu](https://github.com/miyu-agent/miyu) 的知识库软件包。安装以后会多出一个只读的知识库 `Shorin 的 Linux 指南`，AI 回答 Linux 的问题时会自动想起里面相关的段落。

运行以下命令安装：

```sh
miyu pkg install kb-shorinwiki
```

仓库里有以下内容：

- `package/`：软件包本身。`package/kb/shorinwiki/` 是维基的 Markdown 文档，不包含 `wiki/legacy/` 里过时的教程，也不包含图片：同步时，相对路径的图片链接会改写成上游仓库在 `UPSTREAM_COMMIT` 记录的那个提交上的原始文件（raw）地址。`kb.toml` 里写着知识库的名字和说明，「自动想起」默认开启，可以在设置页的 `知识库` 里关闭。
- `tools/sync.sh <wiki 的检出>`：按照维基更新文档，并记下来源的提交（`UPSTREAM_COMMIT`）和被引用图片的 Git 对象哈希（blob 哈希，`UPSTREAM_IMAGES`）。比较时不看链接里固定的提交号；如果上游只多了不涉及文档和这些图片的提交，就算作没有变化，三样都不修改。如果检出不是 Git 仓库，或者 `wiki/` 里一篇 Markdown 都没有，脚本会报错退出，知识库、`UPSTREAM_COMMIT`、`UPSTREAM_IMAGES` 都不会被修改。符号链接形式的 `.md` 文件不会被复制（脚本会在标准错误输出 stderr 里提示一句，不算失败）。`tools/bump.sh`：把版本改成 `0.<日期>.<当天第几次>`。
- `.github/workflows/update.yml`：每天检查一次维基，有新的文档改动就发布新版本；也可以在 GitHub Actions 里手动运行。

## 许可证

文档来自 shorinwiki，按照原仓库的 [CC BY-SA 4.0](LICENSE) 许可证再分发，作者是 SHORiN-KiWATA；这个仓库里的脚本同样以 CC BY-SA 4.0 发布。
