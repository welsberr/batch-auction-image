#!/usr/bin/env python3
"""Conservative local proof of concept for auction photographs."""
from __future__ import annotations
import argparse, base64, csv, hashlib, html, json, math, os, re, shutil, sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageDraw

EXTENSIONS={'.jpg','.jpeg','.png','.tif','.tiff'}
DEFAULT_FOCUS_THRESHOLD=400.0

def natural(p):
    return [(1,int(x)) if x.isdigit() else (0,x.casefold()) for x in re.split(r'(\d+)',p.name)]

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def horizontal_center(rgb, bbox, original_width):
    """Estimate can center from outer vertical edges, rejecting weak candidates.

    The foreground box is used only as a broad search region: background to
    the right can make its midpoint substantially biased.
    """
    if not bbox:
        return None
    height, width = rgb.shape[:2]
    scale = width / original_width
    bx, by, bw, bh = (round(v * scale) for v in bbox)
    y0, y1 = max(0, by + round(bh * .2)), min(height, by + round(bh * .8))
    if bw < 10 or y1 <= y0:
        return None
    gray = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (3, 3), 0)
    sobel = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    score = np.convolve(sobel[y0:y1, :].mean(axis=0), np.ones(5)/5, mode='same')
    def candidates(lo, hi):
        peaks = [p for p in range(max(1, lo), min(width-1, hi)) if score[p] > score[p-1] and score[p] >= score[p+1]]
        threshold = max(15, max((score[p] for p in peaks), default=0) * .3)
        return [p for p in peaks if score[p] >= threshold]
    left_peaks = candidates(bx-12, int(bx+bw*.40))
    right_peaks = candidates(int(bx+bw*.55), bx+bw+12)
    if not left_peaks or not right_peaks:
        return None
    left, right = min(left_peaks), max(right_peaks)
    if not .35*bw <= right-left <= 1.2*bw:
        return None
    return round((left + right) / (2 * scale))

def focus_measure(rgb, bbox, center_x, original_width):
    """Measure local edge detail on a 650-pixel thumbnail; not a focus diagnosis."""
    if not bbox:
        return None
    height,width=rgb.shape[:2]
    scale=width/original_width
    x,y,bw,bh=bbox
    x0=max(0,round((center_x-.3*bw)*scale));x1=min(width,round((center_x+.3*bw)*scale))
    y0=max(0,round((y+.1*bh)*scale));y1=min(height,round((y+.9*bh)*scale))
    if x1-x0<8 or y1-y0<8:
        return None
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    return round(float(cv2.Laplacian(gray[y0:y1,x0:x1],cv2.CV_64F).var()),1)

def make_focus_detail(path, target, crop):
    """Save a larger, unsharpened crop for visual focus review."""
    with Image.open(path) as opened:
        oriented=ImageOps.exif_transpose(opened).convert('RGB')
        x,y,w,h=crop
        detail=oriented.crop((x,y,x+w,y+h))
        detail.thumbnail((1200,1200),Image.Resampling.LANCZOS)
        detail.save(target,'JPEG',quality=90)

