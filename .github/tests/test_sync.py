# tools/sync.sh 的测试（审计 2026-11-18 #188 的空集、非 git 源两条）。
#
# 跑法（在仓库根）：
#   python3 -I -B -m unittest discover -s .github/tests
# （不加 -t .：.github 不是合法的包名，加了 unittest 会报 Start directory is not importable。）
#
# 只用标准库、bash 和 git，不联网：假的上游 git 仓库在临时目录里现造。sync.sh 会改
# package/kb 和 UPSTREAM_COMMIT，所以先把 tools/sync.sh 和现有知识库拷进临时目录，
# 跑拷贝，绝不动仓库本身。
# 放 .github/tests/ 而不是 tools/：和别的包仓库一个跑法；release.yml 的 folder 是 package，
# .github 和 tools 都不进包。

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
KB = pathlib.Path("package") / "kb" / "shorinwiki"


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class Sync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
                    "HOME": str(self.base), "TMPDIR": str(self.base),
                    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                    # 临时目录外面就算有 git 仓库，也不让 git 往上找到它。
                    "GIT_CEILING_DIRECTORIES": str(self.base),
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        # 包仓库的拷贝：tools/sync.sh、现有知识库、UPSTREAM_COMMIT。
        self.here = self.base / "here"
        (self.here / "tools").mkdir(parents=True)
        shutil.copy2(REPO / "tools" / "sync.sh", self.here / "tools" / "sync.sh")
        shutil.copytree(REPO / KB, self.here / KB)
        (self.here / "UPSTREAM_COMMIT").write_text("0" * 40 + "\n")
        self.kb = self.here / KB

    def upstream(self, files, git=True):
        up = self.base / "up"
        for rel, content in files.items():
            p = up / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        if git:
            for cmd in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
                subprocess.run(["git", "-C", str(up), *cmd], env=self.env, check=True,
                               capture_output=True, timeout=30)
        return up

    def sync(self, src):
        return subprocess.run(["bash", str(self.here / "tools" / "sync.sh"), str(src)],
                              env=self.env, capture_output=True, text=True, timeout=60)

    def current_wiki(self):
        """照现有知识库还原出上游 wiki/ 的 Markdown（kb.toml 不是上游的）。"""
        return {f"wiki/{p.relative_to(self.kb)}": p.read_text(encoding="utf-8")
                for p in self.kb.rglob("*.md")}

    # 审计 #188：上游 wiki/ 还在、但一个 .md 都没有（比如 Markdown 挪走了）时，sync.sh 照样
    # 把知识库清得只剩 kb.toml、印 changed、退出码 0；update.yml 见 changed 就自动发版，
    # 发出一个空知识库。应失败退出、知识库和 UPSTREAM_COMMIT 都不动。
    def test_empty_upstream_refused(self):
        before, commit = snapshot(self.kb), (self.here / "UPSTREAM_COMMIT").read_text()
        p = self.sync(self.upstream({"wiki/readme.txt": "moved\n"}))
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("changed", p.stdout.split())
        self.assertEqual(snapshot(self.kb), before, "知识库被清掉了")
        self.assertEqual((self.here / "UPSTREAM_COMMIT").read_text(), commit)

    # 审计 #188：先 rm -rf 知识库、换上新内容、印 changed，最后才 git rev-parse；源不是 git
    # 仓库时 rev-parse 失败（退出码 128），留下换了一半的知识库和 0 字节的 UPSTREAM_COMMIT。
    # 应先取提交号再动知识库：失败时知识库、UPSTREAM_COMMIT 都不变。
    def test_non_git_source_leaves_kb_untouched(self):
        before, commit = snapshot(self.kb), (self.here / "UPSTREAM_COMMIT").read_text()
        p = self.sync(self.upstream({"wiki/a.md": "# a\n"}, git=False))
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(snapshot(self.kb), before, "知识库被换掉了一半")
        self.assertEqual((self.here / "UPSTREAM_COMMIT").read_text(), commit,
                         "UPSTREAM_COMMIT 被截断了")

    # 防改坏（现在就绿）：正常的上游（现有全部文档 + 一篇改动）照常同步、记下提交号。
    def test_normal_upstream_syncs(self):
        files = self.current_wiki()
        files["wiki/new-page.md"] = "# new\n"
        up = self.upstream(files)
        p = self.sync(up)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.split(), ["changed"])
        self.assertEqual((self.kb / "new-page.md").read_text(), "# new\n")
        self.assertTrue((self.kb / "kb.toml").is_file())
        head = subprocess.run(["git", "-C", str(up), "rev-parse", "HEAD"], env=self.env,
                              capture_output=True, text=True, check=True).stdout
        self.assertEqual((self.here / "UPSTREAM_COMMIT").read_text(), head)


if __name__ == "__main__":
    unittest.main()
