#!/usr/bin/env python3
"""Simple desktop launcher for the local auction-photo proof of concept."""
from __future__ import annotations
import json, os, queue, shutil, subprocess, sys, tempfile, threading, webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from review_server import ReviewServer

SCRIPT=Path(__file__).resolve().with_name('auction_poc.py')


def unused_path(parent: Path, name: str) -> Path:
    candidate=parent/name
    for i in range(1,10000):
        if not candidate.exists():return candidate
        item=Path(name);candidate=parent/f'{item.stem}-{i}{item.suffix}'
    raise ValueError('Could not find an unused output folder name.')

class AuctionApp:
    def __init__(self, root):
        self.root=root;root.title('Auction Photo Review');root.geometry('900x700');root.minsize(740,560)
        self.events=queue.Queue();self.running={'prepare':False,'copies':False};self.servers=[];self.web_job=None;self.web_choosing=False
        self.source=tk.StringVar();self.review=tk.StringVar();self.auction=tk.StringVar();self.start=tk.StringVar(value='1');self.views=tk.StringVar(value='6');self.focus=tk.StringVar(value='400')
        self.plan=tk.StringVar();self.output=tk.StringVar();self.mode=tk.StringVar(value='crop')
        outer=ttk.Frame(root,padding=12);outer.pack(fill='both',expand=True)
        title=ttk.Label(outer,text='Auction Photo Review',font=('TkDefaultFont',16,'bold'));title.pack(anchor='w')
        ttk.Label(outer,text='Analyze → review in your browser → save a plan → create copies. Originals are not modified.').pack(anchor='w',pady=(4,10))
        analyze=ttk.LabelFrame(outer,text='1. Prepare photo review',padding=10);analyze.pack(fill='x',pady=4);analyze.columnconfigure(1,weight=1)
        self.row(analyze,0,'Original photos folder',self.source,'Choose…',self.choose_source)
        self.row(analyze,1,'New review folder',self.review,'Choose parent…',self.choose_review)
        row=ttk.Frame(analyze);row.grid(row=2,column=0,columnspan=3,sticky='w',pady=6)
        for label,var,width in [('Auction number',self.auction,9),('Starting can',self.start,7)]:
            ttk.Label(row,text=label).pack(side='left',padx=(0,4));ttk.Entry(row,textvariable=var,width=width).pack(side='left',padx=(0,14))
        ttk.Label(row,text='Photos per can').pack(side='left',padx=(0,4));ttk.Combobox(row,textvariable=self.views,values=('6','2'),state='readonly',width=4).pack(side='left',padx=(0,14))
        ttk.Label(row,text='Focus threshold').pack(side='left',padx=(0,4));ttk.Entry(row,textvariable=self.focus,width=7).pack(side='left')
        buttons=ttk.Frame(analyze);buttons.grid(row=3,column=0,columnspan=3,sticky='w')
        self.analyze_button=ttk.Button(buttons,text='Analyze photos and open review',command=self.run_analysis);self.analyze_button.pack(side='left',padx=(0,8))
        self.open_button=ttk.Button(buttons,text='Update/open existing review…',command=self.open_review);self.open_button.pack(side='left')
        produce=ttk.LabelFrame(outer,text='2. Create copies after review',padding=10);produce.pack(fill='x',pady=6);produce.columnconfigure(1,weight=1)
        self.row(produce,0,'Saved reviewed-plan.json',self.plan,'Choose…',self.choose_plan)
        self.row(produce,1,'New output folder',self.output,'Choose parent…',self.choose_output)
        modes=ttk.Frame(produce);modes.grid(row=2,column=0,columnspan=3,sticky='w',pady=5)
        ttk.Radiobutton(modes,text='Cropped, contrast-adjusted JPEGs',variable=self.mode,value='crop').pack(side='left',padx=(0,15))
        ttk.Radiobutton(modes,text='Renamed originals for PaintShop Pro',variable=self.mode,value='copy').pack(side='left')
        ttk.Label(produce,text='Only included, Reviewed photos are written. PaintShop copies do not apply crops, contrast, or size profiles.').grid(row=3,column=0,columnspan=3,sticky='w',pady=(2,5))
        self.apply_button=ttk.Button(produce,text='Create reviewed copies',command=self.run_apply);self.apply_button.grid(row=4,column=0,columnspan=3,sticky='w')
        logframe=ttk.LabelFrame(outer,text='Progress',padding=6);logframe.pack(fill='both',expand=True,pady=(6,0));self.log=tk.Text(logframe,height=8,wrap='word',state='disabled');scroll=ttk.Scrollbar(logframe,command=self.log.yview);self.log.configure(yscrollcommand=scroll.set);self.log.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.write('Choose originals and a NEW review folder. The starting can number must be verified.')
        root.after(150,self.drain)
    def row(self,parent,row,label,var,button,command):
        ttk.Label(parent,text=label).grid(row=row,column=0,sticky='w',padx=(0,8),pady=3)
        ttk.Entry(parent,textvariable=var).grid(row=row,column=1,sticky='ew',pady=3)
        ttk.Button(parent,text=button,command=command).grid(row=row,column=2,padx=(8,0),pady=3)
    def write(self,text):
        self.log.configure(state='normal');self.log.insert('end',str(text)+'\n');self.log.see('end');self.log.configure(state='disabled')
    def choose_source(self):
        value=filedialog.askdirectory(title='Choose the original photos folder')
        if value:
            self.source.set(value);parent=Path(value).parent
            if not self.review.get():self.review.set(str(unused_path(parent,'Auction-review')))
            if not self.output.get():self.output.set(str(unused_path(parent,'Auction-output')))
    def choose_review(self):
        value=filedialog.askdirectory(title='Choose a parent for the new review folder')
        if value:self.review.set(str(unused_path(Path(value),'Auction-review')))
    def choose_output(self):
        value=filedialog.askdirectory(title='Choose a parent for the new output folder')
        if value:self.output.set(str(unused_path(Path(value),'Auction-output')))
    def choose_plan(self):
        downloads=Path.home()/'Downloads';value=filedialog.askopenfilename(title='Choose the saved reviewed plan',initialdir=str(downloads if downloads.is_dir() else Path.home()),filetypes=[('JSON review plan','*.json'),('All files','*.*')])
        if value:self.plan.set(value)
    def open_review(self):
        value=filedialog.askopenfilename(title='Choose an existing review.html to update',filetypes=[('HTML review','*.html'),('All files','*.*')])
        if value:
            if not messagebox.askyesno('Update review','If your original review page is open, first save your work and download its reviewed plan. A new page will be created; use Load saved plan there to restore your choices. Continue?'):return
            existing=Path(value);output=unused_path(existing.parent,'review-updated.html')
            self.start_job(['refresh-review',str(existing),str(output)],output)
    def run_analysis(self):
        if not self.source.get().strip() or not self.review.get().strip():messagebox.showerror('Missing folder','Choose the originals and a new review folder.');return
        if not self.auction.get().strip():messagebox.showerror('Auction number','Enter an auction number.');return
        args=['analyze',self.source.get(),self.review.get(),'--auction',self.auction.get().strip(),'--start-can',self.start.get().strip(),'--views',self.views.get(),'--focus-threshold',self.focus.get().strip()]
        self.start_job(args,Path(self.review.get())/'review.html')
    def run_apply(self):
        if self.web_choosing:messagebox.showinfo('Choose output','Finish choosing the output folder for the review first.');return
        if not self.plan.get().strip() or not self.output.get().strip():messagebox.showerror('Missing plan or folder','Choose a saved review plan and a new output folder.');return
        self.start_job(['apply',self.plan.get(),self.output.get(),'--mode',self.mode.get()],Path(self.output.get()))
    def serve_review(self, page):
        bridge=ReviewServer(page,lambda server,plan:self.events.put(('web_request',server,plan)))
        self.servers.append(bridge)
        self.write('Review opened with local processing enabled. Keep this app open.')
        def open_browser():
            try:
                if not webbrowser.open(bridge.url):self.events.put(('log','prepare',f'Open this address in a browser: {bridge.url}'))
            except Exception as exc:self.events.put(('log','prepare',f'Could not open the review: {exc}. Address: {bridge.url}'))
        threading.Thread(target=open_browser,daemon=True).start()
    def web_request(self,bridge,plan):
        if self.running['copies'] or self.web_choosing:
            bridge.set_status('error','Another output job is already running. Wait for it to finish and try again.');return
        self.web_choosing=True
        try:self.choose_web_output(bridge,plan)
        except Exception as exc:bridge.set_status('error',f'Could not start processing: {exc}')
        finally:self.web_choosing=False
    def choose_web_output(self,bridge,plan):
        self.root.deiconify();self.root.lift()
        parent=filedialog.askdirectory(parent=self.root,title='Choose where to create the new auction output folder')
        if not parent:
            bridge.set_status('cancelled','No folder chosen. Click Create output images to try again.');return
        auction=str(plan.get('auction','auction'))
        import re
        if not re.fullmatch(r'[A-Za-z0-9-]+',auction):
            bridge.set_status('error','The auction number is invalid. Correct it and save a new reviewed plan.');return
        output=unused_path(Path(parent),f'Auction-{auction}-output')
        if not messagebox.askyesno('Create output images',f"Create cropped JPEGs for {len(plan['records'])} reviewed photos in:\n\n{output}\n\nThe saved crop, contrast and size settings will be applied. Originals will not be changed.",parent=self.root):
            bridge.set_status('cancelled','Processing cancelled. Click Create output images to try again.');return
        try:
            fd,plan_path=tempfile.mkstemp(prefix='auction-reviewed-',suffix='.json')
            with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(plan,f,ensure_ascii=False,indent=2)
        except OSError as exc:
            bridge.set_status('error',f'Could not save the processing plan: {exc}');return
        self.web_job=(bridge,Path(plan_path),output)
        bridge.set_status('running',f'Starting output in {output}',output=str(output))
        self.start_job(['apply',plan_path,str(output),'--mode','crop'],output)
    def start_job(self,args,review_to_open):
        role='copies' if args[0]=='apply' else 'prepare'
        if self.running[role]:
            messagebox.showinfo('Already running','That operation is already running. Check the Progress box.');return
        self.running[role]=True
        if role=='prepare':
            self.analyze_button.configure(state='disabled');self.open_button.configure(state='disabled')
            self.write('[Photo preparation] Starting. This can take several minutes; progress appears below. You can still create copies from a previously saved plan.')
        else:
            self.apply_button.configure(state='disabled')
            self.write('[Create copies] Starting. The button will be available again when this operation finishes.')
        def worker():
            try:
                env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
                proc=subprocess.Popen([sys.executable,'-u',str(SCRIPT),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env)
                assert proc.stdout is not None
                for line in proc.stdout:self.events.put(('log',role,line.rstrip()))
                self.events.put(('done',role,(proc.wait(),review_to_open)))
            except Exception as exc:self.events.put(('error',role,str(exc)))
        try:threading.Thread(target=worker,daemon=True).start()
        except Exception as exc:self.events.put(('error',role,str(exc)))
    def drain(self):
        try:
            while True:
                kind,role,value=self.events.get_nowait()
                if kind=='web_request':self.web_request(role,value);continue
                label='Photo preparation' if role=='prepare' else 'Create copies'
                if kind=='log':
                    self.write(f'[{label}] {value}')
                    if role=='copies' and self.web_job:
                        bridge,_,output=self.web_job;bridge.set_status('running',value,output=str(output))
                elif kind in ('done','error'):
                    self.running[role]=False
                    if role=='prepare':self.analyze_button.configure(state='normal');self.open_button.configure(state='normal')
                    else:self.apply_button.configure(state='normal')
                    if kind=='error':
                        if role=='copies' and self.web_job:
                            bridge,plan_path,output=self.web_job;bridge.set_status('error',f'Could not run: {value}. Plan kept at {plan_path}',output=str(output));self.web_job=None
                        self.write(f'[{label}] Error: {value}');messagebox.showerror('Could not run',value)
                    else:
                        code,review=value
                        if code:
                            if role=='copies' and self.web_job:
                                bridge,plan_path,output=self.web_job;bridge.set_status('error',f'Processing failed. See the desktop progress log. Plan kept at {plan_path}',output=str(output));self.web_job=None
                            self.write(f'[{label}] Failed (exit {code}). Read the details above.');messagebox.showerror('Operation failed','Read the progress log for details.')
                        elif role=='prepare' and review:
                            if review.is_file():
                                self.write('[Photo preparation] Finished. Opening the review in your browser.')
                                try:self.serve_review(review)
                                except Exception as exc:self.write(f'[Photo preparation] Could not start local review: {exc}');messagebox.showerror('Could not open review',str(exc))
                            else:self.write(f'[Photo preparation] The expected review file was not found: {review}');messagebox.showerror('Review not found','The expected review file was not created. Read the Progress box.')
                        else:
                            try:
                                if review is None:raise ValueError('Report folder unavailable')
                                report_path=review/'processing-report.json'
                                summary=json.loads(report_path.read_text(encoding='utf-8'))['summary']
                                if self.web_job:
                                    bridge,plan_path,output=self.web_job
                                    try:
                                        with plan_path.open('rb') as src,(output/'reviewed-plan-used.json').open('xb') as dst:shutil.copyfileobj(src,dst)
                                        plan_path.unlink();plan_message='The plan used is saved in the output folder.'
                                    except OSError as exc:plan_message=f'Could not copy the plan into output: {exc}. Plan kept at {plan_path}.'
                                    bridge.set_status('done',f"Created {summary['written']} photos; {summary['errors']} errors. {plan_message}",output=str(output),summary=summary)
                                    self.web_job=None
                                text=(f"Created {summary['written']} photos. Errors: {summary['errors']}; "
                                      f"excluded: {summary['skipped_excluded']}; unreviewed: {summary['skipped_unreviewed']}; "
                                      f"with analysis warnings: {summary['warning_records']}.\n\n"
                                      f"See {review/'processing-report.csv'} for details.")
                                self.write('[Create copies] '+text.replace('\n',' '))
                                if summary['errors'] or summary['skipped_unreviewed'] or summary['warning_records'] or not summary['written']:messagebox.showwarning('Finished with items to review',text)
                                else:messagebox.showinfo('Finished',text)
                            except (OSError,ValueError,KeyError,TypeError) as exc:
                                if self.web_job:
                                    bridge,plan_path,output=self.web_job;bridge.set_status('error',f'Finished, but the report could not be read: {exc}. Plan kept at {plan_path}',output=str(output));self.web_job=None
                                self.write(f'[Create copies] Finished, but the report could not be read: {exc}')
                                messagebox.showwarning('Check the output','The task finished, but its report could not be read. Check the Progress box and output folder.')
        except queue.Empty:pass
        finally:self.root.after(150,self.drain)

if __name__=='__main__':
    root=tk.Tk();AuctionApp(root);root.mainloop()
