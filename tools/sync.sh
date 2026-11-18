#!/usr/bin/env bash
# 照 shorinwiki 的一份检出更新知识库：把 wiki/ 下的 Markdown（不要 legacy/）抄进 package/kb/shorinwiki/，记下来源的提交。
# 用法：tools/sync.sh <shorinwiki 的检出目录>（要 git、python3）
# 文档有变化时退出码 0 并印 changed；没变化印 unchanged。版本号不在这里改，交给 tools/bump.sh。
# 先在暂存区备齐、查过（是 git 仓库、取到提交号、至少有一篇 Markdown）才替换知识库；哪一步失败都退出非 0，
# 知识库和 UPSTREAM_COMMIT 原样不动。
set -euo pipefail
src="${1:?给 shorinwiki 的检出目录}"
here="$(cd "$(dirname "$0")/.." && pwd)"
kb="$here/package/kb/shorinwiki"
upstream="SHORiN-KiWATA/Shorin-ArchLinux-Guide"
[ -d "$src/wiki" ] || { echo "$src 里没有 wiki/" >&2; exit 1; }

# 源必须自己就是 git 仓库的顶层（不能是别的仓库里的一个目录），提交号先取到手。
top="$(git -C "$src" rev-parse --show-toplevel 2>/dev/null)" &&
  [ "$(cd "$top" && pwd -P)" = "$(cd "$src" && pwd -P)" ] &&
  commit="$(git -C "$src" rev-parse --verify HEAD 2>/dev/null)" ||
  { echo "$src 不是 git 仓库的检出（取不到提交号）" >&2; exit 1; }

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/kb"
# 只要 Markdown；legacy/ 里是过时的教程（项目主人 2026-11-12 定不打进去）。
(cd "$src/wiki" && find . -name '*.md' -not -path './legacy/*' -print0) |
  while IFS= read -r -d '' file; do
    mkdir -p "$stage/kb/$(dirname "$file")"
    cp "$src/wiki/$file" "$stage/kb/$file"
  done
count="$(find "$stage/kb" -name '*.md' | wc -l)"
[ "$count" -gt 0 ] || { echo "$src/wiki/ 里一篇 Markdown 都没有，不更新知识库" >&2; exit 1; }

# 图片不抄（知识库按文字检索），相对图片链接改写成钉在这个提交上的上游 raw 地址，免得指向不存在的文件。
python3 -I - "$stage/kb" "https://raw.githubusercontent.com/$upstream/$commit/" <<'PY'
import pathlib
import posixpath
import re
import sys
import urllib.parse

root, prefix = pathlib.Path(sys.argv[1]), sys.argv[2]
image = re.compile(r"(!\[[^\]]*\]\()([^)\s]+)")


def rewrite(rel, target):
    if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:|/|#", target):
        return target                      # 已经是地址、站内绝对路径或页内锚点
    path, sep, fragment = target.partition("#")
    resolved = posixpath.normpath(posixpath.join("wiki", posixpath.dirname(rel), urllib.parse.unquote(path)))
    if resolved.startswith(".."):
        return target                      # 指到上游仓库外面，不知道该指哪儿
    return prefix + urllib.parse.quote(resolved) + sep + fragment


for md in sorted(root.rglob("*.md")):
    rel = md.relative_to(root).as_posix()
    with open(md, encoding="utf-8", newline="") as handle:
        text = handle.read()
    lines, fence = text.split("\n"), False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            fence = not fence
        elif not fence:
            lines[i] = image.sub(lambda m: m.group(1) + rewrite(rel, m.group(2)), line)
    new = "\n".join(lines)
    if new != text:
        with open(md, "w", encoding="utf-8", newline="") as handle:
            handle.write(new)
PY
cp "$kb/kb.toml" "$stage/kb/kb.toml"

if diff -rq "$stage/kb" "$kb" > /dev/null 2>&1; then
  result=unchanged
else
  rm -rf "$here/.kb.new"
  cp -R "$stage/kb" "$here/.kb.new"
  rm -rf "$kb"
  mv "$here/.kb.new" "$kb"
  result=changed
fi
printf '%s\n' "$commit" > "$here/UPSTREAM_COMMIT.new"
mv "$here/UPSTREAM_COMMIT.new" "$here/UPSTREAM_COMMIT"
echo "$result"
