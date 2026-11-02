import functools
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from simulator.http_security import LocalHTTPGuard


class GuardedHandler(LocalHTTPGuard, SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


class LocalSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / 'index.html').write_text('Safe preview', encoding='utf-8')
        (root / '.private').write_text('private', encoding='utf-8')
        (root / 'folder').mkdir()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(GuardedHandler, directory=root))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(); self.temp.cleanup()

    def request(self, path='/', headers=()):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.putrequest('GET', path, skip_host=True)
        for name, value in headers or [('Host', f'127.0.0.1:{self.server.server_port}')]:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_same_origin_and_security_headers(self):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        status, headers, body = self.request(headers=[('Host', origin[7:]), ('Origin', origin)])
        self.assertEqual(status, 200)
        self.assertIn(b'Safe preview', body)
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("script-src 'self'", headers['Content-Security-Policy'])

    def test_cross_site_and_rebinding_are_rejected(self):
        host = ('Host', f'127.0.0.1:{self.server.server_port}')
        for headers in ([('Host', f'attacker.invalid:{self.server.server_port}')],
                        [host, ('Origin', 'https://attacker.invalid')],
                        [host, ('Sec-Fetch-Site', 'cross-site')], [host, host]):
            self.assertEqual(self.request(headers=headers)[0], 403)

    def test_ambiguous_body_framing_is_rejected(self):
        host = ('Host', f'127.0.0.1:{self.server.server_port}')
        for headers in ([host, ('Content-Length', '0'), ('Content-Length', '0')],
                        [host, ('Transfer-Encoding', 'chunked')]):
            self.assertEqual(self.request(headers=headers)[0], 400)

    def test_hidden_files_and_directory_listing_are_denied(self):
        self.assertEqual(self.request('/.private')[0], 404)
        self.assertEqual(self.request('/folder/')[0], 403)


if __name__ == '__main__': unittest.main()
