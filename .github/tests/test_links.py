# tools/sync.sh 改写图片链接的测试（审计 2026-11-18 #187）。
#
# 跑法（在仓库根）：
#   python3 -I -B -m unittest discover -s .github/tests
# （不加 -t .：.github 不是合法的包名，加了 unittest 会报 Start directory is not importable。）
#
# 只用标准库、bash 和 git，不联网：用现有知识库的 Markdown 还原一个假的上游 git 仓库
# （wiki/ 下放这些 .md，图片路径上放空的占位文件），把 tools/sync.sh 和知识库拷进
# 临时目录跑拷贝，绝不动仓库本身。
# 放 .github/tests/ 而不是 tools/：和别的包仓库一个跑法；.github 和 tools 都不进包。

import os
import pathlib
import posixpath
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.parse

REPO = pathlib.Path(__file__).resolve().parents[2]
KB = pathlib.Path("package") / "kb" / "shorinwiki"
UPSTREAM = "SHORiN-KiWATA/Shorin-ArchLinux-Guide"
RAW = "https://raw.githubusercontent.com/"
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def image_targets(text):
    """Markdown 图片链接的目标（去掉标题、#片段），跳过代码块里的。"""
    out, fence = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        for m in IMAGE.finditer(line):
            parts = m.group(1).strip().split()
            if parts:
                out.append(parts[0])
    return out


def is_remote(target):
    return target.startswith(("http://", "https://"))


def local_part(target):
    return urllib.parse.unquote(target.split("#")[0])


PINNED = re.compile(r"(!\[[^\]]*\]\()" + re.escape(RAW + UPSTREAM + "/") + r"[0-9a-f]{40}/([^)\s#]+)")


def as_upstream(text, rel):
    """把同步时改写成上游 raw 地址的图片链接还原成相对链接（代码块里的同步时没动，这里也不动）。"""
    here = posixpath.join("wiki", posixpath.dirname(rel))

    def back(m):
        path = urllib.parse.unquote(m.group(2))
        return m.group(1) + urllib.parse.quote(posixpath.relpath(path, here))

    lines, fence = text.split("\n"), False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            fence = not fence
        elif not fence:
            lines[i] = PINNED.sub(back, line)
    return "\n".join(lines)


class ImageLinks(unittest.TestCase):
    # 审计 #187：sync.sh 只抄 *.md，上游文档里的图片相对链接（../pictures/x.png 等）在
    # 知识库里全都指向不存在的文件（origin/main 上 13 个文件 94 处）。主人定：同步时改写成
    # 上游仓库的 raw 地址，按 UPSTREAM_COMMIT 钉的提交拼：
    #   https://raw.githubusercontent.com/<owner>/<repo>/<commit>/<相对路径解析后的路径>
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
                    "HOME": str(base), "TMPDIR": str(base),
                    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CEILING_DIRECTORIES": str(base),
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        here = base / "here"
        (here / "tools").mkdir(parents=True)
        shutil.copy2(REPO / "tools" / "sync.sh", here / "tools" / "sync.sh")
        shutil.copytree(REPO / KB, here / KB)
        (here / "UPSTREAM_COMMIT").write_text("0" * 40 + "\n")
        self.here, self.kb = here, here / KB

        # 假上游：wiki/ 下是现有知识库的 .md；每个相对图片链接解析出的路径上放占位文件。
        # 知识库同步过以后，里面的图片链接已经是钉在某个提交上的上游 raw 地址：先还原成上游原来的
        # 相对写法，假上游才和真上游一个样（不然没有相对链接可测）。
        up = base / "up"
        self.expected = {}       # 知识库里的 .md 相对路径 → 该文件里应出现的上游路径集合
        for md in sorted(self.kb.rglob("*.md")):
            rel = md.relative_to(self.kb).as_posix()
            text = as_upstream(md.read_text(encoding="utf-8"), rel)
            dst = up / "wiki" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8")
            for t in image_targets(text):
                if is_remote(t):
                    continue
                path = posixpath.normpath(posixpath.join("wiki", posixpath.dirname(rel), local_part(t)))
                self.assertFalse(path.startswith(".."), f"{rel}: {t} 解析到仓库外面")
                img = up / path
                img.parent.mkdir(parents=True, exist_ok=True)
                img.write_bytes(b"")
                self.expected.setdefault(rel, set()).add(path)
        self.assertTrue(self.expected, "现有知识库里没有相对图片链接，这条测试没东西可测")
        for cmd in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
            subprocess.run(["git", "-C", str(up), *cmd], env=self.env, check=True,
                           capture_output=True, timeout=60)
        self.commit = subprocess.run(["git", "-C", str(up), "rev-parse", "HEAD"], env=self.env,
                                     capture_output=True, text=True, check=True).stdout.strip()
        p = subprocess.run(["bash", str(here / "tools" / "sync.sh"), str(up)], env=self.env,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_no_broken_local_image_links(self):
        broken = []
        for md in sorted(self.kb.rglob("*.md")):
            for t in image_targets(md.read_text(encoding="utf-8")):
                if not is_remote(t) and not (md.parent / local_part(t)).exists():
                    broken.append(f"{md.relative_to(self.kb)}: {t}")
        self.assertEqual(broken, [], f"{len(broken)} 处图片链接指向知识库里不存在的文件")

    def test_relative_links_rewritten_to_pinned_raw(self):
        prefix = f"{RAW}{UPSTREAM}/{self.commit}/"
        missing = []
        for rel, paths in sorted(self.expected.items()):
            text = (self.kb / rel).read_text(encoding="utf-8")
            got = {local_part(t[len(prefix):]) for t in image_targets(text) if t.startswith(prefix)}
            missing += [f"{rel}: {p}" for p in sorted(paths - got)]
        self.assertEqual(missing, [], f"{len(missing)} 处没改写成 {prefix}<路径>")


if __name__ == "__main__":
    unittest.main()
