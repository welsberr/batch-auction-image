"""Exercise the loopback bridge and real cropped output without a GUI."""
import json
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
import auction_poc
from review_server import ReviewServer


def request(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'photos'
    source.mkdir()
    photo = source / 'camera.jpg'
    Image.new('RGB', (60, 80), 'red').save(photo)
    record = {'id': 0, 'source': str(photo), 'sha256': auction_poc.digest(photo),
              'name': photo.name, 'include': True, 'reviewed': True, 'can': '1',
              'view': 'a', 'view_kind': 'side', 'width': 60, 'height': 80,
              'crop': [5, 5, 40, 60]}
    plan = {'version': 1, 'plan_kind': 'reviewed-output', 'source_dir': str(source),
            'auction': '42', 'views': 6, 'contrast': 'none', 'records': [record]}
    page = root / 'review.html'
    page.write_text('const initial=' + json.dumps(plan) + ';\nconst thumbnailData=[];', encoding='utf-8')
    submitted = []

    def start(server, value):
        submitted.append(value)
        def worker():
            try:
                server.set_status('running', 'Processing')
                plan_file = root / 'plan.json'
                plan_file.write_text(json.dumps(value), encoding='utf-8')
                report = auction_poc.apply_review(plan_file, root / 'output', 'crop')
                server.set_status('done', 'Finished', summary=report['summary'])
            except Exception as exc:
                server.set_status('error', str(exc))
        threading.Thread(target=worker, daemon=True).start()

    bridge = ReviewServer(page, start)
    try:
        parsed = urlsplit(bridge.url)
        origin = f'{parsed.scheme}://{parsed.netloc}'
        base = bridge.url.rsplit('/', 1)[0]
        headers = {'Origin': origin, 'Content-Type': 'application/json'}
        assert request(bridge.url)[0] == 200
        assert request(origin + '/wrong/review')[0] == 404
        payload = json.dumps(plan).encode()
        assert request(base + '/process', payload, {'Origin': 'http://evil.example', 'Content-Type': 'application/json'})[0] == 403
        bad = dict(plan, source_dir='different')
        assert request(base + '/process', json.dumps(bad).encode(), headers)[0] == 400
        bad = dict(plan, records=[dict(record, sha256='wrong')])
        assert request(base + '/process', json.dumps(bad).encode(), headers)[0] == 400
        assert request(base + '/process', payload, headers)[0] == 202
        for _ in range(100):
            status = json.loads(request(base + '/status')[1])
            if status['state'] in ('done', 'error'):break
            time.sleep(.05)
        assert status['state'] == 'done', status
        assert status['summary']['written'] == 1 and len(submitted) == 1
        with Image.open(root / 'output' / '42_1a.jpg') as output:
            assert output.size == (40, 60)
        assert photo.exists() and (root / 'output' / 'processing-report.csv').is_file()
        print('PASS: local bridge, origin and project checks, real cropped output and report')
    finally:
        bridge.close()
