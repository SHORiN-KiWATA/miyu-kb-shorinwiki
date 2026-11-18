# miyu-kb-shorinwiki

把 [shorinwiki](https://github.com/SHORiN-KiWATA/Shorin-ArchLinux-Guide) 打成 [Miyu](https://github.com/miyu-agent/miyu) 的知识库包。装上以后多一个只读的知识库「Shorin 的 Linux 指南」，她回答 Linux 的问题时会自己想起里面相关的段落。

```sh
miyu pkg install kb-shorinwiki
```

- `package/`：包本身。`package/kb/shorinwiki/` 是 wiki 的 Markdown（不含 `wiki/legacy/` 里过时的教程，不含图片：相对图片链接同步时改写成上游仓库在 `UPSTREAM_COMMIT` 那个提交上的 raw 地址），`kb.toml` 写着知识库的名字、说明，自动想起默认开着（知识库页能关）。
- `tools/sync.sh <wiki 的检出>`：照 wiki 更新文档，记下来源的提交（`UPSTREAM_COMMIT`）和被引用图片的 blob 哈希（`UPSTREAM_IMAGES`）；比较时不看链接里钉的提交号，上游只多了不碰文档和这些图片的提交算没变化，三样都不动。检出不是 git 仓库、`wiki/` 里一篇 Markdown 都没有时报错退出，知识库、`UPSTREAM_COMMIT`、`UPSTREAM_IMAGES` 不动。符号链接的 `.md` 不抄（在 stderr 说一句，不算失败）。`tools/bump.sh`：版本改成 `0.<日期>.<当天第几次>`。
- `.github/workflows/update.yml`：每天看一次 wiki，有新的文档改动就发新版；也可以在 Actions 里手动跑。

## 许可证

文档来自 shorinwiki，照原仓库的 [CC BY-SA 4.0](LICENSE) 转发，作者 SHORiN-KiWATA；本仓库的脚本同样以 CC BY-SA 4.0 发布。
