"""Loopback-only, synthetic application forms for manual and automated browser checks.

Run: python -m examples.fixture_server --port 8766
No candidate data is logged or retained by this server.
"""
from argparse import ArgumentParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

FIXTURES=Path(__file__).parent/'fixtures'


class FixtureServer:
    def __init__(self,port:int=0,application_html:str|None=None,redirects:dict[str,str]|None=None):
        self.submissions=[]
        submissions=self.submissions
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in (redirects or {}):
                    self.send_response(302)
                    self.send_header('Location',redirects[self.path])
                    self.end_headers()
                    return
                if self.path.startswith('/controls'): content=(FIXTURES/'controls.html').read_text(encoding='utf-8')
                elif self.path.startswith('/frame'): content=(FIXTURES/'frame.html').read_text(encoding='utf-8')
                elif self.path.startswith('/login'): content='<label>Password<input type="password"></label><button>Sign in</button>'
                elif self.path.startswith('/captcha'): content='<h1>Verify you are human</h1><p>CAPTCHA</p>'
                elif self.path.startswith('/failure'): content='<h1>Application failed</h1><p role="alert">Upload rejected. Try manually.</p>'
                elif application_html: content=application_html
                elif self.path.startswith('/apply'): content=(FIXTURES/'application.html').read_text(encoding='utf-8')
                else: content='<h1>ForgeApply fixtures</h1><a href="/controls">Dynamic controls and iframe</a>'
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode())
            def do_POST(self):
                submissions.append(self.path)
                self.send_response(200)
                self.end_headers()
            def log_message(self,*args): pass
        self.server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self,*args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    with FixtureServer(args.port) as fixture:
        print(f'Controlled fixture: {fixture.url}/controls (Ctrl+C to stop)')
        try: threading.Event().wait()
        except KeyboardInterrupt: pass
