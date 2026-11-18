"""Executable POSIX-sh checks for the package smoke tests."""

import os
import pathlib
import shutil
import signal
import subprocess
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SMOKE_TESTS = sorted((ROOT / "scripts").glob("test-*.sh"))


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
    A fake agent checks the ordering that prevents the race: the homedir is
    removed only after the agent has released its socket.
    """

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        self.agent_pid = self.root / "agent.pid"
        self.agent_log = self.root / "agent.log"
        self.homedir_record = self.root / "homedir"
        self.addCleanup(self.stop_fake_gnupg)

    def stop_fake_gnupg(self):
        if self.agent_pid.exists():
            try:
                os.kill(int(self.agent_pid.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.homedir_record.exists():
            shutil.rmtree(self.homedir_record.read_text().strip(),
                          ignore_errors=True)

    def test_homedir_is_removed_only_after_the_agent_releases_its_socket(self):
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        fakes = {
            # Like gpg-agent, the fake agent exits asynchronously when stopped
            # and unlinks its socket on the way out. It logs before unlinking,
            # so the log is complete once the socket is gone; an rm error
            # appended after the marker means someone else removed the socket.
            "gpg": r'''
                #!/bin/sh
                set -eu
                if [ "$1" = --version ]; then
                  echo 'gpg (GnuPG) 9.9.9'
                  exit 0
                fi
                while [ "$1" != --homedir ]; do shift; done
                socket=$2/S.gpg-agent
                [ ! -e "$socket" ] || exit 0
                printf '%s\n' "$2" > "$FAKE_GPG_HOMEDIR"
                : > "$socket"
                sh -c '
                  trap "sleep 0.3; echo unlinking; rm \"\$1\"; exit" TERM
                  while :; do sleep 0.05; done
                ' fake-agent "$socket" </dev/null >>"$FAKE_AGENT_LOG" 2>&1 &
                echo "$!" > "$FAKE_AGENT_PID"
            ''',
            # Like `gpgconf --kill`, return before the daemons have exited.
            "gpgconf": r'''
                #!/bin/sh
                [ ! -f "$FAKE_AGENT_PID" ] || kill "$(cat "$FAKE_AGENT_PID")"
            ''',
        }
        for name, body in fakes.items():
            fake = fake_bin / name
            fake.write_text(textwrap.dedent(body).lstrip())
            fake.chmod(0o755)
        env = {
            **os.environ,
            "FAKE_AGENT_LOG": str(self.agent_log),
            "FAKE_AGENT_PID": str(self.agent_pid),
            "FAKE_GPG_HOMEDIR": str(self.homedir_record),
            "PATH": os.pathsep.join([str(fake_bin), os.environ["PATH"]]),
        }

        completed = subprocess.run(
            ["sh", str(ROOT / "scripts/test-package.sh"), "9.9.9"],
            env=env, capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        homedir = pathlib.Path(self.homedir_record.read_text().strip())
        self.assertFalse(homedir.exists())
        self.assertEqual(self.agent_log.read_text(), "unlinking\n")


if __name__ == "__main__":
    unittest.main()
