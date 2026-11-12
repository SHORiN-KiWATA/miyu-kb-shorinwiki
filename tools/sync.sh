#!/usr/bin/env bash
# 照 shorinwiki 的一份检出更新知识库：把 wiki/ 下的 Markdown（不要 legacy/）抄进 package/kb/shorinwiki/，记下来源的提交。
# 用法：tools/sync.sh <shorinwiki 的检出目录>
# 文档有变化时退出码 0 并印 changed；没变化印 unchanged。版本号不在这里改，交给 tools/bump.sh。
set -euo pipefail
src="${1:?给 shorinwiki 的检出目录}"
here="$(cd "$(dirname "$0")/.." && pwd)"
kb="$here/package/kb/shorinwiki"
[ -d "$src/wiki" ] || { echo "$src 里没有 wiki/" >&2; exit 1; }

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
# 只要 Markdown；legacy/ 里是过时的教程（项目主人 2026-11-12 定不打进去）。
(cd "$src/wiki" && find . -name '*.md' -not -path './legacy/*' -print0) |
  while IFS= read -r -d '' file; do
    mkdir -p "$stage/$(dirname "$file")"
    cp "$src/wiki/$file" "$stage/$file"
  done
cp "$kb/kb.toml" "$stage/kb.toml"

if diff -rq "$stage" "$kb" > /dev/null 2>&1; then
  echo unchanged
else
  rm -rf "$kb"
  mkdir -p "$kb"
  cp -R "$stage/." "$kb/"
  echo changed
fi
git -C "$src" rev-parse HEAD > "$here/UPSTREAM_COMMIT"
