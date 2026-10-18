"""Owned PC Android frontend, observer and unprivileged socket acceptance."""
from pathlib import Path
import http.server, subprocess, sys, threading
HERE=Path(__file__).resolve().parent
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        data=b'p2d-owned-android-network-test';self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:subprocess.run([sys.executable,str(HERE/'run_frontend_lifecycle.py'),'--network','--http-port',str(server.server_port),*sys.argv[1:]],check=True)
finally:server.shutdown();server.server_close();thread.join()
