// Exercise the actual review script with a small DOM stand-in.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
class Element {
  constructor(tag='div') { this.tagName=tag; this.children=[]; this.style={}; this.dataset={}; this.value=''; this.checked=false; this.disabled=false; this.classList={toggle(){}}; }
  append(...items){this.children.push(...items)} replaceChildren(){this.children=[]} setAttribute(k,v){this[k]=v} click(){}
}
const ids = {}, bodies = [];
const document = {getElementById:id=>ids[id]||(ids[id]=new Element()), createElement:tag=>new Element(tag), addEventListener(){}};
const initial={version:1,auction:'42',views:6,source_dir:'/photos',contrast:'none',focus_threshold:400,profiles:{},records:[{id:0,name:'a.jpg',source:'/photos/a.jpg',sha256:'abc',group:1,include:true,reviewed:true,focus_score:500,can:'1',view:'a',shape:'upright',flags:[],box:[10,10,20,30],center_x:20,crop:[5,5,30,40],width:60,height:80,thumbnail:''}]};
const context={document,location:{protocol:'http:',hostname:'127.0.0.1'},console,assert,initialData:initial,bodies,
  confirm:()=>true,alert:message=>{throw Error(message)},setTimeout:()=>{},Blob:class{},URL:{createObjectURL:()=>'',revokeObjectURL(){}},
  fetch:async(url,options)=>{if(url==='process'){bodies.push(JSON.parse(options.body));return {ok:true,json:async()=>({state:'choosing'})}}return {ok:true,json:async()=>({state:'done',message:'Finished',output:'/output'})}}};
let html=fs.readFileSync(__dirname+'/review_template.html','utf8');
let script=html.split('<script>')[1].split('</script>')[0].replace('/*REVIEW_DATA*/','initialData').replace('/*THUMBNAIL_DATA*/','[]').replace('/*FOCUS_DETAIL_DATA*/','[]');
script += `
(async()=>{
 assert(processButton.disabled,'disabled before a reviewed plan');
 document.getElementById('download').onclick();
 assert(!processButton.disabled,'enabled after saving');
 data.records[0].can='2'; updateOutputButton();
 assert(processButton.disabled,'a changed plan cannot be submitted');
 await processButton.onclick(); assert.equal(bodies.length,0);
 data.records[0].can='1'; updateOutputButton();
 await processButton.onclick(); assert.equal(bodies.length,1);
 assert.equal(bodies[0].records[0].can,'1');assert.equal(outputStatus.textContent,'Finished Output folder: /output');
 const plan={...initialData,plan_kind:'reviewed-output'};
 await document.getElementById('load').onchange({target:{files:[{text:async()=>JSON.stringify(plan)}]}});
 assert(!processButton.disabled,'a matching existing reviewed plan enables output');
 assert.equal(outputPlan().records.length,1);
 console.log('PASS: review button, saved plan, stale edits, load and completion status');
})().catch(error=>{console.error(error);process.exitCode=1});`;
context.process=process;
vm.runInNewContext(script,context);
