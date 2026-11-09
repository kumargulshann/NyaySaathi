// Minimal DOM/event harness for application logic. This is NOT a real browser or
// a CSS/microphone-permission check. No runtime/test npm dependencies are needed.
import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {setTimeout as pause} from "node:timers/promises";

const downloads=[];
class Element {
  constructor(tag="div") { this.tagName=tag;this.children=[];this.events={};this.value="";this.textContent="";this.hidden=false;this.disabled=false;this.checked=false;this.dataset={};this.classList={add(){},remove(){}}; }
  set innerHTML(_) { throw new Error("Unsafe HTML assignment"); }
  append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
  addEventListener(name,callback){(this.events[name]||=[]).push(callback);}
  removeAttribute(name){delete this[name];} pause(){} focus(){} remove(){}
  click(){if(this.tagName==="a"&&this.download)downloads.push({name:this.download,url:this.href});}
}
async function until(check) {
  const deadline=Date.now()+3000;
  while(!check()){if(Date.now()>deadline)throw new Error("UI event did not settle");await pause(1);}
}

test("UI logic preserves edits, marks stale drafts, sends approved voice once and clears new cases",async(t)=>{
  const html=await readFile(new URL("../web/index.html",import.meta.url),"utf8"), elements=new Map();
  for(const match of html.matchAll(/<(\w+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){
    const e=new Element(match[1]);e.hidden=/\bhidden(?:\s|$)/.test(match[2]);elements.set(match[3],e);
  }
  const $=(id)=>{assert.ok(elements.has(id),`Missing HTML element ${id}`);return elements.get(id);};
  $("language").value="en";$("document-language").value="en";
  globalThis.document={getElementById:$,createElement:(tag)=>new Element(tag),querySelectorAll:()=>[],documentElement:{},body:new Element("body")};
  globalThis.window={addEventListener(){}};
  const urls=new Map();let urlCount=0;
  URL.createObjectURL=(blob)=>{const key=`blob:offline-${++urlCount}`;urls.set(key,blob);return key;};URL.revokeObjectURL=(key)=>urls.delete(key);
  let stopped=0,node;
  const connected=()=>({connect(){},disconnect(){}});
  Object.defineProperty(globalThis,"isSecureContext",{value:true,configurable:true});
  Object.defineProperty(globalThis,"navigator",{value:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){stopped++;}}]})}},configurable:true});
  globalThis.AudioContext=class {
    constructor(){this.sampleRate=48000;this.state="running";this.destination={};this.audioWorklet={addModule:async()=>{}};}
    createMediaStreamSource(){return connected();}createGain(){return {...connected(),gain:{value:1}};}async resume(){}async close(){this.state="closed";}
  };
  globalThis.AudioWorkletNode=class{constructor(){node=this;this.port={onmessage:null,postMessage:()=>this.port.onmessage({data:{type:"flushed"}})};}connect(){}disconnect(){}};
  const timers=[],realInterval=globalThis.setInterval;
  globalThis.setInterval=(...args)=>{const timer=realInterval(...args);timers.push(timer);return timer;};
  t.after(()=>{timers.forEach(clearInterval);globalThis.setInterval=realInterval;});
  const calls=[];let amount="2999",fail=false,transcriptionError=false;
  const caseData=()=>({issue_type:"defective product",company_or_seller:"Example Shop",amount_inr:amount,incident_date:null,evidence_available:[],evidence_missing:[],timeline:[],user_summary:amount==="2500"?null:"Damaged headphones.",desired_resolution:"refund",unanswered_questions:["Order date?"],case_status:"in_progress",narrative_review_required:amount==="2500"});
  const readiness={status:"missing",missing:["incident_date"],review:[],provisional_allowed:true};
  globalThis.fetch=async(path,options)=>{
    const body=path==="/api/transcribe"?options.body:JSON.parse(options.body);calls.push({path,body});
    if(fail)throw new Error("offline network failure");
    if(path==="/api/transcribe")return transcriptionError ? {ok:false,json:async()=>({error:{code:"empty_transcription",message:"Provider returned no transcript; this does not confirm silence."}})} : {ok:true,json:async()=>({transcript:"Mera 2000 ka refund pending hai"})};
    if(path==="/api/chat"){
      if(body.message.includes("2500"))amount="2500";
      return{ok:true,json:async()=>({case:caseData(),case_signature:`signature-${amount}`,reply:"<img src=x onerror=alert(1)> Which seller?",guidance:{status:"grounded",language:"en",message:"",citations:[
        {source_id:"OFFLINE-FIXTURE",title:"Official fixture",url:"https://consumeraffairs.gov.in/",explanation:"Checked fixture explanation",next_step:"Review the records",limitation:"Not an outcome guarantee",location:"Fixture only",date_checked:"2026-11-09"},
        {source_id:"UNSAFE-FIXTURE",title:"Unsafe fixture",url:"javascript:alert(1)",explanation:"Do not render this link"},
      ]},readiness,fingerprint:amount,error:null})};
    }
    assert.equal(path,"/api/action-package");
    return{ok:true,json:async()=>({readiness,package:{complaint:`Current complaint ${amount}`,summary:`Current summary ${amount}`,language:body.language,fingerprint:amount,checklist:{reported:[],collect:["invoice"],unknown:[]}}})};
  };
  const emit=async(id,event="click")=>{for(const callback of $(id).events[event]||[])await callback({preventDefault(){}});};
  await import("../web/app.js");
  assert.equal(calls.length,0); // No recording/transcription/intake on page load.
  await emit("example");assert.match($("message").value,/headphones/);assert.equal(calls.length,0);
  await emit("chat-form","submit");await emit("chat-form","submit");await until(()=>!$("send").disabled);
  assert.equal(calls.length,1);assert.match($("messages").children[1].children[1].textContent,/<img/);
  assert.equal($("guidance-content").children.length,1);
  assert.equal($("guidance-content").children[0].children[1].href,"https://consumeraffairs.gov.in/");
  $("provisional").checked=true;await emit("generate");
  assert.equal(calls.at(-1).body.case_signature,"signature-2999");
  assert.equal($("complaint").value,"Current complaint 2999");
  $("complaint").value="My manually reviewed complaint";$("nch-summary").value="My manual NCH summary";
  await emit("download-complaint");
  assert.match(downloads.at(-1).name,/complaint_en.txt$/);
  const downloaded=urls.get(downloads.at(-1).url);
  assert.ok((await downloaded.text()).endsWith("My manually reviewed complaint"));
  assert.deepEqual([...new Uint8Array(await downloaded.arrayBuffer()).slice(0,3)],[239,187,191]);
  $("language").value="hi";await emit("language","change");
  assert.equal($("complaint").value,"My manually reviewed complaint");
  $("message").value="Correction: amount 2500";await emit("chat-form","submit");await until(()=>!$("send").disabled);
  assert.equal(calls.at(-1).body.case_signature,"signature-2999");
  assert.equal($("complaint").value,"My manually reviewed complaint");assert.equal($("nch-summary").value,"My manual NCH summary");assert.equal($("outdated").hidden,false);
  await emit("generate");assert.equal($("complaint").value,"Current complaint 2500");assert.equal($("outdated").hidden,true);
  assert.equal(calls.at(-1).body.case_signature,"signature-2500");
  $("document-language").value="hi";await emit("document-language","change");assert.equal($("outdated").hidden,false);assert.equal($("complaint").value,"Current complaint 2500");
  await emit("new-case");assert.equal($("complaint").value,"");assert.equal($("messages").children.length,0);
  const beforeVoice=calls.length;
  await emit("record");node.port.onmessage({data:{type:"chunk",samples:new Float32Array(4800).fill(.1)}});await emit("record");
  await until(()=>!$("transcribe").hidden);assert.equal(stopped,1);assert.equal(calls.length,beforeVoice);
  const wave=urls.get($("audio-preview").src);assert.equal(wave.type,"audio/wav");assert.equal(wave.size,3244);
  transcriptionError=true;
  await emit("transcribe");
  assert.equal($("voice-error").hidden,false);
  assert.match($("voice-error").textContent,/मौन|silence/);
  assert.equal($("transcript-section").hidden,true);
  assert.equal(calls.length,beforeVoice+1);
  await emit("language","change");assert.equal(calls.length,beforeVoice+1); // No automatic retry.
  transcriptionError=false;
  await emit("transcribe");await emit("transcribe");assert.equal(calls.length,beforeVoice+2);
  $("transcript").value="Approved correction 2500";await emit("transcript","input");
  await emit("send-voice");await emit("send-voice");await until(()=>!$("send").disabled);
  assert.equal(calls.length,beforeVoice+3);assert.equal(calls.at(-1).body.message,"Approved correction 2500");assert.equal($("send-voice").disabled,true);
  assert.equal(calls.at(-1).body.case_signature,null);
  const beforeLanguage=calls.length;await emit("language","change");assert.equal(calls.length,beforeLanguage);
  fail=true;$("message").value="Refund still pending";await emit("chat-form","submit");await until(()=>!$("send").disabled);
  assert.equal($("request-error").hidden,false);assert.equal(calls.length,beforeLanguage+1);
  await emit("new-case");assert.equal($("transcript").value,"");assert.equal($("audio-preview").hidden,true);assert.equal($("documents").hidden,true);
});
