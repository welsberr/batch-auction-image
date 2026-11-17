from pathlib import Path
import importlib.util,json,tempfile,hashlib
from PIL import Image
import numpy as np
p=Path(__file__).with_name('auction_poc.py').resolve()
s=importlib.util.spec_from_file_location('auction_poc',p); m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp).resolve();src=root/'original';src.mkdir()
 path=src/'camera_0001.JPG';im=Image.new('RGB',(120,80),'red');exif=im.getexif();exif[274]=6;im.save(path,exif=exif)
 sha=m.digest(path)
 base={'source':str(path),'name':path.name,'include':True,'reviewed':False,'sha256':sha,'can':'01','view':'a','width':80,'height':120,'crop':[10,20,30,40]}
 plan={'version':1,'source_dir':str(src),'auction':'42','records':[base]};f=root/'plan.json';f.write_text(json.dumps(plan))
 assert m.apply_review(f,root/'nope','copy')['summary']['skipped_unreviewed']==1
 base['reviewed']=True;base['view_kind']='end';f.write_text(json.dumps(plan))
 assert 'incompatible' in m.apply_review(f,root/'invalid-end','copy')['records'][0]['message']
 base['view_kind']='side';base['view']='c';plan['views']=2;f.write_text(json.dumps(plan))
 assert 'incompatible' in m.apply_review(f,root/'invalid-two-view','copy')['records'][0]['message']
 base['view']='a';plan['views']=6
 base['reviewed']=True;f.write_text(json.dumps(plan));m.apply_review(f,root/'copy','copy')
 assert m.digest(root/'copy/42_01a.jpg')==sha
 plan['records'].append({'include':False,'reviewed':False,'source':str(src/'absent.jpg')});f.write_text(json.dumps(plan));m.apply_review(f,root/'excluded','copy')
 assert sorted(p.name for p in (root/'excluded').iterdir())==['42_01a.jpg','mapping.csv','processing-report.csv','processing-report.json']
 assert 'absent.jpg' not in (root/'excluded/mapping.csv').read_text()
 plan['records'].pop();f.write_text(json.dumps(plan))
 plan['records'].append({'include':True,'reviewed':False,'source':str(src/'unreviewed-missing.jpg')});f.write_text(json.dumps(plan));m.apply_review(f,root/'unreviewed-skipped','copy')
 assert sorted(p.name for p in (root/'unreviewed-skipped').iterdir())==['42_01a.jpg','mapping.csv','processing-report.csv','processing-report.json']
 assert 'unreviewed-missing.jpg' not in (root/'unreviewed-skipped/mapping.csv').read_text()
 plan['records'].pop();f.write_text(json.dumps(plan))
 m.apply_review(f,root/'crop','crop')
 with Image.open(root/'crop/42_01a.jpg') as out:assert out.size==(30,40) and out.getexif().get(274) is None
 plan['contrast']='none';plan['profiles']={'tall':{'label':'tall','width':100,'height':150,'background':'#ffffff','upscale':True}};base['profile_id']='tall';f.write_text(json.dumps(plan));m.apply_review(f,root/'sized','crop')
 with Image.open(root/'sized/42_01a.jpg') as out:assert out.size==(100,150)
 assert 'tall,100,150' in (root/'sized/mapping.csv').read_text()
 plan['records'].append(dict(base));f.write_text(json.dumps(plan))
 assert all('more than once' in r['message'] for r in m.apply_review(f,root/'duplicate','copy')['records'])
 path2=src/'camera_0002.JPG';Image.new('RGB',(80,120),'blue').save(path2)
 other=dict(base,source=str(path2),name=path2.name,sha256=m.digest(path2));plan['records'][1]=other;f.write_text(json.dumps(plan))
 assert all('Duplicate output' in r['message'] for r in m.apply_review(f,root/'collision','copy')['records'])
 other.update(view='b',profile_id='',crop=[0,0,80,120]);f.write_text(json.dumps(plan))
 assert all('inconsistent output sizes' in r['message'] for r in m.apply_review(f,root/'inconsistent','crop')['records'])
 other['profile_id']='tall';f.write_text(json.dumps(plan));m.apply_review(f,root/'two-views','crop')
 for filename in ('42_01a.jpg','42_01b.jpg'):
  with Image.open(root/'two-views'/filename) as out:assert out.size==(100,150)
 plan['records'].pop();base['crop']=[70,20,30,40];f.write_text(json.dumps(plan))
 assert 'outside image' in m.apply_review(f,root/'bounds','copy')['records'][0]['message']
 base['crop']=[10,20,30,40];base['sha256']='0'*64;f.write_text(json.dumps(plan))
 assert 'changed' in m.apply_review(f,root/'changed','copy')['records'][0]['message']
 assert m.digest(path)==sha
 r=[{'shape':'upright','flags':[]},{'shape':'upright','flags':[]},{'shape':'upright','flags':[]}]
 g=m.propose_groups(r,1,2);assert [len(x) for x in g]==[2,1] and [x['view'] for x in r]==['a','b','']
 image=np.full((480,650,3),220,dtype=np.uint8);image[140:390,220:340]=60
 detected=m.horizontal_center(image,[210,140,180,250],650)
 assert detected is not None and abs(detected-280)<=3,detected
 assert m.horizontal_center(np.full((480,650,3),220,dtype=np.uint8),[210,140,180,250],650) is None
 values=np.array([[[10,20,30],[50,80,110],[200,220,230]]],dtype=np.uint8)
 full=np.asarray(m.apply_contrast(Image.fromarray(values),'full'))
 assert all(full[:,:,k].min()==0 and full[:,:,k].max()==255 for k in range(3))
 assert np.array_equal(np.asarray(m.apply_contrast(Image.fromarray(values),'none')),values)
 pixels=np.full((1,2000,3),120,dtype=np.uint8);pixels[:,1000:]=200;pixels[:,0]=0;pixels[:,-1]=255
 stronger=np.asarray(m.apply_contrast(Image.fromarray(pixels),'0.5'))
 assert int(stronger[0,20,0])==0 and int(stronger[0,1200,0])==255
 flat=np.full((4,4,3),127,dtype=np.uint8)
 assert np.array_equal(np.asarray(m.apply_contrast(Image.fromarray(flat),'full')),flat)
 pattern=np.zeros((480,650,3),dtype=np.uint8)
 pattern[140:390,220:340]=np.repeat(((np.indices((250,120)).sum(axis=0)%2)*255).astype(np.uint8)[:,:,None],3,axis=2)
 clear=m.focus_measure(pattern,[210,140,180,250],280,650)
 blurry=m.focus_measure(m.cv2.GaussianBlur(pattern,(11,11),3),[210,140,180,250],280,650)
 assert clear is not None and blurry is not None and clear>400 and blurry<400
 assert m.focus_measure(pattern,None,280,650) is None
 profile={'label':'test','width':300,'height':400,'background':'#ffffff','upscale':False}
 fit=m.fit_to_profile(Image.new('RGB',(80,120),'red'),profile)
 assert fit.size==(300,400) and fit.getpixel((0,0))==(255,255,255) and fit.getpixel((150,200))==(255,0,0)
 assert fit.getpixel((109,200))==(255,255,255) and fit.getpixel((110,200))==(255,0,0)
 profile['upscale']=True; fit=m.fit_to_profile(Image.new('RGB',(80,120),'red'),profile)
 assert fit.size==(300,400) and fit.getpixel((150,0))==(255,0,0)
 try:m.validate_profile(dict(profile,width=0));raise AssertionError('invalid profile passed')
 except ValueError:pass
 m.make_review(src,root/'new-review','42',1,6)
 new=json.loads((root/'new-review'/'analysis.json').read_text())
 assert len(new['records'])==2 and all(r['include'] and r['reviewed'] for r in new['records'])
 old_page=root/'new-review'/'old-review.html';old_page.write_text('<script>const initial='+json.dumps(new)+';</script>')
 refreshed=root/'refreshed.html';m.refresh_review(old_page,refreshed)
 refreshed_text=refreshed.read_text();assert "plan_kind:'reviewed-output'" in refreshed_text and refreshed_text.count('data:image/jpeg;base64,')==4
 try:m.refresh_review(old_page,refreshed);raise AssertionError('refresh overwrote existing file')
 except ValueError:pass
 print('PASS: prechecked auctions, skipping unreviewed/excluded, review-page refresh, focus, centering, contrast and size profiles')
