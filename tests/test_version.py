import subprocess
import tempfile
from pathlib import Path
import unittest

from scripts.version import (app_changed,bump,check,current,next_version,parse,
                             release_notes,transition)


PROJECT='[project]\nname = "fixture"\nversion = "0.1.0"\ndependencies = []\n'
LOG='# Changes\n\n## [0.1.0] - 2026-10-09\n\nInitial fixture.\n'


class VersionTests(unittest.TestCase):
    def test_patch_minor_and_major_reset(self):
        self.assertEqual(next_version('0.2.4','patch'),'0.2.5')
        self.assertEqual(next_version('0.2.4','minor'),'0.3.0')
        self.assertEqual(next_version('0.2.4','major',True),'1.0.0')

    def test_major_needs_explicit_request(self):
        with self.assertRaises(ValueError):
            next_version('0.2.4','major')
        with self.assertRaises(ValueError):
            transition('0.2.4','1.0.0',True)
        transition('0.2.4','1.0.0',True,True)

    def test_version_syntax_and_regression(self):
        for value in ('1.2','01.2.3','1.02.3','1.2.3-beta','v1.2.3'):
            with self.assertRaises(ValueError):
                parse(value)
        with self.assertRaises(ValueError):
            transition('0.2.4','0.2.3',False)

    def test_docs_tests_and_version_metadata_are_not_app_changes(self):
        self.assertFalse(app_changed(['README.md','docs/guide.md','tests/test_fixture.py'],PROJECT,PROJECT))
        self.assertFalse(app_changed(['pyproject.toml'],PROJECT,PROJECT.replace('0.1.0','0.1.1')))
        self.assertTrue(app_changed(['src/fixture.py'],PROJECT,PROJECT))
        self.assertTrue(app_changed(['pyproject.toml'],PROJECT,PROJECT.replace('dependencies = []','dependencies = ["fixture-package"]')))

    def test_app_changes_require_a_new_version(self):
        with self.assertRaises(ValueError):
            transition('0.1.0','0.1.0',True)
        transition('0.1.0','0.1.0',False)
        transition('0.1.0','0.1.1',True)

    def test_release_notes_are_limited_to_the_chosen_version(self):
        log='# Changes\n\n## [0.1.1] - today\n\nNew feature.\n\n## [0.1.0] - yesterday\n\nOriginal feature.\n'
        self.assertEqual(release_notes(log,'0.1.1'),'New feature.\n')
        with self.assertRaises(ValueError):
            release_notes(log,'0.1.2')

    def test_bump_updates_only_version_and_adds_release_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'pyproject.toml').write_text(PROJECT,encoding='utf-8')
            (root/'CHANGELOG.md').write_text(LOG,encoding='utf-8')
            value=bump(root,'patch','Fixture improvement')
            self.assertEqual(value,'0.1.1')
            text=(root/'pyproject.toml').read_text(encoding='utf-8')
            self.assertEqual(current(text),'0.1.1')
            self.assertEqual(text.replace('0.1.1','0.1.0'),PROJECT)
            self.assertEqual(release_notes((root/'CHANGELOG.md').read_text(encoding='utf-8'),value),'- Fixture improvement\n')
            with self.assertRaises(ValueError):
                bump(root,'major','No permission')
            self.assertEqual(current((root/'pyproject.toml').read_text(encoding='utf-8')),'0.1.1')

    def test_git_check_rejects_unversioned_code_and_accepts_justified_typo(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root,encoding='utf-8',stderr=subprocess.PIPE).strip()
            git('init','-b','main')
            git('config','user.name','Fixture')
            git('config','user.email','fixture@example.invalid')
            (root/'pyproject.toml').write_text(PROJECT,encoding='utf-8')
            (root/'CHANGELOG.md').write_text(LOG,encoding='utf-8')
            (root/'src').mkdir()
            code=root/'src/fixture.py'
            code.write_text('value = "original"\n',encoding='utf-8')
            git('add','.')
            git('commit','-m','Initial fixture')
            base=git('rev-parse','HEAD')
            code.write_text('value = "changed"\n',encoding='utf-8')
            with self.assertRaises(ValueError):
                check(root=root)
            git('add','.')
            git('commit','-m','Fixture change')
            with self.assertRaises(ValueError):
                check(base,root,working=False)
            git('commit','--amend','-m','Fixture spelling correction\n\nGlareshield-No-App-Change: spelling only')
            self.assertEqual(check(base,root,working=False),('0.1.0',False))


if __name__=='__main__':
    unittest.main()
