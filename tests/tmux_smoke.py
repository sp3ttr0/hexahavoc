"""Exercise containment and ownership with real tmux and inert pane commands."""
import os
from pathlib import Path
import pty
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest


LAUNCHER = Path(__file__).resolve().parents[1] / 'hexahavoc.sh'


class TmuxSmokeTest(unittest.TestCase):
    def setUp(self):
        tmux = shutil.which('tmux')
        self.assertIsNotNone(tmux, 'Install tmux before running the smoke test')
        directory = tempfile.TemporaryDirectory(prefix='hh-tmux-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.tmux = [tmux, '-f', '/dev/null', '-S', str(self.root / 'sock')]
        self.addCleanup(self.server, 'kill-server', check=False)

        self.launcher = self.root / 'launcher.sh'
        self.launcher.write_text(LAUNCHER.read_text().replace(
            "(( EUID == 0 )) || fail 'Run this script as root.'",
            ': # root guard bypassed for isolated tests',
        ))
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        stubs = {
            'uname': 'echo Linux',
            'ip': 'exit 0',
            'mitm6': 'exec sleep 120',
            'impacket-ntlmrelayx': 'exec sleep 120',
            'tmux': (
                '# Simulate detaching at the client boundary.\n'
                'if [ "$1" = attach-session ]; then exit 0; fi\n'
                f'exec {shlex.join(self.tmux)} "$@"'
            ),
        }
        for name, body in stubs.items():
            path = bin_dir / name
            path.write_text(f'#!/bin/sh\n{body}\n')
            path.chmod(0o700)
        self.env = dict(os.environ, PATH=f'{bin_dir}{os.pathsep}{os.environ["PATH"]}')
        self.env.pop('TMUX', None)

    def server(self, *args, check=True):
        return subprocess.run(
            [*self.tmux, *args], cwd=self.root, capture_output=True, text=True,
            timeout=5, check=check,
        )

    def launch(self, *args, check=True):
        master, slave = pty.openpty()
        try:
            result = subprocess.run(
                ['/bin/bash', str(self.launcher), *args], cwd=self.root, env=self.env,
                stdin=slave, stdout=slave, stderr=subprocess.PIPE, text=True, timeout=12,
            )
            if check:
                self.assertEqual(result.returncode, 0, result.stderr)
            return result
        finally:
            os.close(slave)
            os.close(master)

    def wait_for_shutdown(self, target):
        deadline = time.monotonic() + 7
        while time.monotonic() < deadline:
            if self.server('has-session', '-t', target, check=False).returncode:
                return
            time.sleep(0.05)
        self.fail(f'Timed session {target} stayed up')

    def test_deadline_and_timer_window_loss_stop_only_owned_session(self):
        self.launch('--status')
        unrelated = '=ipv6_dns_takeover_unowned'
        self.server('new-session', '-d', '-s', unrelated[1:], 'sleep 120')
        result = self.launch('--stop', '--session', unrelated[1:], check=False)
        self.assertNotEqual(result.returncode, 0)
        self.server('has-session', '-t', unrelated)

        for event, duration in (('deadline', '6'), ('window removed', '60'),
                                ('timer exited', '60'), ('explicit stop', '60')):
            with self.subTest(event=event):
                self.launch('-s', '-d', 'example.test', '-t', '192.0.2.1',
                            '--duration', duration)
                sessions = self.server(
                    'list-sessions', '-F', '#{session_name} #{session_id} #{@hexahavoc_owned}',
                ).stdout
                owned = [line.split() for line in sessions.splitlines()
                         if line.startswith('ipv6_dns_takeover_example_test ')]
                self.assertEqual(len(owned), 1, sessions)
                _, target, *marker = owned[0]
                self.assertEqual(marker, ['1'], sessions)
                if event == 'window removed':
                    self.server('kill-window', '-t', f'{target}:duration')
                elif event == 'timer exited':
                    timer = f'{target}:duration'
                    self.server('set-option', '-w', '-t', timer, 'remain-on-exit', 'on')
                    self.server('respawn-pane', '-k', '-t', timer, 'exit 1')
                elif event == 'explicit stop':
                    self.launch('--stop', '--session', 'ipv6_dns_takeover_example_test')
                self.wait_for_shutdown(target)
                self.server('has-session', '-t', unrelated)


if __name__ == '__main__':
    unittest.main()
