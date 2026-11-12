from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import msfs_autostart as m


class AutostartTests(unittest.TestCase):
    def test_install_is_idempotent_and_remove_keeps_others(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'local/.venv/Scripts').mkdir(parents=True)
            (root/'local/.venv/Scripts/pythonw.exe').touch()
            xml=root/'exe.xml'
            xml.write_text('<SimBase.Document><Launch.Addon><Name>Other</Name></Launch.Addon></SimBase.Document>')
            with mock.patch.object(m,'ROOT',root):
                m.main(['install','--exe-xml',str(xml)])
                m.main(['install','--exe-xml',str(xml)])
                self.assertEqual(len(m.entries(m.load(xml))),1)
                m.main(['remove','--exe-xml',str(xml)])
            tree=m.load(xml)
            self.assertEqual(m.entries(tree),[])
            self.assertEqual(len(tree.getroot().findall('Launch.Addon')),1)
            self.assertTrue((root/'exe.xml.glareshield.bak').exists())

    def test_launcher_is_guarded_for_spawned_workers(self):
        source=(Path(m.__file__).with_name('launch.pyw')).read_text(encoding='utf-8')
        self.assertIn("if __name__=='__main__':",source)
        self.assertLess(source.index("if __name__=='__main__':"),source.index('    main()'))
