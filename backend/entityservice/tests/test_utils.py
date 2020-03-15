import textwrap

import pytest

from entityservice.errors import InvalidConfiguration
from entityservice.utils import load_yaml_config, deduplicate_sorted_iter
from entityservice.tests.util import generate_bytes, temp_file_containing


class TestYamlLoader:

    def test_empty(self):
        with temp_file_containing(b'') as fp:
            filename = fp.name
            assert None == load_yaml_config(filename)

    def test_list(self):
        with temp_file_containing(b'[1,2,3]') as fp:
            filename = fp.name
            assert [1, 2, 3] == load_yaml_config(filename)

    def test_missing_file(self):
        filename = 'unlikely a valid file'
        with pytest.raises(InvalidConfiguration):
            load_yaml_config(filename)

    def test_random_bytes(self):
        with temp_file_containing(generate_bytes(128)) as fp:
            filename = fp.name
            with pytest.raises(InvalidConfiguration):
                load_yaml_config(filename)

    def test_valid_yaml(self):
        yamldata = textwrap.dedent("""
        api:
          number: 42
          ingress:
            enabled: true
            host: example.com
        """)
        self._check_valid_yaml(yamldata)

    def _check_valid_yaml(self, yamldata: str):
        with temp_file_containing(yamldata.encode()) as fp:
            filename = fp.name
            loaded = load_yaml_config(filename)
        assert 'api' in loaded
        assert 'number' in loaded['api']
        assert loaded['api']['number'] == 42
        assert loaded['api']['ingress']['enabled']
        return loaded

    def test_valid_yaml_with_comments(self):
        yamldata = textwrap.dedent("""
        ## Api is a thing
        api:
          number: 42
          ingress:
            enabled: true
            # host: example.com
        """)
        loaded = self._check_valid_yaml(yamldata)
        assert 'host' not in loaded['api']['ingress']


def test_deduplicate_sorted_iter():
    assert list(deduplicate_sorted_iter(iter([1, 2, 2, 2, 3]))) == [1, 2, 3]

    res = list(deduplicate_sorted_iter(zip(['a','a','a'], [1, 1, 1], [1,1,2])))
    assert res == [('a', 1, 1), ('a', 1, 2)]