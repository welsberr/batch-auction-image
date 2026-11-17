"""Exercise the desktop handoff with real processing and mocked file dialogs."""
import hashlib
import json
import queue
import sys
import tempfile
import time
import types
from pathlib import Path
from unittest.mock import Mock

from PIL import Image

# This test does not require a display or an installed Tk runtime.
tk = types.ModuleType('tkinter')
tk.filedialog = Mock()
tk.messagebox = Mock()
tk.ttk = Mock()
sys.modules['tkinter'] = tk
import jeff_auction_app as app_module


class Root:
    def deiconify(self):pass
    def lift(self):pass
    def after(self, *args):pass


class Bridge:
    def __init__(self):self.status={}
    def set_status(self,state,message,**details):self.status={'state':state,'message':message,**details}


with tempfile.TemporaryDirectory() as temp:
    base=Path(temp);source=base/'photos';source.mkdir()
    photo=source/'camera.jpg';Image.new('RGB',(60,80),'red').save(photo)
    digest=hashlib.sha256(photo.read_bytes()).hexdigest()
    plan={'version':1,'plan_kind':'reviewed-output','auction':'42','source_dir':str(source),'contrast':'none',
          'records':[{'id':0,'source':str(photo),'name':photo.name,'sha256':digest,'include':True,'reviewed':True,
                      'can':'1','view':'a','width':60,'height':80,'crop':[5,5,40,60]}]}
    tk.filedialog.askdirectory.return_value=str(base)
    tk.messagebox.askyesno.return_value=True
    app=app_module.AuctionApp.__new__(app_module.AuctionApp)
    app.root=Root();app.events=queue.Queue();app.running={'prepare':False,'copies':False}
    app.web_choosing=False;app.web_job=None;app.apply_button=Mock();app.write=Mock()
    bridge=Bridge();app.web_request(bridge,plan)
    assert bridge.status['state']=='running'
    for _ in range(500):
        app.drain()
        if not app.running['copies']:break
        time.sleep(.02)
    assert bridge.status['state']=='done',bridge.status
    output=base/'Auction-42-output'
    assert (output/'42_1a.jpg').is_file()
    assert json.loads((output/'reviewed-plan-used.json').read_text())==plan
    assert json.loads((output/'processing-report.json').read_text())['summary']['written']==1
    assert hashlib.sha256(photo.read_bytes()).hexdigest()==digest
    cancelled=Bridge();tk.filedialog.askdirectory.return_value='';app.web_request(cancelled,plan)
    assert cancelled.status['state']=='cancelled' and not app.running['copies']
    print('PASS: desktop handoff, output creation, saved plan and cancellation')
