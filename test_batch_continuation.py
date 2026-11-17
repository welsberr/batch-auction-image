from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import csv, importlib.util, json
from PIL import Image

spec=importlib.util.spec_from_file_location('auction_poc',Path(__file__).with_name('auction_poc.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with TemporaryDirectory() as tmp:
    root=Path(tmp).resolve();source=root/'source';source.mkdir()
    def item(i,can=None,view='a',**kw):
        path=source/f'camera_{i:04}.JPG';Image.new('RGB',(80,120),(i,120,120)).save(path)
        return dict(source=str(path),name=path.name,sha256=m.digest(path),include=True,reviewed=True,
                    can=str(i if can is None else can),view=view,width=80,height=120,crop=[0,0,80,120],**kw)
    good=item(1,flags=['Check crop'],focus_score=10)
    invalid=item(2,view='');missing=item(3);Path(missing['source']).unlink()
    changed=item(4);changed['sha256']='bad'
    duplicate1=item(5,can=5);duplicate2=item(6,can=5)
    dupsource=item(7);dupsource2=dict(dupsource,can='8')
    badcrop=item(9);badcrop['crop']=[79,0,10,10]
    fail_save=item(10);after=item(11)
    excluded=item(12);excluded['include']=False
    unreviewed=item(13);unreviewed['reviewed']=False
    corrupt_path=source/'camera_0014.JPG';corrupt_path.write_bytes(b'not an image')
    corrupt=dict(source=str(corrupt_path),name=corrupt_path.name,sha256=m.digest(corrupt_path),include=True,reviewed=True,can='14',view='a',width=80,height=120,crop=[0,0,80,120])
    profile={'label':'Tall','width':200,'height':300,'background':'#ffffff','upscale':False}
    inconsistent1=item(15,can=15,profile_id='tall');inconsistent2=item(16,can=15,view='b')
    records=[good,invalid,missing,changed,duplicate1,duplicate2,dupsource,dupsource2,badcrop,fail_save,after,excluded,unreviewed,corrupt,inconsistent1,inconsistent2]
    plan={'version':1,'auction':'42','source_dir':str(source),'views':6,'profiles':{'tall':profile},'records':records}
    planfile=root/'plan.json';planfile.write_text(json.dumps(plan))
    real_save=Image.Image.save
    def failing_save(self,fp,*args,**kwargs):
        if getattr(fp,'name','').endswith('42_10a.jpg'):
            fp.write(b'partial');raise OSError('simulated disk write error')
        return real_save(self,fp,*args,**kwargs)
    output=root/'output'
    with patch.object(Image.Image,'save',failing_save):report=m.apply_review(planfile,output,'crop')
    assert report['summary']=={'total':16,'written':2,'errors':12,'skipped_excluded':1,'skipped_unreviewed':1,'warning_records':1},report['summary']
    assert (output/'42_1a.jpg').exists() and (output/'42_11a.jpg').exists()
    assert not (output/'42_10a.jpg').exists()
    assert 'simulated disk write error' in report['records'][9]['message']
    assert 'Invalid can number or view' in report['records'][1]['message']
    assert len(report['records'][0]['warnings'])==2
    with (output/'mapping.csv').open() as f: assert len(list(csv.DictReader(f)))==2
    with (output/'processing-report.csv').open(encoding='utf-8-sig') as f: assert len(list(csv.DictReader(f)))==16
    assert json.loads((output/'processing-report.json').read_text())==report
    try:m.apply_review(planfile,output,'crop');raise AssertionError('Existing output was accepted')
    except ValueError as exc:assert 'already exists' in str(exc)
    assert m.digest(Path(good['source']))==good['sha256']
    # A corrupt file remains in position as a disabled placeholder; later photos are analyzed.
    review=root/'review';m.make_review(source,review,'42',1,2)
    analysis=json.loads((review/'analysis.json').read_text())
    placeholder=next(r for r in analysis['records'] if r['name']=='camera_0014.JPG')
    assert not placeholder['include'] and not placeholder['reviewed'] and 'Analysis failed' in placeholder['flags'][0]
    assert any(r['name']=='camera_0016.JPG' and r['include'] for r in analysis['records'])
    with (review/'analysis-report.csv').open(encoding='utf-8-sig') as f: assert any(row['status']=='error' and 'camera_0014.JPG' in row['source'] for row in csv.DictReader(f))
    assert (review/'review.html').exists()
    print('PASS: continuation, validation errors, collisions, partial-file cleanup, reports, and corrupt-photo analysis')
