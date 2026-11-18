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


RAW = "https://raw.githubusercontent.com/SHORiN-KiWATA/Shorin-ArchLinux-Guide/"


class PinnedCommit(Sync):
    # 审计 #187 返工（合并人要求）：图片链接钉在上游最新提交上，上游任何一次提交（哪怕没碰
    # wiki）都会让改写出来的地址变、判成 changed、自动发一版。比较时要把钉的提交号归一化掉，
    # 另用仓库根的 UPSTREAM_IMAGES（每行 `<blob 哈希> <上游路径>`）看被引用的图片变没变。
    # unchanged 时知识库、UPSTREAM_COMMIT、UPSTREAM_IMAGES 都不动。
    PAGE = "# 页面\n\n![图](../pictures/a.png)\n"
    # 只借 Sync 的准备和帮手；它的三条测试不在这个类下面再跑一遍。
    test_empty_upstream_refused = None
    test_non_git_source_leaves_kb_untouched = None
    test_normal_upstream_syncs = None

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], env=self.env, check=True,
                              capture_output=True, text=True, timeout=30).stdout.strip()

    def commit_files(self, up, files):
        for rel, content in files.items():
            p = up / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_text(content, encoding="utf-8")
        self.git(up, "add", "-A")
        self.git(up, "commit", "-q", "-m", "next")
        return self.git(up, "rev-parse", "HEAD")

    def first_upstream(self):
        up = self.upstream({"wiki/guide/page.md": self.PAGE, "README.md": "readme\n"})
        return up, self.commit_files(up, {"wiki/pictures/a.png": b"PNG-1"})

    def state(self):
        images = self.here / "UPSTREAM_IMAGES"
        return (snapshot(self.kb), (self.here / "UPSTREAM_COMMIT").read_text(),
                images.read_text() if images.exists() else None)

    def sync_ok(self, src, expect):
        p = self.sync(src)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.split(), [expect], p.stderr)

    def page_links(self):
        return (self.kb / "guide" / "page.md").read_text(encoding="utf-8")

    def check_unrelated_commit_unchanged(self, clone):
        up, first = self.first_upstream()
        src = clone(up)
        self.sync_ok(src, "changed")
        self.assertIn(f"{RAW}{first}/wiki/pictures/a.png", self.page_links())
        blob = self.git(up, "rev-parse", "HEAD:wiki/pictures/a.png")
        self.assertEqual((self.here / "UPSTREAM_IMAGES").read_text(),
                         f"{blob} wiki/pictures/a.png\n")
        before = self.state()
        self.commit_files(up, {"README.md": "readme 2\n"})
        self.sync_ok(clone(up), "unchanged")
        self.assertEqual(self.state(), before, "上游没动 wiki 和图片，三样都不该变")
        self.assertIn(f"{RAW}{first}/wiki/pictures/a.png", self.page_links())

    def test_unrelated_upstream_commit_is_unchanged(self):
        self.check_unrelated_commit_unchanged(lambda up: up)

    # update.yml 用 git clone --depth 1：浅克隆里也要取得到 blob 哈希。
    def test_unrelated_commit_unchanged_with_shallow_clone(self):
        n = [0]

        def clone(up):
            n[0] += 1
            dst = self.base / f"clone{n[0]}"
            subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{up}", str(dst)],
                           env=self.env, check=True, capture_output=True, timeout=30)
            return dst
        self.check_unrelated_commit_unchanged(clone)

    def test_replaced_image_is_changed(self):
        up, first = self.first_upstream()
        self.sync_ok(up, "changed")
        old_blob = self.git(up, "rev-parse", "HEAD:wiki/pictures/a.png")
        second = self.commit_files(up, {"wiki/pictures/a.png": b"PNG-2"})
        self.sync_ok(up, "changed")
        self.assertIn(f"{RAW}{second}/wiki/pictures/a.png", self.page_links())
        new_blob = self.git(up, "rev-parse", "HEAD:wiki/pictures/a.png")
        self.assertNotEqual(old_blob, new_blob)
        self.assertEqual((self.here / "UPSTREAM_IMAGES").read_text(),
                         f"{new_blob} wiki/pictures/a.png\n")
        self.assertEqual((self.here / "UPSTREAM_COMMIT").read_text(), second + "\n")

    def test_edited_markdown_is_changed(self):
        up, _ = self.first_upstream()
        self.sync_ok(up, "changed")
        second = self.commit_files(up, {"wiki/guide/page.md": self.PAGE + "\n多一行\n"})
        self.sync_ok(up, "changed")
        self.assertIn("多一行", self.page_links())
        self.assertIn(f"{RAW}{second}/wiki/pictures/a.png", self.page_links())
        self.assertEqual((self.here / "UPSTREAM_COMMIT").read_text(), second + "\n")


class SymlinkedMarkdown(Sync):
    # 审计 #188：抄 Markdown 的 cp 不带 -P，跟着符号链接抄：上游放一个指向仓库外文件的
    # .md 链接，那个文件的内容就进了知识库。链接本身也不能进包（核心打包拒收符号链接）。
    # 应跳过链接、在 stderr 说一句，不算失败；别的文档照常同步。
    test_empty_upstream_refused = None
    test_non_git_source_leaves_kb_untouched = None
    test_normal_upstream_syncs = None

    def test_symlinked_markdown_skipped(self):
        secret = self.base / "outside.txt"
        secret.write_text("SECRET-OUTSIDE\n", encoding="utf-8")
        up = self.base / "up"
        (up / "wiki" / "sub").mkdir(parents=True)
        (up / "wiki" / "a.md").write_text("# a\n", encoding="utf-8")
        (up / "wiki" / "leak.md").symlink_to(secret)
        (up / "wiki" / "sub" / "alias.md").symlink_to("../a.md")
        for cmd in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
            subprocess.run(["git", "-C", str(up), *cmd], env=self.env, check=True,
                           capture_output=True, timeout=30)
        p = self.sync(up)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.split(), ["changed"], p.stderr)
        self.assertEqual((self.kb / "a.md").read_text(encoding="utf-8"), "# a\n")
        for rel in ("leak.md", "sub/alias.md"):
            with self.subTest(rel=rel):
                self.assertFalse(os.path.lexists(self.kb / rel), f"{rel} 是符号链接，不该进知识库")
                self.assertIn(rel, p.stderr, "跳过链接要在 stderr 说一句")
        leaked = [str(q) for q in self.kb.rglob("*") if q.is_symlink()
                  or (q.is_file() and b"SECRET-OUTSIDE" in q.read_bytes())]
        self.assertEqual(leaked, [], "仓库外的内容或链接进了知识库")


if __name__ == "__main__":
    unittest.main()
