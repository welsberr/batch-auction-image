"""Check that a version-1 saved plan can be processed without review HTML."""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    source = root / 'originals'
    source.mkdir()
    photo = source / 'camera_1.jpg'
    Image.new('RGB', (32, 48), 'blue').save(photo)
    digest = hashlib.sha256(photo.read_bytes()).hexdigest()
    # Older plans have neither plan_kind nor size profiles/view_kind.
    record = {'source': str(photo), 'name': photo.name, 'sha256': digest,
              'include': True, 'reviewed': True, 'can': '1', 'view': 'a',
              'width': 32, 'height': 48, 'crop': [2, 3, 20, 30]}
    plan = {'version': 1, 'auction': '42', 'source_dir': str(source),
            'contrast': 'none', 'records': [record]}
    saved = root / 'reviewed-plan-old.json'
    saved.write_text(json.dumps(plan), encoding='utf-8')
    output = root / 'output'
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('auction_poc.py')),
                             'apply', str(saved), str(output), '--mode', 'crop'],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    with Image.open(output / '42_1a.jpg') as image:
        assert image.size == (20, 30)
    assert json.loads((output / 'processing-report.json').read_text())['summary']['written'] == 1
    assert hashlib.sha256(photo.read_bytes()).hexdigest() == digest
    print('PASS: legacy saved plan processed directly; originals unchanged')
