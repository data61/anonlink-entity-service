import textwrap

import pytest

from entityservice.errors import InvalidConfiguration
from entityservice.utils import load_yaml_config
from entityservice.tests.util import generate_bytes, temp_file_containing
from entityservice.views import convert_encoding_upload_to_clknblock


class TestEncodingConversionUtils:

    def test_convert_encoding_upload_to_clknblock_encodings_only(self):

        out = convert_encoding_upload_to_clknblock({
            "encodings": ['123', '456', '789']
        })

        assert 'clknblocks' in out
        assert len(out['clknblocks']) == 3
        assert out['clknblocks'][0] == ['123', '1']

    def test_convert_encoding_upload_to_clknblock(self):

        out = convert_encoding_upload_to_clknblock({
            "encodings": ['123', '456', '789', '000'],
            "blocks": {
                '0': ['1', '2'],
                '1': ['1'],
                '2': []
            }
        })

        assert 'clknblocks' in out
        assert len(out['clknblocks']) == 3
        assert out['clknblocks'][0] == ['123', '1', '2']
        assert out['clknblocks'][1] == ['456', '1']
        assert out['clknblocks'][2] == ['789', ]


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


