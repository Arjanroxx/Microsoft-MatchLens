import unittest

from backend.app.agent_providers import OllamaAgents, require_local_model


class LocalInferenceTests(unittest.TestCase):
    def test_remote_or_credential_bearing_endpoints_are_rejected(self):
        for host in ('https://ollama.com', 'http://example.com:11434',
                     'http://key@localhost:11434', 'http://localhost:11434?key=secret',
                     'http://localhost:11434/proxy', 'file:///tmp/model'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                OllamaAgents(host=host)
        for host in ('http://127.0.0.1:11434', 'http://localhost:11434', 'http://[::1]:11434'):
            self.assertEqual(OllamaAgents(host=host).host, host)

    def test_cloud_names_and_renamed_cloud_aliases_are_rejected(self):
        with self.assertRaises(ValueError):OllamaAgents(model='example:cloud')
        for details in ({'remote_model':'remote-model'}, {'remote_host':'https://ollama.com'}, None):
            with self.assertRaises(ValueError):require_local_model(details)
        require_local_model({'details':{'parameter_size':'1.7B'}, 'model_info':{}})


if __name__=='__main__':unittest.main()