def analyze(path, thumb):
    with Image.open(path) as opened:
        opened.load()
        image=ImageOps.exif_transpose(opened).convert('RGB')
    W,H=image.size
    image.thumbnail((650,650),Image.Resampling.LANCZOS)
    rgb=np.asarray(image); h,w=rgb.shape[:2]
    lab=cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB).astype(np.float32)
    strips=np.concatenate((lab[:,int(w*.24):int(w*.32)],lab[:,int(w*.68):int(w*.76)]),axis=1)
    bg=np.median(strips,axis=1)
    diff=np.linalg.norm(lab-bg[:,None,:],axis=2)
    mask=np.uint8(diff>20)*255
    mask[:int(h*.20),:]=0;mask[int(h*.86):,:]=0;mask[:,:int(w*.30)]=0;mask[:,int(w*.70):]=0
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contours=[c for c in contours if cv2.contourArea(c)>50]
    flags=[]
    if not contours:
        bbox=None; crop=[0,0,W,H]; shape='unknown'; flags.append('No can-like region found; crop is the whole image')
    else:
        x,y,bw,bh=cv2.boundingRect(max(contours,key=cv2.contourArea))
        # Add ample padding. Coordinates always describe the EXIF-oriented image.
        pad_x=max(8,round(bw*.22));pad_y=max(8,round(bh*.18))
        x0=max(0,round((x-pad_x)*W/w));y0=max(0,round((y-pad_y)*H/h))
        x1=min(W,math.ceil((x+bw+pad_x)*W/w));y1=min(H,math.ceil((y+bh+pad_y)*H/h))
        crop=[x0,y0,x1-x0,y1-y0]
        bbox=[round(x*W/w),round(y*H/h),round(bw*W/w),round(bh*H/h)]
        ratio=bh/bw
        shape='upright' if ratio>1.12 else ('end' if ratio<1.02 else 'unknown')
        if shape=='unknown': flags.append('Ambiguous shape')
        if x<=w*.305 or x+bw>=w*.695 or y<=h*.205 or y+bh>=h*.855:
            flags.append('Detected region touches analysis boundary; check crop')
    center=horizontal_center(rgb,bbox,W)
    if center is None:
        center=round(bbox[0]+bbox[2]/2) if bbox else round(W/2)
        flags.append('Can edges were unclear; check horizontal center')
    else:
        crop[0]=max(0,min(W-crop[2],round(center-crop[2]/2)))
        if abs(crop[0]+crop[2]/2-center)>1:
            flags.append('Cannot fully center crop at the image edge')
    image.save(thumb,'JPEG',quality=80)
    with Image.open(thumb) as saved_thumbnail:
        focus=focus_measure(np.asarray(saved_thumbnail.convert('RGB')),bbox,center,W)
    return {'width':W,'height':H,'box':bbox,'crop':crop,'center_x':center,'shape':shape,'focus_score':focus,'flags':flags}

def propose_groups(records,start,views):
    # Sequence evidence only: closing a group after its run of end-shaped photos.
    groups=[];current=[];end_seen=False
    for r in records:
        if views==2 and len(current)==2:
            groups.append(current); current=[]; end_seen=False
        if current and end_seen and r['shape']=='upright':
            if views==6:
                groups.append(current);current=[];end_seen=False
        current.append(r)
        if r['shape']=='end': end_seen=True
    if current:groups.append(current)
    for i,group in enumerate(groups):
        shapes=[r['shape'] for r in group]
        common=(shapes==['upright']*4+['end']*2) if views==6 else (shapes==['upright']*2)
        for j,r in enumerate(group):
            r['group']=i+1;r['can']=str(start+i);r['view']='abcdef'[j] if common else ''
            if not common:r['flags'].append('Irregular group: assign can and view manually')
            if views==2:r['flags'].append('Two-photo mode: verify front and seam; seam is not detected automatically')
    return groups

