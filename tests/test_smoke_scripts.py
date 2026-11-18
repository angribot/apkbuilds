"""Executable POSIX-sh checks for the package smoke tests."""

import os
import pathlib
import signal
import stat
import subprocess
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SMOKE_TESTS = sorted((ROOT / "scripts").glob("test-*.sh"))


def write_executable(path, body):
    path.write_text(textwrap.dedent(body).lstrip())
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class SmokeScriptTest(unittest.TestCase):
    def test_every_smoke_script_is_registered_for_a_package_origin(self):
        completed = subprocess.run(
            ["sh", "-eu", "-c",
             '. scripts/lib.sh; for origin in $(all_origins); do smoke_script "$origin"; done'],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            {str(path.relative_to(ROOT)) for path in SMOKE_TESTS},
            set(completed.stdout.splitlines()),
        )

    def test_every_smoke_script_is_an_executable_posix_shell_script(self):
        self.assertTrue(SMOKE_TESTS)
        for path in SMOKE_TESTS:
            with self.subTest(script=path.name):
                self.assertEqual(path.stat().st_mode & 0o111, 0o111)
                completed = subprocess.run(
                    ["sh", "-n", str(path)], capture_output=True, text=True
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)


class GnupgSmokeCleanupTest(unittest.TestCase):
    """gpg autostarts daemons that unlink their own sockets while exiting.

    When that unlink races the smoke test's `rm -rf` of the homedir, BusyBox
    `rm` reports the vanished socket and fails an otherwise passing smoke test.
    """

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        self.agent_pid = self.root / "agent.pid"
        self.agent_log = self.root / "agent.log"
        self.addCleanup(self.kill_agent)

    def kill_agent(self):
        if self.agent_pid.exists():
            try:
                os.kill(int(self.agent_pid.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_homedir_is_removed_only_after_the_agent_releases_its_socket(self):
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        tmp = self.root / "tmp"
        tmp.mkdir()
        # Like gpg-agent, the fake agent exits asynchronously when stopped and
        # unlinks its socket on the way out.
        write_executable(
            fake_bin / "gpg",
            r'''
            #!/bin/sh
            set -eu
            if [ "$1" = --version ]; then
              echo 'gpg (GnuPG) 9.9.9'
              exit 0
            fi
            while [ "$1" != --homedir ]; do shift; done
            socket=$2/S.gpg-agent
            [ ! -e "$socket" ] || exit 0
            : > "$socket"
            sh -c '
              trap "sleep 0.3; rm \"\$1\" && echo removed; exit" TERM
              while :; do sleep 0.05; done
            ' fake-agent "$socket" </dev/null >>"$FAKE_AGENT_LOG" 2>&1 &
            echo "$!" > "$FAKE_AGENT_PID"
            ''',
        )
        # Like `gpgconf --kill`, return before the daemons have exited.
        write_executable(
            fake_bin / "gpgconf",
            r'''
            #!/bin/sh
            [ ! -f "$FAKE_AGENT_PID" ] || kill "$(cat "$FAKE_AGENT_PID")"
            ''',
        )
        env = {
            **os.environ,
            "FAKE_AGENT_LOG": str(self.agent_log),
            "FAKE_AGENT_PID": str(self.agent_pid),
            "PATH": os.pathsep.join([str(fake_bin), os.environ["PATH"]]),
            "TMPDIR": str(tmp),
        }

        completed = subprocess.run(
            ["sh", str(ROOT / "scripts/test-package.sh"), "9.9.9"],
            env=env, capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(list(tmp.iterdir()), [])
        self.assertEqual(self.agent_log.read_text(), "removed\n")


if __name__ == "__main__":
    unittest.main()
