#!/usr/bin/env bash
# 把 package/package.toml 的版本改成 0.<今天的日期>.<当天第几次>（UTC），印出新版本号。同一天再发一次，最后一段加一。
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
manifest="$here/package/package.toml"
today="$(date -u +%Y%m%d)"
current="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$manifest" | head -1)"
if [ "${current%.*}" = "0.$today" ]; then
  next="0.$today.$(( ${current##*.} + 1 ))"
else
  next="0.$today.0"
fi
sed -i "s/^version = \".*\"$/version = \"$next\"/" "$manifest"
echo "$next"
