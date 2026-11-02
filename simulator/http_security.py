"""Browser isolation and static-file boundaries for the loopback development UI."""
from pathlib import Path
from urllib.parse import urlsplit


class LocalHTTPGuard:
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def parse_request(self):
        if not super().parse_request():return False
        hosts=self.headers.get_all('Host',[])
        try:
            if len(hosts)!=1:raise ValueError()
            target=urlsplit('http://'+hosts[0])
            if target.hostname not in ('127.0.0.1','localhost','::1') or target.username or target.password:
                raise ValueError()
            if (target.port or 80)!=self.server.server_port or target.path or target.query or target.fragment:
                raise ValueError()
            if self.headers.get('Sec-Fetch-Site')=='cross-site':raise ValueError()
            origins=self.headers.get_all('Origin',[])
            if origins and (len(origins)!=1 or origins[0]!=f'http://{hosts[0]}'):raise ValueError()
            if urlsplit(self.path).scheme or urlsplit(self.path).netloc:raise ValueError()
        except ValueError:
            self.close_connection=True;self.send_error(403,'Only same-origin loopback requests are accepted');return False
        if self.headers.get_all('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))>1:
            self.close_connection=True;self.send_error(400,'Ambiguous request framing');return False
        return True

    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cross-Origin-Resource-Policy','same-origin')
        self.send_header('Content-Security-Policy',
            "default-src 'self'; script-src 'self'; connect-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        super().end_headers()

    def list_directory(self,path):
        self.send_error(403,'Directory listings are disabled');return None

    def send_head(self):
        target=Path(self.translate_path(self.path)).resolve()
        root=Path(self.directory).resolve()
        if not target.is_relative_to(root) or any(part.startswith('.') for part in target.relative_to(root).parts):
            self.send_error(404,'File not found');return None
        return super().send_head()
