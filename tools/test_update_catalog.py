import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import update_catalog as catalog

def repo(name, **extra):
    return {'name':name,'owner':{'login':catalog.OWNER},'private':False,**extra}

class CatalogTests(unittest.TestCase):
    def test_only_public_owned_projects(self):
        records=[repo('public'),repo('private',private=True),repo(catalog.OWNER),repo(catalog.OWNER+'.github.io'),repo('someone-else',owner={'login':'other'}),{'name':'unknown','owner':{'login':catalog.OWNER}}]
        self.assertEqual([r['name'] for r in catalog.public_records(records)],['public'])

    def test_new_repository_and_untrusted_description(self):
        page,profile=catalog.render([repo('new-project',description='<script>alert(1)</script> | [link](evil)',homepage='javascript:alert(1)')],{},'2026-10-06')
        self.assertIn('Other projects',page)
        self.assertIn('new-project',page)
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('<script>',page)
        self.assertNotIn('javascript:',page)
        self.assertIn('&#124;',profile)
        self.assertIn('&#91;link&#93;',profile)

    def test_pagination_includes_repository_on_second_page(self):
        pages=[json.dumps([repo(f'project-{i}') for i in range(100)]).encode(),json.dumps([repo('last-project')]).encode()]
        calls=[]
        def opener(request,timeout):
            calls.append(request.full_url)
            return io.BytesIO(pages.pop(0))
        records=catalog.fetch_repositories(opener)
        self.assertEqual(len(records),101)
        self.assertTrue(calls[1].endswith('page=2'))
        self.assertIn('last-project',[r['name'] for r in records])

    def test_api_failure_preserves_previous_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir()
            (root/'data/overrides.json').write_text('{}')
            (root/'index.html').write_text('previous page')
            (root/'data/repos.json').write_text('previous snapshot')
            with patch.object(catalog,'fetch_repositories',side_effect=OSError('network unavailable')):
                with self.assertRaises(OSError):catalog.update(root)
            self.assertEqual((root/'index.html').read_text(),'previous page')
            self.assertEqual((root/'data/repos.json').read_text(),'previous snapshot')

    def test_refresh_removes_repository_no_longer_public(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir()
            (root/'data/overrides.json').write_text(json.dumps({'old':{'description':'old description'}}))
            (root/'data/repos.json').write_text(json.dumps({'updated_at':'2026-10-06','repositories':[repo('old')]}))
            with patch.object(catalog,'fetch_repositories',return_value=[repo('new')]):catalog.update(root)
            self.assertNotIn('old description',(root/'index.html').read_text())
            self.assertNotIn('old description',(root/'data/profile-README.md').read_text())
            self.assertEqual([r['name'] for r in json.loads((root/'data/repos.json').read_text())['repositories']],['new'])

    def test_offline_preserves_date_and_does_not_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir()
            (root/'data/overrides.json').write_text('{}')
            (root/'data/repos.json').write_text(json.dumps({'updated_at':'2026-10-06','repositories':[repo('current')]}))
            with patch.object(catalog,'fetch_repositories',side_effect=AssertionError('must not fetch')):
                self.assertEqual(catalog.update(root,offline=True),1)
            self.assertIn('2026-10-06',(root/'index.html').read_text())

if __name__=='__main__':
    unittest.main()
