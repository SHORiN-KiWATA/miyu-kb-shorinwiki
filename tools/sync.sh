#!/usr/bin/env bash
# 照 shorinwiki 的一份检出更新知识库：把 wiki/ 下的 Markdown（不要 legacy/）抄进 package/kb/shorinwiki/，记下来源的提交。
# 用法：tools/sync.sh <shorinwiki 的检出目录>（要 git、python3）
# 文档或被引用的图片有变化时退出码 0 并印 changed；没变化印 unchanged。版本号不在这里改，交给 tools/bump.sh。
# 比较时不看图片链接里钉的提交号；被引用的图片记在 UPSTREAM_IMAGES（每行 `<blob 哈希> <上游路径>`，上游没有的写 -），
# 和上次的清单比。unchanged 时知识库、UPSTREAM_COMMIT、UPSTREAM_IMAGES 都不动，所以 UPSTREAM_COMMIT 总是链接钉的那个提交。
# 先在暂存区备齐、查过（是 git 仓库、取到提交号、至少有一篇 Markdown）才替换知识库；哪一步失败都退出非 0，
# 知识库、UPSTREAM_COMMIT、UPSTREAM_IMAGES 原样不动。
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
# 改写过的链接指到的上游路径记进 $stage/paths，下面取它们的 blob 哈希。
raw="https://raw.githubusercontent.com/$upstream"
python3 -I - "$stage/kb" "$raw/$commit/" "$stage/paths" <<'PY'
import pathlib
import posixpath
import re
import sys
import urllib.parse

root, prefix, listing = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
paths = set()
image = re.compile(r"(!\[[^\]]*\]\()([^)\s]+)")


def rewrite(rel, target):
    if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:|/|#", target):
        return target                      # 已经是地址、站内绝对路径或页内锚点
    path, sep, fragment = target.partition("#")
    resolved = posixpath.normpath(posixpath.join("wiki", posixpath.dirname(rel), urllib.parse.unquote(path)))
    if resolved.startswith(".."):
        return target                      # 指到上游仓库外面，不知道该指哪儿
    paths.add(resolved)
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
with open(listing, "w", encoding="utf-8") as handle:
    handle.writelines(p + "\n" for p in sorted(paths))
PY
cp "$kb/kb.toml" "$stage/kb/kb.toml"

# 被引用的图片：深度 1 的克隆也取得到 HEAD 里的 blob 哈希。
while IFS= read -r path; do
  blob="$(git -C "$src" rev-parse --verify -q "HEAD:$path")" || blob=-
  printf '%s %s\n' "$blob" "$path"
done < "$stage/paths" > "$stage/UPSTREAM_IMAGES"

# 比较前把链接里钉的提交号归一化掉：上游只多了不碰 wiki 的提交不算变化。
mkdir -p "$stage/cmp"
cp -R "$stage/kb" "$stage/cmp/new"
cp -R "$kb" "$stage/cmp/old"
find "$stage/cmp" -type f -name '*.md' -exec env LC_ALL=C sed -i -E \
  "s#(https://raw\.githubusercontent\.com/$upstream/)[0-9a-f]{40}/#\1-/#g" {} +
old_images="$here/UPSTREAM_IMAGES"
[ -e "$old_images" ] || old_images=/dev/null
if diff -rq "$stage/cmp/new" "$stage/cmp/old" > /dev/null 2>&1 &&
  cmp -s "$stage/UPSTREAM_IMAGES" "$old_images"; then
  echo unchanged
  exit 0
fi

rm -rf "$here/.kb.new"
cp -R "$stage/kb" "$here/.kb.new"
rm -rf "$kb"
mv "$here/.kb.new" "$kb"
printf '%s\n' "$commit" > "$here/UPSTREAM_COMMIT.new"
cp "$stage/UPSTREAM_IMAGES" "$here/UPSTREAM_IMAGES.new"
mv "$here/UPSTREAM_COMMIT.new" "$here/UPSTREAM_COMMIT"
mv "$here/UPSTREAM_IMAGES.new" "$here/UPSTREAM_IMAGES"
echo changed
