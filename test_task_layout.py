"""Offline migration regression: imports, caller cwd, legacy paths, navigation."""
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class TaskLayoutTests(unittest.TestCase):
    def test_legacy_imports_alias_canonical_modules(self):
        for slug, module in [('batch-executor', 'batch_executor'),
                             ('policy-gatekeeper', 'policy_gatekeeper')]:
            legacy = importlib.import_module(module)
            canonical = importlib.import_module(f'tasks.{slug}.source.{module}')
            self.assertIs(legacy, canonical)
            assert legacy.__file__ is not None
            self.assertEqual(Path(legacy.__file__), ROOT / f'tasks/{slug}/source/{module}.py')
            self.assertEqual((ROOT / f'tasks/{slug}/tests/test_{module}.py').resolve(),
                             ROOT / f'test_{module}.py')

    def test_policy_cli_preserves_caller_paths_and_audit_append(self):
        request = {'action': 'transfer', 'asset': 'USDC', 'amount': '25',
                   'to': '0x1111111111111111111111111111111111111111',
                   'requested_at': '2026-10-22T12:00:00Z'}
        with tempfile.TemporaryDirectory() as folder:
            cwd = Path(folder)
            (cwd / 'policy-gatekeeper.json').write_bytes((ROOT / 'policy-gatekeeper.json').read_bytes())
            for script in ['policy_gatekeeper.py', 'tasks/policy-gatekeeper/source/policy_gatekeeper.py']:
                for amount, decision in [('25', 'allow'), ('101', 'deny')]:
                    request['amount'] = amount
                    result = subprocess.run([sys.executable, str(ROOT / script), json.dumps(request)],
                                            cwd=cwd, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(report['decision'], decision)
                    if decision == 'allow':
                        self.assertFalse(report['prepared']['signed'])
                        self.assertFalse(report['prepared']['broadcast'])
                    else:
                        self.assertNotIn('prepared', report)
            records = (cwd / 'policy-gatekeeper-audit.jsonl').read_text().splitlines()
            self.assertEqual([json.loads(row)['decision'] for row in records],
                             ['allow', 'deny', 'allow', 'deny'])

    def test_batch_cli_reads_relative_input_and_fails_before_rpc(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'actions.json').write_text('[]')
            for script in ['batch_executor.py', 'tasks/batch-executor/source/batch_executor.py']:
                result = subprocess.run([sys.executable, str(ROOT / script), '@actions.json'],
                                        cwd=folder, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                report = json.loads(result.stderr)
                self.assertIn('at least 3', report['error']['message'])
                self.assertFalse(report['broadcast'])
                self.assertNotIn('prepared_transaction', report)

    @unittest.skipUnless(os.environ.get('PUBLICATION_MANIFEST'),
                         'Set PUBLICATION_MANIFEST to check HEAD plus approved publication paths')
    def test_task_map_publication_links(self):
        manifest = json.loads(Path(os.environ['PUBLICATION_MANIFEST']).read_text())
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        self.assertEqual(head, manifest['head'])
        tree = subprocess.check_output(['git', 'ls-tree', '-rz', '--full-tree', 'HEAD'], cwd=ROOT)
        published = {}
        for entry in tree.split(b'\0'):
            if entry:
                metadata, name = entry.split(b'\t', 1)
                mode, _, oid = metadata.decode().split()
                published[name.decode()] = (mode, oid)
        symlinks = {}
        for item in manifest['candidate_paths']:
            path = item['path']
            self.assertTrue(os.path.lexists(ROOT / path), path)
            mode = '120000' if (ROOT / path).is_symlink() else '100644'
            self.assertEqual(mode, item['git_mode'], path)
            published[path] = (mode, None)
            if mode == '120000':
                symlinks[path] = os.readlink(ROOT / path)
                self.assertEqual(symlinks[path], item['symlink_target'], path)
        for path, (mode, oid) in published.items():
            if mode == '120000' and oid:
                symlinks[path] = subprocess.check_output(
                    ['git', 'cat-file', 'blob', oid], cwd=ROOT, text=True)

        def available(path, seen=()):
            path = posixpath.normpath(path)
            if path.startswith('../') or path.startswith('/') or path in seen:
                return False
            parts = PurePosixPath(path).parts
            for i in range(1, len(parts) + 1):
                prefix = '/'.join(parts[:i])
                if prefix in symlinks:
                    target = posixpath.join(posixpath.dirname(prefix), symlinks[prefix], *parts[i:])
                    return available(target, (*seen, path))
            return path in published or any(p.startswith(path + '/') for p in published)

        broken = []
        for target in re.findall(r'\]\(([^)]+)\)', (ROOT / 'tasks/README.md').read_text()):
            if '://' not in target and not target.startswith('#'):
                if not available(posixpath.join('tasks', target.split('#')[0])):
                    broken.append(target)
        for path in symlinks:
            if not available(path):
                broken.append(path)
        self.assertEqual(broken, [], 'Targets absent from HEAD plus approved publication paths')

    def test_task_map_links_and_known_videos(self):
        paths = [ROOT / 'README.md', ROOT / 'tasks/README.md', ROOT / 'videos/README.md']
        paths += list((ROOT / 'tasks').glob('*/README.md'))
        paths += list((ROOT / 'tasks').glob('*/evidence/README.md'))
        paths += [ROOT / 'README-batch-executor.md', ROOT / 'README-policy-gatekeeper.md']
        for path in paths:
            text = path.read_text()
            for target in re.findall(r'\]\(([^)]+)\)', text):
                if '://' not in target and not target.startswith('#'):
                    self.assertTrue((path.parent / target.split('#')[0]).exists(), f'{path}: {target}')
        slugs = re.findall(r'^\| ([a-z][a-z0-9-]+) \|', (ROOT / 'tasks/README.md').read_text(), re.M)
        self.assertEqual(len(slugs), 30)
        self.assertEqual(len(set(slugs)), 30)
        catalog = ROOT / 'arena-tasks.json'
        if catalog.exists():
            self.assertEqual(set(slugs), {task['slug'] for task in json.loads(catalog.read_text())})
        videos = (ROOT / 'videos/README.md').read_text()
        self.assertEqual(re.findall(r'https://x\.com/\S+', videos), [
            'https://x.com/mxmeepo/status/2120326041436914009?a=-IqSQ-9evwt9IC7fG4g&s=20',
            'https://x.com/mxmeepo/status/2120319479930605855?a=kIKn2WCLkwvdDC785Ns&s=20'])
        self.assertNotIn('2120318415240102317', videos)


if __name__ == '__main__':
    unittest.main()
