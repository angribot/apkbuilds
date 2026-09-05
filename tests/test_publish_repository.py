import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/publish-repository.sh"


class PublishRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = self.root / "pages"
        self.snapshot.mkdir()
        self.remote = self.root / "remote.git"
        self.keys = self.root / "runner temp"
        self.keys.mkdir()
        self.env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "RUNNER_TEMP": str(self.keys),
            "PAGES_DEPLOY_KEY": "fake-publication-secret",
        }
        self.git(self.root, "init", "--bare", str(self.remote))
        self.git(self.snapshot, "init", "--initial-branch=gh-pages")
        self.git(self.snapshot, "config", "user.name", "Test")
        self.git(self.snapshot, "config", "user.email", "test@example.com")
        (self.snapshot / "stale.apk").write_text("old package")
        self.git(self.snapshot, "add", ".")
        self.git(self.snapshot, "commit", "-m", "old snapshot")
        (self.snapshot / ".nojekyll").touch()
        self.git(self.snapshot, "add", ".")
        self.git(self.snapshot, "commit", "-m", "second old commit")
        self.git(self.snapshot, "push", str(self.remote), "gh-pages")
        self.previous = self.git(self.remote, "rev-parse", "gh-pages")
        (self.snapshot / "stale.apk").unlink()
        package = self.snapshot / "edge/x86_64/example.apk"
        package.parent.mkdir(parents=True)
        package.write_bytes(b"new package\x00\xff")
        self.expected = {
            ".nojekyll": b"",
            "edge/x86_64/example.apk": package.read_bytes(),
        }

    def git(self, directory, *args):
        return subprocess.run(
            ["git", "-C", str(directory), *args],
            env=self.env, check=True, capture_output=True,
        ).stdout.decode().strip()

    def publish(self):
        result = subprocess.run(
            [str(SCRIPT), str(self.snapshot), "source-revision", str(self.remote)],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(list(self.keys.iterdir()), [])
        self.assertNotIn("fake-publication-secret", result.stdout + result.stderr)
        return result

    def test_replaces_history_and_exact_snapshot(self):
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.remote, "rev-list", "--count", "gh-pages"), "1")
        self.assertEqual(self.git(self.remote, "log", "-1", "--format=%P", "gh-pages"), "")
        self.assertEqual(
            self.git(self.remote, "log", "-1", "--format=%s", "gh-pages"),
            "Publish source-revision",
        )
        paths = self.git(self.remote, "ls-tree", "-r", "--name-only", "gh-pages").splitlines()
        self.assertEqual(set(paths), set(self.expected))
        for path, content in self.expected.items():
            actual = subprocess.run(
                ["git", "-C", str(self.remote), "show", f"gh-pages:{path}"],
                env=self.env, check=True, capture_output=True,
            ).stdout
            self.assertEqual(actual, content)

    def test_rejected_push_preserves_remote(self):
        hook = self.remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\necho 'publication rejected' >&2\nexit 1\n")
        hook.chmod(0o755)
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("publish stage=push", result.stderr)
        self.assertIn("publication rejected", result.stderr)
        self.assertEqual(self.git(self.remote, "rev-parse", "gh-pages"), self.previous)

    def test_missing_credential_cleans_created_key(self):
        self.env.pop("PAGES_DEPLOY_KEY")
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("publish stage=credentials", result.stderr)
        self.assertEqual(self.git(self.remote, "rev-parse", "gh-pages"), self.previous)


if __name__ == "__main__":
    unittest.main()
