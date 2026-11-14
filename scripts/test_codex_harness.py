"""Black-box regression tests for codex_harness; never invokes a real model."""
import json
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import signal
import select
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HARNESS = Path(__file__).with_name('codex_harness.py').resolve()

FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
prompt = sys.stdin.read()
model = args[args.index('--model') + 1]
role = {'gpt-6-astra': 'product', 'gpt-6.1-sol': 'developer', 'gpt-6.1-terra': 'tester'}[model]
stage = pathlib.Path(args[args.index('--output-last-message') + 1]).parent.name.split('-', 1)[1]
log = pathlib.Path(os.environ['FAKE_LOG'])
with log.open('a') as f:
    f.write(json.dumps({'role': role, 'stage': stage, 'args': args, 'prompt': prompt, 'pid': os.getpid()}) + '\n')
mode = os.environ.get('FAKE_MODE', '')
if mode in ('stream', 'stream_wait'):
    print(json.dumps({'type':'item.completed','item':{'id':'note','type':'agent_message','text':'LIVE_PROGRESS_MARKER 正在核对页面'}}), flush=True)
    print(json.dumps({'type':'item.completed','item':{'id':'internal','type':'reasoning','text':'INTERNAL_EVENT_MUST_NOT_DISPLAY'}}), flush=True)
    print(json.dumps({'type':'item.started','item':{'id':'cmd','type':'command_execution','command':'inspect source'}}), flush=True)
    print(json.dumps({'type':'item.completed','item':{'id':'cmd','type':'command_execution','exit_code':0,'aggregated_output':'TOOL_RESULT_MARKER'}}), flush=True)
    print('STDERR_MARKER', file=sys.stderr, flush=True)
    if mode == 'stream_wait':
        until = time.monotonic() + 10
        while not pathlib.Path(os.environ['STREAM_RELEASE']).exists() and time.monotonic() < until:
            time.sleep(.05)
schema = json.loads(pathlib.Path(args[args.index('--output-schema') + 1]).read_text())
planning = stage == 'product-plan'
if (mode == 'product_mutates' and role == 'product') or (mode == 'tester_mutates' and role == 'tester'):
    pathlib.Path('tracked.txt').write_text('unauthorized production edit\n')
if mode == 'checkpoints' and stage == 'developer':
    pathlib.Path('tracked.txt').write_text('implemented\n')
if mode == 'checkpoints' and stage == 'tester':
    pathlib.Path('test_added.py').write_text('# independent regression coverage\n')
if mode == 'checkpoint_secret' and stage == 'developer':
    pathlib.Path('credentials.pem').write_text('sensitive fixture\n')
if mode == 'sleep':
    time.sleep(30)
if mode == 'malformed' and role == 'tester':
    result = 'not json'
else:
    criteria = [{'id': 'a', 'status': 'pass', 'evidence': 'checked a'},
                {'id': 'b', 'status': 'pass', 'evidence': 'checked b'}]
    if role == 'tester' and mode == 'missing': criteria.pop()
    if role == 'tester' and mode == 'no_evidence': criteria[0]['evidence'] = ''
    report_role = 'product' if mode == 'tester_impersonates' and role == 'tester' else role
    verdict = 'revise' if planning and mode != 'planner_claims_pass' else 'pass'
    summary, actions = 'done', []
    count = sum(json.loads(line)['stage'] == stage for line in log.read_text().splitlines())
    asks = ((stage == 'developer' and mode in ('developer_question', 'decision_requires_user', 'repeat_question', 'many_questions'))
            or (stage == 'tester' and mode == 'tester_question'))
    if asks and (count == 1 or mode in ('repeat_question', 'many_questions')):
        verdict = 'needs_product'
        summary = 'Should blank names use a default?' + (str(count) if mode == 'many_questions' else '')
        actions = ['Recommend rejecting blanks; alternative: use anonymous.']
    if stage == 'product-decision':
        verdict, summary = 'decided', 'Reject blank names to match existing behavior.'
        actions = ['DECISION: reject blanks and retain the original acceptance criteria.']
        if mode == 'decision_requires_user':
            verdict, summary = 'blocked', 'Requires real account permission; no authority to grant it.'
    if mode == 'authorization_blocked' and stage == 'developer':
        verdict, summary = 'blocked', 'Missing required account permission.'
    result = json.dumps({'role': report_role, 'verdict': verdict, 'summary': summary,
                         'criteria': criteria, 'next_actions': actions})
