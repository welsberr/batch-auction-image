"""Local, capability-protected bridge between a review page and the desktop app."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_PLAN_BYTES = 32 * 1024 * 1024


class ReviewServer:
    def __init__(self, page, on_process):
        self.page = Path(page).resolve()
        self.on_process = on_process
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.status = {'state': 'idle', 'message': 'Save or load a reviewed plan to create output.'}
        # The data precedes the much larger embedded thumbnail array.
        with self.page.open('r', encoding='utf-8') as stream:
            prefix = stream.read(32 * 1024 * 1024)
        marker = 'const initial='
        pos = prefix.find(marker)
        if pos < 0:
            raise ValueError('This is not a supported review page.')
        initial = json.JSONDecoder().raw_decode(prefix[pos + len(marker):].lstrip())[0]
        self.source = initial['source_dir']
        self.records = {r['id']: (r['source'], r['sha256']) for r in initial['records']}
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_json(self, code, value):
                body = json.dumps(value, ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(body)

            def permitted_host(self):
                return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

            def do_GET(self):
                if not self.permitted_host():
                    return self.send_json(403, {'error': 'Invalid host'})
                if self.path == f'/{bridge.token}/review':
                    try:
                        with bridge.page.open('rb') as page_file:
                            size = bridge.page.stat().st_size
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/html; charset=utf-8')
                            self.send_header('Content-Length', str(size))
                            self.send_header('Cache-Control', 'no-store')
                            self.send_header('Referrer-Policy', 'no-referrer')
                            self.end_headers()
                            import shutil
                            shutil.copyfileobj(page_file, self.wfile)
                    except (OSError, BrokenPipeError):
                        pass
                elif self.path == f'/{bridge.token}/status':
                    with bridge.lock:
                        status = dict(bridge.status)
                    self.send_json(200, status)
                else:
                    self.send_json(404, {'error': 'Not found'})

            def do_POST(self):
                origin = f'http://127.0.0.1:{self.server.server_port}'
                if (not self.permitted_host() or self.path != f'/{bridge.token}/process'
                        or self.headers.get('Origin') != origin
                        or self.headers.get('Content-Type', '').split(';')[0] != 'application/json'):
                    return self.send_json(403, {'error': 'Request not allowed'})
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if length <= 0 or length > MAX_PLAN_BYTES:
                        raise ValueError('Plan is empty or too large')
                    plan = json.loads(self.rfile.read(length))
                    bridge.validate(plan)
                except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                    return self.send_json(400, {'error': str(exc)})
                with bridge.lock:
                    if bridge.status['state'] in ('choosing', 'running'):
                        return self.send_json(409, {'error': 'Processing is already active.'})
                    bridge.status = {'state': 'choosing', 'message': 'Choose where to create the output folder in the desktop app.'}
                try:
                    bridge.on_process(bridge, plan)
                except Exception as exc:
                    bridge.set_status('error', str(exc))
                    return self.send_json(500, {'error': str(exc)})
                self.send_json(202, {'state': 'choosing'})

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.http.daemon_threads = True
        self.url = f'http://127.0.0.1:{self.http.server_port}/{self.token}/review'
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def validate(self, plan):
        if (not isinstance(plan, dict) or plan.get('version') != 1
                or plan.get('plan_kind') != 'reviewed-output' or plan.get('source_dir') != self.source
                or not isinstance(plan.get('records'), list) or not plan['records']):
            raise ValueError('Choose a nonempty reviewed plan for this project.')
        seen = set()
        for record in plan['records']:
            if not isinstance(record, dict):
                raise ValueError('Invalid photo in reviewed plan.')
            key = record.get('id')
            if (key in seen or key not in self.records or
                    (record.get('source'), record.get('sha256')) != self.records[key] or
                    record.get('include') is not True or record.get('reviewed') is not True):
                raise ValueError('This reviewed plan does not match the current project.')
            seen.add(key)

    def set_status(self, state, message, **details):
        with self.lock:
            self.status = {'state': state, 'message': message, **details}

    def close(self):
        self.http.shutdown()
        self.http.server_close()
