"""Exercise real Git publication and failure recovery in disposable repositories."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")


@unittest.skipUnless(GIT, "Git is required for release transaction fixtures")
class ReleaseTransaction(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zcall-omarchy-release-")
        self.directory = Path(self.temporary.name)
        self.checkout = self.directory / "checkout"
        self.checkout.mkdir()
        self.remote = self.directory / "remote.git"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(HOME=str(self.directory), GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
        self.git("init", "--quiet", "--initial-branch=main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        subprocess.run([GIT, "init", "--bare", "--quiet", str(self.remote)],
                       env=self.env, check=True, capture_output=True)
        self.git("remote", "add", "origin", str(self.remote))
        (self.checkout / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/bump.py", self.checkout / "scripts/bump.py")
        (self.checkout / "scripts/check.py").write_text(
            "import os,sys\nfrom pathlib import Path\n"
            "if os.environ.get('FIXTURE_FAIL_CHECK') or os.environ.get('FIXTURE_FAIL_PUSH'):\n"
            " Path('unrelated-note.txt').write_text('keep this note')\n"
            "if os.environ.get('FIXTURE_FAIL_CHECK'): sys.exit(7)\n")
        (self.checkout / "VERSION").write_text("0.1.0\n")
        (self.checkout / "manifest.json").write_text(json.dumps(
            {"id": "lightjunction.zcall", "version": "0.1.0"}, indent=2) + "\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Initial fixture")
        self.git("push", "--quiet", "-u", "origin", "main")
        self.start = self.git("rev-parse", "HEAD")
        self.before = {name: (self.checkout / name).read_bytes()
                       for name in ("VERSION", "manifest.json")}
        self.commands = self.directory / "bin"
        self.commands.mkdir()
        wrapper = self.commands / "git"
        wrapper.write_text("#!" + sys.executable + "\n" +
            "import os,subprocess,sys\n"
            "mode=os.environ.get('FIXTURE_FAIL_PUSH')\n"
            "if sys.argv[1:2]==['push'] and mode:\n"
            " if mode=='after': subprocess.run([" + repr(GIT) + ",*sys.argv[1:]],check=True)\n"
            " sys.exit(9)\n"
            "os.execv(" + repr(GIT) + ",[" + repr(GIT) + ",*sys.argv[1:]])\n")
        wrapper.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args):
        result = subprocess.run([GIT, *args], cwd=self.checkout, env=self.env,
                                text=True, capture_output=True, check=True)
        return result.stdout.strip()

    def bump(self, version="patch", **flags):
        env = {**self.env, **flags}
        env["PATH"] = str(self.commands) + os.pathsep + env.get("PATH", "")
        return subprocess.run([sys.executable, "scripts/bump.py", version, "--release"],
                              cwd=self.checkout, env=env, text=True, capture_output=True, timeout=20)

    def assert_unpublished_rollback(self):
        self.assertEqual(self.git("rev-parse", "HEAD"), self.start)
        self.assertEqual(self.git("tag", "--list", "v0.1.1"), "")
        self.assertEqual(self.git("ls-remote", "--tags", "origin", "refs/tags/v0.1.1"), "")
        self.assertEqual({name: (self.checkout / name).read_bytes() for name in self.before}, self.before)
        self.assertEqual((self.checkout / "unrelated-note.txt").read_text(), "keep this note")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_failed_check_restores_only_owned_version_files(self):
        result = self.bump(FIXTURE_FAIL_CHECK="1")
        self.assertNotEqual(result.returncode, 0)
        self.assert_unpublished_rollback()

    def test_confirmed_failed_push_removes_only_its_local_commit_and_tag(self):
        result = self.bump(FIXTURE_FAIL_PUSH="before")
        self.assertNotEqual(result.returncode, 0)
        self.assert_unpublished_rollback()

    def test_remote_publication_is_never_rolled_back_after_lost_acknowledgement(self):
        result = self.bump(FIXTURE_FAIL_PUSH="after")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote tag exists", result.stderr)
        self.assertNotEqual(self.git("rev-parse", "HEAD"), self.start)
        self.assertEqual((self.checkout / "VERSION").read_text(), "0.1.1\n")
        self.assertTrue(self.git("ls-remote", "--tags", "origin", "refs/tags/v0.1.1"))
        self.assertEqual(self.git("rev-parse", "v0.1.1^{commit}"), self.git("rev-parse", "HEAD"))

    def test_successful_atomic_release_and_duplicate_tag_refusal(self):
        result = self.bump()
        self.assertEqual(result.returncode, 0, result.stderr)
        published = self.git("rev-parse", "HEAD")
        self.assertIn(published, self.git("ls-remote", "origin", "refs/heads/main"))
        original_tag = self.git("rev-parse", "refs/tags/v0.1.1")
        repeated = self.bump("0.1.1")
        self.assertNotEqual(repeated.returncode, 0)
        self.assertEqual(self.git("rev-parse", "refs/tags/v0.1.1"), original_tag)
        self.assertEqual(self.git("rev-parse", "HEAD"), published)


if __name__ == "__main__":
    unittest.main(verbosity=2)