pathlib.Path(args[args.index('--output-last-message') + 1]).write_text(result)
'''

GATE = r'''import os, pathlib, sys
p = pathlib.Path(os.environ['GATE_LOG'])
n = int(p.read_text()) if p.exists() else 0
p.write_text(str(n + 1))
if os.environ.get('GATE_MUTATE'):
    pathlib.Path('tracked.txt').write_text('changed during verification\n')
if os.environ.get('GATE_FAIL_FIRST') and n == 0:
    print('unique gate failure for feedback', file=sys.stderr)
    sys.exit(1)
'''


class HarnessBlackBoxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.fake = self.base / 'fake-codex'
        self.fake.write_text(FAKE)
        self.fake.chmod(0o755)
        self.log = self.base / 'calls.jsonl'
        self.gate_log = self.base / 'gate-count'
        self.env = dict(os.environ, FAKE_LOG=str(self.log), GATE_LOG=str(self.gate_log))
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        (self.repo / 'gate.py').write_text(GATE)
        (self.repo / 'tracked.txt').write_text('original\n')
        self.task = self.repo / 'task.json'
        self.task.write_text(json.dumps({
            'version': 1, 'id': 'example', 'title': 'Example', 'goal': 'Exercise the workflow',
            'scope': ['tracked.txt'], 'constraints': ['Do not call real services'],
            'acceptance': [{'id': 'a', 'description': 'A'}, {'id': 'b', 'description': 'B'}],
            'gates': [{'id': 'gate', 'argv': [sys.executable, 'gate.py'], 'cwd': '.', 'timeout_seconds': 5}],
            'models': {'product': 'gpt-6-astra', 'developer': 'gpt-6.1-sol', 'tester': 'gpt-6.1-terra'},
        }))
        self.git('add', '.')
        self.git('commit', '-qm', 'initial')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True, text=True).stdout

    def command(self, *args, timeout=20):
        return subprocess.run([sys.executable, str(HARNESS), *map(str, args)], cwd=self.repo,
                              env=self.env, capture_output=True, text=True, timeout=timeout)

    def run_harness(self, *args):
        return self.command('run', '--task', self.task, '--codex-bin', self.fake,
                            '--max-cycles', '1', *args)

    def status(self):
        paths = list((self.repo / '.codex-harness' / 'runs').glob('*/status.json'))
        self.assertEqual(len(paths), 1, paths)
        return json.loads(paths[0].read_text())

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_complete_requires_independent_tester_gate_and_final_product(self):
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.status()['status'], 'complete')
        self.assertEqual([c['role'] for c in self.calls()], ['product', 'developer', 'tester', 'product'])
        self.assertEqual(self.gate_log.read_text(), '1')

    def test_live_output_and_quiet_preserve_reports(self):
        self.env['FAKE_MODE'] = 'stream'
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for text in ['LIVE_PROGRESS_MARKER', 'TOOL_RESULT_MARKER', 'STDERR_MARKER', '交接 pass']:
            self.assertIn(text, result.stdout)
        self.assertNotIn('INTERNAL_EVENT_MUST_NOT_DISPLAY', result.stdout)
        raw = next(Path(self.status()['run_dir']).glob('stages/*product-plan/events.jsonl')).read_text()
        self.assertIn('INTERNAL_EVENT_MUST_NOT_DISPLAY', raw)
        result = self.run_harness('--quiet', '--allow-dirty')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('LIVE_PROGRESS_MARKER', result.stdout)
        self.assertNotIn('TOOL_RESULT_MARKER', result.stdout)

    def test_progress_is_visible_before_agent_exits(self):
        release = self.base / 'release'
        self.env.update(FAKE_MODE='stream_wait', STREAM_RELEASE=str(release))
        command = [sys.executable, str(HARNESS), 'run', '--task', str(self.task),
                   '--codex-bin', str(self.fake), '--max-cycles', '1']
        process = subprocess.Popen(command, cwd=self.repo, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            captured = b''
            deadline = time.monotonic() + 7
            while time.monotonic() < deadline and b'LIVE_PROGRESS_MARKER' not in captured:
                if select.select([process.stdout], [], [], .1)[0]:
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    captured += chunk
            self.assertIn(b'LIVE_PROGRESS_MARKER', captured)
            self.assertIsNone(process.poll())
            self.assertFalse(list((self.repo / '.codex-harness/runs').glob('*/stages/*product-plan/report.json')))
            release.touch()
            output, errors = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, (captured + output + errors).decode())
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)

    def test_live_tail_handles_split_utf8_partial_json_and_terminal_controls(self):
        spec = importlib.util.spec_from_file_location('harness_live_test', HARNESS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        path = self.base / 'stream.jsonl'; path.write_bytes(b'')
        tail = module.LiveTail(path, '产品', True)
        data = json.dumps({'type':'item.completed','item':{'id':'a','type':'agent_message','text':'中文进度'}}, ensure_ascii=False).encode() + b'\n'
        cut = data.index('中'.encode()) + 1
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                with path.open('ab') as f: f.write(data[:cut])
                tail.pump()
                self.assertEqual(output.getvalue(), '')
                with path.open('ab') as f: f.write(data[cut:])
                tail.pump()
                tail.pump(final=True)
            self.assertEqual(output.getvalue().count('中文进度'), 1)
            self.assertEqual(module.console_text('\x1b[2Jhello\x07'), 'hello')
        finally:
            tail.close()

    def test_checkpoints_commit_each_handoff_and_record_accepted_head(self):
        self.git('checkout', '-qb', 'codex/checkpoints')
        self.env['FAKE_MODE'] = 'checkpoints'
        result = self.run_harness('--git-checkpoints')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = self.status()
        self.assertEqual(state['status'], 'complete')
        commits = [e for e in state['history'] if e['event'] == 'git_checkpoint']
        self.assertEqual([e['stage'] for e in commits], ['developer', 'tester'])
        self.assertEqual(commits[0]['files'], ['tracked.txt'])
        self.assertEqual(commits[1]['files'], ['test_added.py'])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD').strip(), '3')
        self.assertEqual(state['accepted_commit'], self.git('rev-parse', 'HEAD').strip())
        self.assertIn('Pending full QA', self.git('log', '-1', '--format=%B'))

    def test_checkpoints_reject_main_and_dirty_baseline(self):
        self.git('branch', '-M', 'main')
        result = self.run_harness('--git-checkpoints')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls())
        self.git('checkout', '-qb', 'codex/checkpoints')
        (self.repo / 'tracked.txt').write_text('existing user work\n')
        result = self.run_harness('--git-checkpoints', '--allow-dirty')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls())
        self.assertEqual(self.git('rev-list', '--count', 'HEAD').strip(), '1')

    def test_checkpoints_reject_secret_artifacts(self):
        self.git('checkout', '-qb', 'codex/checkpoints')
        self.env['FAKE_MODE'] = 'checkpoint_secret'
        result = self.run_harness('--git-checkpoints')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()['status'], 'error')
        self.assertIn('credentials.pem', self.status()['message'])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD').strip(), '1')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')

    def test_failed_gate_keeps_checkpoint_and_resume_preserves_policy(self):
        self.git('checkout', '-qb', 'codex/checkpoints')
        self.env.update(FAKE_MODE='checkpoints', GATE_FAIL_FIRST='1')
        result = self.run_harness('--git-checkpoints')
        self.assertNotEqual(result.returncode, 0)
        state = self.status()
        self.assertEqual(state['status'], 'limit_reached')
        self.assertNotIn('accepted_commit', state)
        count = self.git('rev-list', '--count', 'HEAD')
        result = self.command('resume', '--run-dir', state['run_dir'], '--max-cycles', '1')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.status()['options']['git_checkpoints'])
        self.assertEqual(count, self.git('rev-list', '--count', 'HEAD'))

    def test_invalid_tester_reports_cannot_complete(self):
        for mode in ('malformed', 'missing', 'no_evidence'):
            with self.subTest(mode=mode):
                # Each mode gets a fresh independent run directory and budget.
                if (self.repo / '.codex-harness').exists():
                    import shutil
                    shutil.rmtree(self.repo / '.codex-harness')
                self.env['FAKE_MODE'] = mode
                result = self.run_harness()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotEqual(self.status()['status'], 'complete')

    def test_developer_question_goes_to_product_then_back_to_developer(self):
        self.env['FAKE_MODE'] = 'developer_question'
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([c['stage'] for c in self.calls()], [
            'product-plan', 'developer', 'product-decision', 'developer', 'tester', 'product-review'])
        self.assertIn('DECISION: reject blanks', self.calls()[3]['prompt'])
        self.assertIn('DECISION: reject blanks', self.calls()[4]['prompt'])
        self.assertEqual(len(self.status()['product_decisions']), 1)
        self.assertEqual(self.gate_log.read_text(), '1')

    def test_tester_question_returns_to_tester_without_skipping_gates(self):
        self.env['FAKE_MODE'] = 'tester_question'
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([c['stage'] for c in self.calls()], [
            'product-plan', 'developer', 'tester', 'product-decision', 'tester', 'product-review'])
        self.assertEqual(self.gate_log.read_text(), '1')

    def test_product_cannot_grant_missing_authority(self):
        self.env['FAKE_MODE'] = 'decision_requires_user'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()['status'], 'blocked')
        self.assertEqual(self.status()['product_decisions'][0]['answer']['verdict'], 'blocked')
        self.assertEqual(self.calls()[-1]['stage'], 'product-decision')
        self.assertFalse(self.gate_log.exists())

    def test_explicit_permission_block_does_not_get_auto_approved(self):
        self.env['FAKE_MODE'] = 'authorization_blocked'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()['status'], 'blocked')
        self.assertEqual([c['stage'] for c in self.calls()], ['product-plan', 'developer'])

    def test_repeated_answered_question_stops_instead_of_looping(self):
        self.env['FAKE_MODE'] = 'repeat_question'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()['status'], 'blocked')
        self.assertEqual(sum(c['stage'] == 'product-decision' for c in self.calls()), 1)
        self.assertIsNotNone(self.status()['pending_question'])

    def test_product_question_round_trips_are_bounded(self):
        self.env['FAKE_MODE'] = 'many_questions'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()['status'], 'blocked')
        self.assertEqual(sum(c['stage'] == 'product-decision' for c in self.calls()), 3)

    def test_product_decisions_survive_resume_and_tests_run_again(self):
        self.env['FAKE_MODE'] = 'developer_question'
        self.env['GATE_FAIL_FIRST'] = '1'
        self.run_harness()
        self.assertEqual(self.status()['status'], 'limit_reached')
        run_dir = next((self.repo / '.codex-harness' / 'runs').iterdir())
        result = self.command('resume', '--run-dir', run_dir, '--codex-bin', self.fake, '--max-cycles', '1')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('DECISION: reject blanks', [c for c in self.calls() if c['stage'] == 'developer'][-1]['prompt'])
        self.assertEqual(sum(c['stage'] == 'product-decision' for c in self.calls()), 1)
        self.assertEqual(self.gate_log.read_text(), '2')

    def test_planner_cannot_claim_acceptance_and_skip_development(self):
        self.env['FAKE_MODE'] = 'planner_claims_pass'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()['status'], 'error')
        self.assertEqual([c['role'] for c in self.calls()], ['product'])
        self.assertFalse(self.gate_log.exists())

    def test_product_cannot_implement_production_code(self):
        self.env['FAKE_MODE'] = 'product_mutates'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()['status'], 'error')
        self.assertIn('产品只读', self.status()['message'])
        self.assertEqual([c['role'] for c in self.calls()], ['product'])

    def test_tester_cannot_fix_production_code_then_claim_pass(self):
        self.env['FAKE_MODE'] = 'tester_mutates'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()['status'], 'error')
        self.assertIn('非测试文件', self.status()['message'])
        self.assertEqual([c['role'] for c in self.calls()], ['product', 'developer', 'tester'])
        self.assertFalse(self.gate_log.exists())

    def test_tester_cannot_submit_product_acceptance_report(self):
        self.env['FAKE_MODE'] = 'tester_impersonates'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.status()['status'], 'error')
        self.assertFalse(self.gate_log.exists())

    def test_failed_gate_is_fed_to_next_cycle(self):
        self.env['GATE_FAIL_FIRST'] = '1'
        result = self.command('run', '--task', self.task, '--codex-bin', self.fake, '--max-cycles', '2')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.status()['status'], 'complete')
        self.assertEqual(self.gate_log.read_text(), '2')
        developers = [c for c in self.calls() if c['role'] == 'developer']
        self.assertEqual(len(developers), 2)
        self.assertIn('unique gate failure for feedback', developers[1]['prompt'])

    def test_dirty_worktree_requires_explicit_allowance_and_preserves_changes(self):
        (self.repo / 'tracked.txt').write_text('user changes\n')
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertEqual((self.repo / 'tracked.txt').read_text(), 'user changes\n')
        result = self.run_harness('--allow-dirty')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.repo / 'tracked.txt').read_text(), 'user changes\n')

    def test_dry_run_does_not_call_agents_or_gates(self):
        result = self.run_harness('--dry-run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.gate_log.exists())

    def test_resume_retests_after_gate_failure(self):
        self.env['GATE_FAIL_FIRST'] = '1'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.status()['status'], 'limit_reached')
        run_dir = next((self.repo / '.codex-harness' / 'runs').iterdir())
        result = self.command('resume', '--run-dir', run_dir, '--codex-bin', self.fake,
                              '--max-cycles', '2')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.status()['status'], 'complete')
        self.assertEqual(self.gate_log.read_text(), '2')
        self.assertEqual(sum(c['role'] == 'tester' for c in self.calls()), 2)
        developers = [c for c in self.calls() if c['role'] == 'developer']
        self.assertIn('unique gate failure for feedback', developers[-1]['prompt'])

    def test_resume_rejects_tampered_frozen_task(self):
        self.env['GATE_FAIL_FIRST'] = '1'
        self.run_harness()
        run_dir = next((self.repo / '.codex-harness' / 'runs').iterdir())
        frozen = run_dir / 'task.json'
        task = json.loads(frozen.read_text())
        task['goal'] = 'changed after start'
        frozen.write_text(json.dumps(task))
        count = len(self.calls())
        result = self.command('resume', '--run-dir', run_dir, '--codex-bin', self.fake,
                              '--max-cycles', '2')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), count)
        self.assertNotEqual(self.status()['status'], 'complete')

    def test_verification_cannot_complete_if_gate_changes_source(self):
        self.env['GATE_MUTATE'] = '1'
        result = self.run_harness()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual(self.status()['status'], 'complete')

    def test_stop_terminates_active_agent_and_concurrent_resume_is_locked(self):
        self.env['FAKE_MODE'] = 'sleep'
        proc = subprocess.Popen([sys.executable, str(HARNESS), 'run', '--task', str(self.task),
                                 '--codex-bin', str(self.fake), '--max-cycles', '1'],
                                cwd=self.repo, env=self.env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: proc.kill() if proc.poll() is None else None)
        deadline = time.monotonic() + 10
        while not self.calls() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.calls(), proc.communicate(timeout=2) if proc.poll() is not None else 'agent did not start')
        pid = self.calls()[0]['pid']
        run_dir = next((self.repo / '.codex-harness' / 'runs').iterdir())
        concurrent = self.command('resume', '--run-dir', run_dir, '--codex-bin', self.fake)
        self.assertNotEqual(concurrent.returncode, 0, concurrent.stdout + concurrent.stderr)
        stopped = self.command('stop', '--run-dir', run_dir)
        self.assertEqual(stopped.returncode, 0, stopped.stdout + stopped.stderr)
        stdout, stderr = proc.communicate(timeout=10)
        self.assertNotEqual(proc.returncode, 0, stdout + stderr)
        self.assertNotEqual(self.status()['status'], 'complete')
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_sigterm_cleans_up_agent_and_run_can_resume(self):
        self.env['FAKE_MODE'] = 'sleep'
        proc = subprocess.Popen([sys.executable, str(HARNESS), 'run', '--task', str(self.task),
                                 '--codex-bin', str(self.fake), '--max-cycles', '1'],
                                cwd=self.repo, env=self.env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: proc.kill() if proc.poll() is None else None)
        deadline = time.monotonic() + 10
        while not self.calls() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.calls())
        pid = self.calls()[0]['pid']
        run_dir = next((self.repo / '.codex-harness' / 'runs').iterdir())
        proc.send_signal(signal.SIGTERM)
        stdout, stderr = proc.communicate(timeout=10)
        self.assertNotEqual(proc.returncode, 0, stdout + stderr)
        self.assertEqual(self.status()['status'], 'interrupted')
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        del self.env['FAKE_MODE']
        result = self.command('resume', '--run-dir', run_dir, '--codex-bin', self.fake,
                              '--max-cycles', '2')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.status()['status'], 'complete')

    def test_agent_timeout_is_not_completion(self):
        self.env['FAKE_MODE'] = 'sleep'
        result = self.run_harness('--agent-timeout', '1')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual(self.status()['status'], 'complete')
        with self.assertRaises(ProcessLookupError):
            os.kill(self.calls()[0]['pid'], 0)

    def cleanup_module(self):
        spec = importlib.util.spec_from_file_location('harness_cleanup_test', HARNESS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_group_eperm_requires_inspection_and_only_signals_same_user_members(self):
        module = self.cleanup_module()
        listing = subprocess.CompletedProcess([], 0, '', '')
        with mock.patch.object(module.os, 'killpg', side_effect=PermissionError(1, 'denied')), \
             mock.patch.object(module.subprocess, 'run', return_value=listing) as ps, \
             mock.patch.object(module.os, 'kill') as kill:
            module.signal_process_group(54321, signal.SIGKILL)
            ps.assert_called_once()
            kill.assert_not_called()
            listing.stdout = f'54322 54321 {os.getuid()}\n'
            with mock.patch.object(module.os, 'getpgid', return_value=54321):
                module.signal_process_group(54321, signal.SIGKILL)
            kill.assert_called_once_with(54322, signal.SIGKILL)
            listing.stdout = f'54323 54321 {os.getuid() + 1}\n'
            with self.assertRaises(module.HarnessError):
                module.signal_process_group(54321, signal.SIGKILL)
            self.assertEqual(kill.call_count, 1)
            listing.returncode = 1
            with self.assertRaises(module.HarnessError):
                module.signal_process_group(54321, signal.SIGKILL)

    def run_with_cleanup_patch(self, patch):
        wrapper = self.base / 'patched_harness.py'
        wrapper.write_text(
            'import importlib.util, sys\n'
            f'spec=importlib.util.spec_from_file_location("h", {str(HARNESS)!r})\n'
            'h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h)\n'
            'def denied(*args): raise PermissionError(1, "injected cleanup denial")\n'
            + patch + '\nsys.exit(h.main())\n')
        return subprocess.run([sys.executable, str(wrapper), 'run', '--task', str(self.task),
                               '--codex-bin', str(self.fake), '--max-cycles', '1'],
                              cwd=self.repo, env=self.env, capture_output=True, text=True, timeout=25)

    def test_exited_group_eperm_does_not_lose_completed_phase(self):
        result = self.run_with_cleanup_patch('h.os.killpg=denied')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.status()['status'], 'complete')
        self.assertEqual(len(self.calls()), 4)
        self.assertEqual(self.gate_log.read_text(), '1')

    def test_unrecoverable_cleanup_records_error_and_flushes_final_output(self):
        self.env['FAKE_MODE'] = 'stream'
        result = self.run_with_cleanup_patch('h.signal_process_group=denied')
        self.assertNotEqual(result.returncode, 0)
        state = self.status()
        self.assertEqual(state['status'], 'error')
        self.assertIsNone(state['pid'])
        self.assertIn('injected cleanup denial', state['message'])
        self.assertIn('状态：error', result.stdout)
        self.assertIn('LIVE_PROGRESS_MARKER', result.stdout)
        self.assertIn('injected cleanup denial', Path(state['error_log']).read_text())
        self.assertEqual(len(self.calls()), 1)
        self.assertFalse(self.gate_log.exists())


if __name__ == '__main__':
    unittest.main()