def make_review(source, out, auction, start, views, focus_threshold=DEFAULT_FOCUS_THRESHOLD):
    source=source.resolve();out=out.resolve()
    if not source.is_dir(): raise ValueError('Input must be a directory')
    if out==source or source in out.parents:raise ValueError('Review folder must be outside the original photo folder')
    files=sorted((p for p in source.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS),key=natural)
    if not files:raise ValueError('No supported images found')
    out.mkdir(parents=True,exist_ok=False); thumbs=out/'thumbs';thumbs.mkdir();details=out/'focus';details.mkdir()
    records=[]; previous=None; analysis_rows=[]
    for i,path in enumerate(files):
        error=''
        try:
            rec=analyze(path,thumbs/f'{i:04d}.jpg')
            stat=path.stat();rec.update(id=i,source=str(path),name=path.name,thumbnail=f'thumbs/{i:04d}.jpg',size=stat.st_size,sha256=digest(path),include=True,reviewed=True)
            if rec['focus_score'] is None or rec['focus_score']<focus_threshold:
                try:
                    make_focus_detail(path,out/f'focus/{i:04d}.jpg',rec['crop'])
                    rec['focus_detail']=f'focus/{i:04d}.jpg'
                except Exception as exc:rec['flags'].append(f'Focus detail preview unavailable: {exc}')
        except Exception as exc:
            error=str(exc) or type(exc).__name__
            # Keep its position in the sequence so later proposals are not silently shifted.
            placeholder=Image.new('RGB',(500,300),'#ddd9d2')
            ImageDraw.Draw(placeholder).text((18,120),'IMAGE COULD NOT BE ANALYZED\nExcluded: see analysis report',fill='#7b2020')
            placeholder.save(thumbs/f'{i:04d}.jpg','JPEG')
            rec={'id':i,'source':str(path),'name':path.name,'thumbnail':f'thumbs/{i:04d}.jpg','size':0,'sha256':'',
                 'include':False,'reviewed':False,'width':1,'height':1,'box':None,'crop':[0,0,1,1],
                 'center_x':0,'shape':'unknown','focus_score':None,'flags':[f'Analysis failed; excluded: {error}']}
            print(f'Analysis error for {path.name}: {error}',flush=True)
        m=re.search(r'(\d+)$',path.stem)
        if m and previous is not None and int(m.group(1))!=previous+1:
            rec['flags'].append(f'Camera filename gap before this photo (previous number {previous})')
        previous=int(m.group(1)) if m else None
        records.append(rec);analysis_rows.append({'source':str(path),'status':'error' if error else 'analyzed','message':error})
        if (i+1)%50==0:print(f'Analyzed {i+1}/{len(files)}',flush=True)
    groups=propose_groups(records,start,views)
    data={'version':1,'source_dir':str(source),'auction':str(auction),'views':views,'contrast':'full','focus_threshold':focus_threshold,'records':records}
    (out/'analysis.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    with (out/'analysis-report.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['source','status','message']);w.writerows((r['source'],r['status'],r['message']) for r in analysis_rows)
    with (out/'crop-proposals.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['original','provisional_can','provisional_view','shape','focus_score','focus_warning','left','top','width','height','image_width','image_height','flags'])
        for r in records:w.writerow([r['name'],r['can'],r['view'],r['shape'],r['focus_score'],r['focus_score'] is None or r['focus_score']<focus_threshold,*r['crop'],r['width'],r['height'],'; '.join(r['flags'])])
    template=(Path(__file__).parent/'review_template.html').read_text(encoding='utf-8')
    embedded=json.dumps(data,ensure_ascii=False).replace('</','<\\/')
    images=['data:image/jpeg;base64,'+base64.b64encode((out/r['thumbnail']).read_bytes()).decode('ascii') for r in records]
    focus_images=['data:image/jpeg;base64,'+base64.b64encode((out/r['focus_detail']).read_bytes()).decode('ascii') if r.get('focus_detail') else None for r in records]
    page=template.replace('/*REVIEW_DATA*/',embedded).replace('/*THUMBNAIL_DATA*/',json.dumps(images)).replace('/*FOCUS_DETAIL_DATA*/',json.dumps(focus_images))
    (out/'review.html').write_text(page,encoding='utf-8')
    print(f'Created {out}: {len(records)} images, {len(groups)} provisional groups, {sum(bool(r["flags"]) for r in records)} images with other flags, {sum(r["focus_score"] is None or r["focus_score"]<focus_threshold for r in records)} focus warnings.')
    print(f"Analysis errors: {sum(r['status']=='error' for r in analysis_rows)}; see {out/'analysis-report.csv'}.")
    print('Open review.html. Analyzed photos are prechecked; inspect warnings and correct or exclude problems.')

def refresh_review(existing, output):
    """Create a new review page from an existing page's embedded data and photos."""
    existing=existing.resolve();output=output.resolve()
    if output.exists():raise ValueError('Updated review already exists; choose a new file')
    if not existing.is_file():raise ValueError('Existing review page not found')
    content=existing.read_text(encoding='utf-8')
    decoder=json.JSONDecoder()
    def embedded(name,required=True):
        marker='const '+name+'='
        pos=content.find(marker)
        if pos<0:
            if required:raise ValueError(f'Existing page has no {name}; select an auction review page')
            return None
        try:return decoder.raw_decode(content[pos+len(marker):].lstrip())[0]
        except json.JSONDecodeError as exc:raise ValueError(f'Could not read {name} from existing review') from exc
    data=embedded('initial')
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('records'),list) or not isinstance(data.get('source_dir'),str):raise ValueError('Unsupported review data')
    source=Path(data['source_dir']).resolve()
    if output==source or source in output.parents:raise ValueError('Updated review must be outside the original photo folder')
    records=data['records'];images=embedded('thumbnailData',False);focus=embedded('focusDetailData',False)
    def local_image(relative):
        file=(existing.parent/relative).resolve()
        if existing.parent not in file.parents or not file.is_file():raise ValueError(f'Local review image missing: {relative}')
        return 'data:image/jpeg;base64,'+base64.b64encode(file.read_bytes()).decode('ascii')
    if images is None:images=[local_image(r['thumbnail']) for r in records]
    if focus is None:focus=[local_image(r['focus_detail']) if r.get('focus_detail') else None for r in records]
    if not isinstance(images,list) or len(images)!=len(records) or not isinstance(focus,list) or len(focus)!=len(records):raise ValueError('Review image data does not match its records')
    if any(not isinstance(x,str) or not x.startswith('data:image/jpeg;base64,') for x in images) or any(x is not None and (not isinstance(x,str) or not x.startswith('data:image/jpeg;base64,')) for x in focus):raise ValueError('Review image data is invalid')
    template=Path(__file__).parent/'review_template.html'
    page=template.read_text(encoding='utf-8').replace('/*REVIEW_DATA*/',json.dumps(data,ensure_ascii=False).replace('</','<\\/')).replace('/*THUMBNAIL_DATA*/',json.dumps(images)).replace('/*FOCUS_DETAIL_DATA*/',json.dumps(focus))
    with output.open('x',encoding='utf-8') as f:f.write(page)
    print(f'Updated review created: {output}. Load your saved plan to restore your choices.')

