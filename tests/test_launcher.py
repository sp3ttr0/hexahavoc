"""Offline regression tests. All network tools and tmux are replaced by mocks."""
import json
import os
from pathlib import Path
import pty
import shlex
import subprocess
import tempfile
import threading
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'hexahavoc.sh'


class LauncherTests(unittest.TestCase):
    def run_launcher(self, args, failure='', system='Linux', interactive=True, timer_mode='', existing=False, log_tools=False, sessions=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mockbin = root / 'bin'
            mockbin.mkdir()
            log = root / 'calls.jsonl'
            if existing:
                (root / 'active').touch()
            # Only the root guard is bypassed in the disposable test copy.
            script = root / 'launcher'
            script.write_text(SCRIPT.read_text().replace(
                "(( EUID == 0 )) || fail 'Run this script as root.'", ': # root guard bypassed for offline tests'))
            mock = mockbin / 'mock'
            mock.write_text('''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['MOCK_LOG'], 'a') as f:
    f.write(json.dumps([name] + args) + '\\n')
if name == 'uname':
    print(os.environ['MOCK_SYSTEM'])
elif name == 'sleep' and os.environ.get('MOCK_TIMER_MODE'):
    time.sleep(float(args[0]))
elif name in ('mitm6', 'impacket-ntlmrelayx'):
    print(name + ' stdout')
    print(name + ' stderr', file=sys.stderr)
    sys.exit(int(os.environ.get('MOCK_TOOL_EXIT', '0')))
elif name == 'tmux':
    action = args[0]
    failure = os.environ.get('MOCK_FAILURE', '')
    active = pathlib.Path(os.environ['MOCK_LOG']).parent / 'active'
    if action == 'list-sessions':
        for index, session in enumerate(json.loads(os.environ['MOCK_SESSIONS'])):
            print('$' + str(index + 7) + ' ' + session)
        sys.exit(0)
    if action == 'has-session': sys.exit(0 if active.exists() else 1)
    if action == failure: sys.exit(1)
    if action == 'new-session':
        active.touch()
        if os.environ.get('MOCK_LOG_TOOLS'):
            result = subprocess.run(['/bin/bash', '-c', args[-1]], capture_output=True)
            (active.parent / 'mitm_console').write_bytes(result.stdout)
        print('%1')
    if action == 'kill-session': active.unlink(missing_ok=True)
    if action in ('new-window', 'split-window'):
        if not active.exists(): sys.exit(1)
        if 'duration' in args:
            if failure == 'timer': sys.exit(1)
            if os.environ.get('MOCK_TIMER_MODE'):
                subprocess.Popen(['/bin/bash', '-c', args[-1]], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            if os.environ.get('MOCK_LOG_TOOLS'):
                result = subprocess.run(['/bin/bash', '-c', args[-1]], capture_output=True)
                (active.parent / 'relay_console').write_bytes(result.stdout)
            print('%2')
    if action == 'display-message':
        if not active.exists(): sys.exit(1)
        print('$7' if args[-1] == '#{session_id}' else ('1' if failure == 'dead' else '0'))
    if action == 'attach-session' and os.environ.get('MOCK_TIMER_MODE') == 'attached':
        while active.exists(): time.sleep(0.05)
''')
            mock.chmod(0o755)
            for name in ('uname', 'ip', 'tmux', 'mitm6', 'impacket-ntlmrelayx', 'sleep'):
                (mockbin / name).symlink_to(mock)
            env = dict(os.environ, PATH=str(mockbin) + os.pathsep + os.environ['PATH'],
                       MOCK_LOG=str(log), MOCK_FAILURE=failure, MOCK_SYSTEM=system,
                       MOCK_TIMER_MODE=timer_mode, MOCK_LOG_TOOLS='1' if log_tools else '',
                       MOCK_SESSIONS=json.dumps(sessions))
            env.pop('TMUX', None)
            command = ['/bin/bash', str(script), *args]
            if interactive:
                master, slave = pty.openpty()
                def drain_terminal():
                    try:
                        while os.read(master, 4096):
                            pass
                    except OSError:
                        pass
                reader = threading.Thread(target=drain_terminal, daemon=True)
                reader.start()
                try:
                    process = subprocess.Popen(command, stdin=slave, stdout=slave,
                                               stderr=subprocess.PIPE, cwd=root, env=env)
                    try:
                        _, errors = process.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()
                        raise
                    code = process.returncode
                finally:
                    os.close(slave)
                    reader.join(timeout=1)
                    os.close(master)
            else:
                result = subprocess.run(command, capture_output=True, cwd=root, env=env, timeout=10)
                code, errors = result.returncode, result.stderr
            if timer_mode:
                deadline = time.monotonic() + 6
                while (root / 'active').exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse((root / 'active').exists(), 'Timer did not close the mock session')
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            self.output_created = (root / 'dumps').exists()
            self.run_files = {str(p.relative_to(root)): p.read_text()
                              for p in root.rglob('*.log')}
            self.run_modes = {str(p.relative_to(root)): p.stat().st_mode & 0o777
                              for p in root.rglob('*.log')}
            self.console_output = {p.name: p.read_text() for p in root.glob('*_console')}
            return code, errors.decode(), calls

    def test_argument_errors_precede_external_commands(self):
        for args in (['-d'], ['-z'], ['-d', 'example.com', '-t', '192.0.2.1', 'extra'],
                     ['-d', '-bad.example', '-t', '192.0.2.1'], ['-v', '-s']):
            with self.subTest(args=args):
                code, _, calls = self.run_launcher(args)
                self.assertNotEqual(code, 0)
                self.assertEqual(calls, [])

    def test_help(self):
        code, _, calls = self.run_launcher(['-h'])
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])

    def test_platform_check(self):
        code, error, calls = self.run_launcher(['-d', 'example.com', '-t', '192.0.2.1'], system='Darwin')
        self.assertNotEqual(code, 0)
        self.assertIn('requires Linux', error)
        self.assertEqual(calls, [['uname', '-s']])

    def test_literal_ip_only(self):
        for address in ('host.example.com', '999.1.1.1', 'fe80::1%eth0'):
            code, error, calls = self.run_launcher(['-d', 'example.com', '-t', address])
            self.assertNotEqual(code, 0)
            self.assertIn('literal IPv4 or IPv6', error)
            self.assertFalse(any(c[0] == 'tmux' for c in calls))

    def test_noninteractive_rejected_before_session_creation(self):
        code, error, calls = self.run_launcher(['-d', 'example.com', '-t', '192.0.2.1'], interactive=False)
        self.assertNotEqual(code, 0)
        self.assertIn('interactive terminal', error)
        self.assertFalse(any(c[:2] == ['tmux', 'new-session'] for c in calls))

    def test_quoted_arguments_and_ipv6(self):
        unusual = "output space ' quote; $(false) `false`"
        code, error, calls = self.run_launcher(['-d', 'example.com', '-t', '2001:db8::1', '-l', unusual])
        self.assertEqual(code, 0, error)
        command = next(c[-1] for c in calls if c[:2] == ['tmux', 'split-window'])
        args = shlex.split(command)
        tool_index = args.index('impacket-ntlmrelayx')
        self.assertEqual(args[tool_index:tool_index + 4], ['impacket-ntlmrelayx', '-6', '-t', 'ldaps://[2001:db8::1]'])
        self.assertEqual(Path(args[-1]).parent.name, unusual)
        self.assertEqual(Path(args[tool_index - 1]).name, 'ntlmrelayx.log')
        self.assertEqual(str(Path(args[tool_index - 1]).parent), args[-1])
        self.assertFalse(any(c[:2] == ['tmux', 'kill-session'] for c in calls))
        # Actually parse the generated command in Bash with a harmless function,
        # verifying shell characters remain literal and no real tool is invoked.
        wrapper = 'exec() { printf "%s\\0" "$@"; }; ' + command
        result = subprocess.run(['/bin/bash', '-c', wrapper], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.decode().split('\0')[:-1], args[1:])

    def test_failures_cleanup_owned_session(self):
        for failure in ('split-window', 'dead', 'display-message', 'attach-session'):
            with self.subTest(failure=failure):
                code, _, calls = self.run_launcher(['-d', 'example.com', '-t', '192.0.2.1'], failure=failure)
                self.assertNotEqual(code, 0)
                self.assertTrue(any(c[:2] == ['tmux', 'kill-session'] for c in calls))

    def test_failed_creation_does_not_kill_unowned_session(self):
        code, _, calls = self.run_launcher(['-d', 'example.com', '-t', '192.0.2.1'], failure='new-session')
        self.assertNotEqual(code, 0)
        self.assertFalse(any(c[:2] == ['tmux', 'kill-session'] for c in calls))

    def test_invalid_duration(self):
        for extra in (['--duration'], ['--duration='], ['--duration', '0'],
                      ['--duration', '-1'], ['--duration', '1.5'],
                      ['--duration', 'abc'], ['--duration', '2147483648'],
                      ['--duration', '99999999999999999999999']):
            with self.subTest(extra=extra):
                code, _, calls = self.run_launcher(['-d', 'example.com', '-t', '192.0.2.1', *extra])
                self.assertNotEqual(code, 0)
                self.assertEqual(calls, [])

    def test_duration_closes_session(self):
        for mode, flag in (('attached', ['--duration', '4']), ('detached', ['--duration=4']),
                           ('startup', ['--duration', '1'])):
            with self.subTest(mode=mode):
                code, error, calls = self.run_launcher(
                    ['-d', 'example.com', '-t', '192.0.2.1', *flag], timer_mode=mode)
                self.assertEqual(code, 0, error)
                self.assertEqual([c for c in calls if c[:2] == ['tmux', 'kill-session']],
                                 [['tmux', 'kill-session', '-t', '$7']])
                if mode == 'detached':
                    self.assertTrue(any(c[:2] == ['tmux', 'attach-session'] for c in calls))

    def test_timer_creation_failure_cleans_up(self):
        code, _, calls = self.run_launcher(
            ['--duration', '10', '-d', 'example.com', '-t', '192.0.2.1'], failure='timer')
        self.assertNotEqual(code, 0)
        self.assertIn(['tmux', 'kill-session', '-t', '$7'], calls)

    def test_existing_session_is_not_given_a_timer(self):
        code, error, calls = self.run_launcher(
            ['-d', 'example.com', '-t', '192.0.2.1', '--duration=10'], existing=True)
        self.assertNotEqual(code, 0)
        self.assertIn('only to a new session', error)
        self.assertFalse(any(c[:2] == ['tmux', 'kill-session'] for c in calls))
        self.assertFalse(any(c[:2] == ['tmux', 'split-window'] for c in calls))

    def test_separate_timestamped_logs_and_console_output(self):
        code, error, _ = self.run_launcher(
            ['-d', 'example.com', '-t', '192.0.2.1', '-l', "logs with ' spaces"], log_tools=True)
        self.assertEqual(code, 0, error)
        self.assertEqual(len(self.run_files), 2)
        parents = {str(Path(p).parent) for p in self.run_files}
        self.assertEqual(len(parents), 1)
        self.assertRegex(Path(next(iter(parents))).name,
                         r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_[A-Za-z0-9]+$')
        for path, content in self.run_files.items():
            name = 'mitm6' if Path(path).name == 'mitm6.log' else 'impacket-ntlmrelayx'
            self.assertEqual(set(content.splitlines()), {name + ' stdout', name + ' stderr'})
            console = 'mitm_console' if name == 'mitm6' else 'relay_console'
            self.assertEqual(content, self.console_output[console])
            self.assertEqual(self.run_modes[path], 0o600)

    def test_tools_start_side_by_side(self):
        code, error, calls = self.run_launcher(['-d', 'example.com', '-t', '192.0.2.1'])
        self.assertEqual(code, 0, error)
        split = next(c for c in calls if c[:2] == ['tmux', 'split-window'])
        self.assertIn('-h', split)
        self.assertIn('-d', split)
        self.assertEqual(split[split.index('-t') + 1], '%1')
        self.assertFalse(any(c[:2] == ['tmux', 'new-window'] for c in calls))

    def test_logging_preserves_tool_failure(self):
        # Execute the actual logging function with a harmless failing shell tool.
        source = SCRIPT.read_text()
        functions = source[source.index('shell_command() {'):source.index('log "Creating session')]
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'failure.log')
            script = functions + '\ncommand=$(logged_command "$1" /bin/bash -c \'echo diagnostic >&2; exit 23\')\nexec /bin/bash -c "$command"'
            result = subprocess.run(['/bin/bash', '-c', script, 'test', path], capture_output=True)
            self.assertEqual(result.returncode, 23)
            self.assertEqual(Path(path).read_text(), 'diagnostic\n')
            self.assertEqual(result.stdout, b'diagnostic\n')

    def test_preflight_without_targets_is_read_only(self):
        code, error, calls = self.run_launcher(['--check'], interactive=False)
        self.assertEqual(code, 0, error)
        self.assertFalse(self.output_created)
        self.assertFalse(any(c[0] in ('tmux', 'mitm6', 'impacket-ntlmrelayx') for c in calls))

    def test_preflight_validates_supplied_settings(self):
        for settings in (['-t', 'not-an-ip'], ['-d', '-bad.example'], ['-l', 'launcher']):
            with self.subTest(settings=settings):
                code, _, calls = self.run_launcher(['--check', *settings], interactive=False)
                self.assertNotEqual(code, 0)
                self.assertFalse(self.output_created)
                self.assertFalse(any(c[0] == 'tmux' for c in calls))

    def test_session_controls_without_targets(self):
        session = 'ipv6_dns_takeover_example_com'
        for action in ('status', 'attach', 'stop'):
            with self.subTest(action=action):
                code, error, calls = self.run_launcher(['--' + action], sessions=[session])
                self.assertEqual(code, 0, error)
                self.assertFalse(self.output_created)
                self.assertTrue(all(c[0] == 'tmux' for c in calls))
                if action != 'status':
                    expected = 'attach-session' if action == 'attach' else 'kill-session'
                    self.assertIn(['tmux', expected, '-t', '$7'], calls)

    def test_multiple_sessions_require_selection(self):
        sessions = ['ipv6_dns_takeover_one_com', 'ipv6_dns_takeover_two_com', 'unrelated']
        code, error, calls = self.run_launcher(['--stop'], sessions=sessions)
        self.assertNotEqual(code, 0)
        self.assertIn('Multiple sessions', error)
        self.assertFalse(any(c[:2] == ['tmux', 'kill-session'] for c in calls))
        code, error, calls = self.run_launcher(['--stop', '--session', sessions[1]], sessions=sessions)
        self.assertEqual(code, 0, error)
        self.assertIn(['tmux', 'kill-session', '-t', '$8'], calls)

    def test_session_controls_reject_unrelated_sessions_and_conflicts(self):
        for args in (['--attach'], ['--stop', '--session=unrelated'],
                     ['--stop', '--check'], ['--status', '-d', 'example.com']):
            with self.subTest(args=args):
                code, _, calls = self.run_launcher(args, sessions=['unrelated'])
                self.assertNotEqual(code, 0)
                self.assertFalse(any(c[:2] == ['tmux', 'kill-session'] for c in calls))
        code, error, _ = self.run_launcher(['--status'], sessions=['unrelated'], interactive=False)
        self.assertEqual(code, 0, error)


if __name__ == '__main__':
    unittest.main()