def apply_contrast(image, contrast):
    """Stretch each RGB channel, optionally excluding 0.5% of pixels at each end."""
    if contrast == 'none':
        return image
    if contrast not in ('full', '0.5'):
        raise ValueError('Invalid contrast setting')
    return ImageOps.autocontrast(image, cutoff=0 if contrast == 'full' else .5)

def validate_profile(profile):
    if not isinstance(profile,dict):raise ValueError('Invalid size profile')
    width,height=profile.get('width'),profile.get('height')
    if type(width)!=int or type(height)!=int or not (1<=width<=10000 and 1<=height<=10000) or width*height>40000000:
        raise ValueError('Profile dimensions must be positive integers, at most 10,000 pixels per side and 40 megapixels')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(profile.get('background',''))):raise ValueError('Profile background must be a hex color like #ffffff')
    if type(profile.get('upscale',False))!=bool:raise ValueError('Invalid upscale setting')
    return profile

def fit_to_profile(image,profile):
    """Fit the whole crop in a fixed canvas, centered and without distortion."""
    validate_profile(profile)
    width,height=profile['width'],profile['height']
    scale=min(width/image.width,height/image.height)
    if not profile.get('upscale',False):scale=min(scale,1)
    size=(max(1,min(width,round(image.width*scale))),max(1,min(height,round(image.height*scale))))
    fitted=image.resize(size,Image.Resampling.LANCZOS) if size!=image.size else image
    canvas=Image.new('RGB',(width,height),profile['background'])
    canvas.paste(fitted,((width-size[0])//2,(height-size[1])//2))
    return canvas

def apply_review(plan,dest,mode,contrast_override=None):
    data=json.loads(plan.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('records'),list):raise ValueError('Invalid review file')
    auction=str(data.get('auction',''))
    if not re.fullmatch(r'[A-Za-z0-9-]+',auction):raise ValueError('Auction must contain only letters, digits, or hyphens')
    if mode not in ('copy','crop'):raise ValueError('Invalid output mode')
    contrast=contrast_override or data.get('contrast','full')
    if contrast not in ('none','full','0.5'):raise ValueError('Invalid contrast setting')
    applied_contrast=contrast if mode=='crop' else 'none (byte-identical copy)'
    profiles=data.get('profiles',{})
    if not isinstance(profiles,dict):raise ValueError('Invalid size profiles')
    if not isinstance(data.get('source_dir'),str) or not data['source_dir']:raise ValueError('Invalid source folder in review file')
    source=Path(data['source_dir']).resolve();dest=dest.resolve()
    if dest==source or source in dest.parents:raise ValueError('Output must be outside original photo folder')
    if dest.exists():raise ValueError('Output directory already exists; choose a new directory')
    threshold=data.get('focus_threshold',DEFAULT_FOCUS_THRESHOLD)
    if not isinstance(threshold,(int,float)) or isinstance(threshold,bool) or not math.isfinite(threshold) or threshold<0:threshold=DEFAULT_FOCUS_THRESHOLD
    rows=[];items=[]
    for index,r in enumerate(data['records'],1):
        if index==1 or index%25==0:print(f'Checking originals and plan: {index}/{len(data["records"])}',flush=True)
        row={'index':index,'source':'','output':'','status':'error','message':'','warnings':[]};rows.append(row)
        try:
            if not isinstance(r,dict):raise ValueError('Photo entry is not an object')
            row['source']=str(r.get('source') or r.get('name') or '')
            flags=r.get('flags',[])
            if isinstance(flags,list):row['warnings'].extend(str(flag) for flag in flags)
            if isinstance(r.get('margin_warning'),str) and r['margin_warning']:row['warnings'].append(r['margin_warning'])
            if 'focus_score' in r:
                score=r['focus_score']
                if score is None:row['warnings'].append('Focus could not be assessed; inspect the photo')
                elif isinstance(score,(int,float)) and not isinstance(score,bool) and math.isfinite(score) and score<threshold:row['warnings'].append(f'Low image detail (focus score {score}, threshold {threshold}); inspect the photo')
            if type(r.get('include')) is not bool:raise ValueError('Include must be true or false')
            if not r['include']:
                row.update(status='skipped_excluded',message='Excluded from output');continue
            if type(r.get('reviewed',False)) is not bool:raise ValueError('Reviewed must be true or false')
            if not r.get('reviewed',False):
                row.update(status='skipped_unreviewed',message='Not marked reviewed');continue
            if not isinstance(r.get('source'),str) or not r['source']:raise ValueError('Source filename is missing')
            src=Path(r['source']).resolve()
            if src.parent!=source or not src.is_file():raise ValueError(f'Source is missing or outside source folder: {src}')
            if digest(src)!=r.get('sha256'):raise ValueError(f'Source changed since analysis: {src.name}')
            if mode=='crop' and src.suffix.lower() not in ('.jpg','.jpeg'):raise ValueError(f'Crop mode currently supports JPEG only: {src.name}')
            can=str(r.get('can',''));view=str(r.get('view','')).lower()
            if not re.fullmatch(r'[0-9]+',can) or view not in 'abcdef' or len(view)!=1:raise ValueError(f'Invalid can number or view for {src.name}')
            view_kind=r.get('view_kind')
            if view_kind is not None:
                if view_kind not in ('side','end'):raise ValueError(f'Confirm whether {src.name} is a side or end view')
                permitted='ef' if view_kind=='end' else ('ab' if data.get('views')==2 else 'abcd')
                if view not in permitted:raise ValueError(f'View letter {view} is incompatible with the selected photo type for {src.name}')
            name=f'{auction}_{can}{view}{src.suffix.lower()}';row['output']=name
            box=r.get('crop');W,H=r.get('width'),r.get('height')
            if not isinstance(box,list) or len(box)!=4 or any(type(v)!=int for v in box) or type(W)!=int or type(H)!=int:raise ValueError(f'Invalid crop for {src.name}')
            x,y,w,h=box
            if x<0 or y<0 or w<=0 or h<=0 or x+w>W or y+h>H:raise ValueError(f'Crop outside image: {src.name}')
            profile_id=r.get('profile_id','')
            if not isinstance(profile_id,str):raise ValueError(f'Invalid profile for {src.name}')
            if profile_id:
                if profile_id not in profiles:raise ValueError(f'Size profile is missing for {src.name}')
                validate_profile(profiles[profile_id])
            items.append((r,src,name,row))
        except Exception as exc:row['message']=str(exc) or type(exc).__name__
    # Reject every participant in a collision rather than silently choosing one.
    from collections import Counter
    source_counts=Counter(src for r,src,name,row in items)
    name_counts=Counter(name.casefold() for r,src,name,row in items)
    sizes_by_can={}
    if mode=='crop':
        for r,src,name,row in items:
            profile=profiles.get(r.get('profile_id',''))
            sizes_by_can.setdefault(str(r['can']),set()).add((profile['width'],profile['height']) if profile else None)
    for r,src,name,row in items:
        problems=[]
        if source_counts[src]>1:problems.append(f'Source appears more than once: {src.name}')
        if name_counts[name.casefold()]>1:problems.append(f'Duplicate output filename: {name}')
        if mode=='crop' and len(sizes_by_can[str(r['can'])])>1:problems.append(f'Can {r["can"]} has inconsistent output sizes or a missing size profile')
        if problems:row['message']='; '.join(problems)
    dest.mkdir(parents=True,exist_ok=False)
    written=[]
    for output_index,(r,src,name,row) in enumerate(items,1):
        if output_index==1 or output_index%25==0:print(f'Processing photos: {output_index}/{len(items)}',flush=True)
        if row['message']:continue
        target=dest/name;created=False
        try:
            if digest(src)!=r['sha256']:raise ValueError(f'Source changed since analysis: {src.name}')
            if mode=='copy':
                with src.open('rb') as inp, target.open('xb') as out:
                    created=True;shutil.copyfileobj(inp,out)
                if digest(target)!=r['sha256']:raise ValueError('Copy verification failed')
            else:
                with Image.open(src) as im:
                    icc=im.info.get('icc_profile');oriented=ImageOps.exif_transpose(im)
                    if oriented.size!=(r['width'],r['height']):raise ValueError('Actual image dimensions differ from the review plan')
                    exif=oriented.getexif();exif.pop(274,None)
                    x,y,w,h=r['crop'];result=oriented.crop((x,y,x+w,y+h)).convert('RGB')
                    result=apply_contrast(result,contrast)
                    if r.get('profile_id'):result=fit_to_profile(result,profiles[r['profile_id']])
                    params={'quality':95,'subsampling':0,'exif':exif.tobytes()}
                    if icc:params['icc_profile']=icc
                    with target.open('xb') as out:
                        created=True;result.save(out,'JPEG',**params)
            row.update(status='written',message='Created successfully');written.append((r,src,name))
        except Exception as exc:
            row['message']=str(exc) or type(exc).__name__
            if created:
                try:target.unlink(missing_ok=True)
                except OSError as cleanup:row['message']+=f'; could not remove incomplete output: {cleanup}'
    summary={'total':len(rows),'written':sum(r['status']=='written' for r in rows),'errors':sum(r['status']=='error' for r in rows),'skipped_excluded':sum(r['status']=='skipped_excluded' for r in rows),'skipped_unreviewed':sum(r['status']=='skipped_unreviewed' for r in rows),'warning_records':sum(bool(r['warnings']) for r in rows)}
    report={'version':1,'source_plan':str(plan.resolve()),'mode':mode,'contrast':applied_contrast,'summary':summary,'records':rows}
    with (dest/'mapping.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['original','output','mode','contrast','size_profile','output_width','output_height','left','top','width','height','sha256_original'])
        for r,src,name in written:
            profile=profiles.get(r.get('profile_id','')) if mode=='crop' else None
            w.writerow([str(src),name,mode,applied_contrast,profile.get('label','') if profile else '',profile['width'] if profile else '',profile['height'] if profile else '',*r['crop'],r['sha256']])
    with (dest/'processing-report.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,ensure_ascii=False)
    with (dest/'processing-report.csv').open('x',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['entry','source','output','status','message','analysis warnings (may have been resolved)'])
        for row in rows:w.writerow([row['index'],row['source'],row['output'],row['status'],row['message'],'; '.join(row['warnings'])])
    for row in rows:
        if row['status']=='error':print(f"Error in plan entry {row['index']} ({row['source']}): {row['message']}")
    print(f"Finished: {summary['written']} written, {summary['errors']} errors, {summary['skipped_excluded']} excluded, {summary['skipped_unreviewed']} unreviewed, {summary['warning_records']} with analysis warnings. Report: {dest/'processing-report.csv'}")
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);sp=p.add_subparsers(dest='command',required=True)
    a=sp.add_parser('analyze');a.add_argument('source',type=Path);a.add_argument('review_dir',type=Path);a.add_argument('--auction',required=True);a.add_argument('--start-can',type=int,required=True);a.add_argument('--views',type=int,choices=[2,6],default=6);a.add_argument('--focus-threshold',type=float,default=DEFAULT_FOCUS_THRESHOLD,help='Low-detail warning threshold on 650-pixel thumbnails (default: 400; adjust after testing)')
    c=sp.add_parser('refresh-review',help='Create an updated review page without reanalyzing photos');c.add_argument('existing',type=Path);c.add_argument('output',type=Path)
    b=sp.add_parser('apply');b.add_argument('review_json',type=Path);b.add_argument('output_dir',type=Path);b.add_argument('--mode',choices=['copy','crop'],default='copy');b.add_argument('--contrast',choices=['none','full','0.5'],help='Override saved contrast for crop mode: full (exact; default), 0.5 (clip 0.5%% at each end), or none')
    args=p.parse_args()
    try:
        if args.command=='analyze':
            if not re.fullmatch(r'[A-Za-z0-9-]+',args.auction) or args.start_can<0:raise ValueError('Invalid auction or starting can')
            if not math.isfinite(args.focus_threshold) or args.focus_threshold<0:raise ValueError('Focus threshold must be a finite nonnegative number')
            make_review(args.source,args.review_dir,args.auction,args.start_can,args.views,args.focus_threshold)
        elif args.command=='refresh-review':refresh_review(args.existing,args.output)
        else:apply_review(args.review_json,args.output_dir,args.mode,args.contrast)
    except (ValueError,RuntimeError,OSError) as e:
        print('Error:',e,file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
