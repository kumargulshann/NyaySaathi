// Offline digital signal/container checks, not evidence of real speech recognition.
import test from "node:test";
import assert from "node:assert/strict";
import {encodeWav, resampleMono, WavRecorder} from "../web/audio.js";

test("PCM WAV has a real RIFF header, mono PCM16 frames and exact rate", () => {
  const samples = new Float32Array([-2,-1,-.5,0,.5,1,2]);
  const buffer = encodeWav(samples, 16000), view = new DataView(buffer);
  assert.equal(new TextDecoder().decode(buffer.slice(0,4)), "RIFF");
  assert.equal(new TextDecoder().decode(buffer.slice(8,12)), "WAVE");
  assert.equal(view.getUint32(4,true), buffer.byteLength - 8);
  assert.equal(view.getUint16(20,true),1); assert.equal(view.getUint16(22,true),1);
  assert.equal(view.getUint32(24,true),16000); assert.equal(view.getUint32(28,true),32000);
  assert.equal(view.getUint16(34,true),16); assert.equal(view.getUint32(40,true),samples.length*2);
  assert.equal(view.getInt16(44,true),-32768); assert.equal(view.getInt16(buffer.byteLength-2,true),32767);
});
for (const sourceRate of [44100,48000]) {
  test(`real ${sourceRate} to 16000 resampling preserves time and low-frequency signal`, () => {
    const samples = Float32Array.from({length:sourceRate},(_,i)=>.5*Math.sin(2*Math.PI*1000*i/sourceRate));
    const mono=resampleMono(samples,sourceRate);
    assert.equal(mono.length,16000);
    const error=mono.slice(50,-50).reduce((sum,x,i)=>sum+Math.abs(x-.5*Math.sin(2*Math.PI*1000*(i+50)/16000)),0)/15900;
    assert.ok(error<.02,error);
    assert.equal(encodeWav(samples,sourceRate).byteLength,32044);
  });
}
test("downsampling attenuates an out-of-band signal",()=>{
  const input=Float32Array.from({length:48000},(_,i)=>Math.sin(2*Math.PI*14000*i/48000));
  const output=resampleMono(input,48000);
  const energy=output.slice(50,-50).reduce((sum,x)=>sum+x*x,0)/15900;
  assert.ok(energy<.01,energy);
});
test("60-second WAV fits below 2 MB; empty/overlong audio is rejected",()=>{
  assert.equal(encodeWav(new Float32Array(16000*60),16000).byteLength,1920044);
  assert.throws(()=>encodeWav(new Float32Array(),16000));
  assert.throws(()=>encodeWav(new Float32Array(16000*60+1),16000));
  assert.throws(()=>resampleMono(new Float32Array(10),0));
});
test("capture stops microphone tracks and closes audio resources",async()=>{
  let stopped=0,closed=0;
  const connections=()=>({connect(){},disconnect(){}});
  Object.defineProperty(globalThis,"isSecureContext",{value:true,configurable:true});
  Object.defineProperty(globalThis,"navigator",{value:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){stopped++;}}]})}},configurable:true});
  globalThis.AudioContext=class {
    constructor(){this.sampleRate=48000;this.state="running";this.destination={};this.audioWorklet={addModule:async()=>{}};}
    createMediaStreamSource(){return connections();} createGain(){return {...connections(),gain:{value:1}};}
    async resume(){} async close(){closed++;this.state="closed";}
  };
  globalThis.AudioWorkletNode=class {
    constructor(){this.port={onmessage:null,postMessage:()=>this.port.onmessage({data:{type:"flushed"}})};}
    connect(){} disconnect(){}
  };
  let result;
  const recorder=new WavRecorder(()=>{},(blob)=>{result=blob;},()=>{});
  await recorder.start();
  recorder.node.port.onmessage({data:{type:"chunk",samples:new Float32Array(4800).fill(.1)}});
  await recorder.stop();
  assert.equal(stopped,1);assert.equal(closed,1);assert.equal(result.type,"audio/wav");assert.equal(result.size,3244);
});
test("permission denial is propagated without creating an audio context",async()=>{
  Object.defineProperty(globalThis,"isSecureContext",{value:true,configurable:true});
  Object.defineProperty(globalThis,"navigator",{value:{mediaDevices:{getUserMedia:async()=>{const error=new Error("denied");error.name="NotAllowedError";throw error;}}},configurable:true});
  let created=0;
  globalThis.AudioContext=class{constructor(){created++;}};
  const recorder=new WavRecorder(()=>{},()=>{},()=>{});
  await assert.rejects(()=>recorder.start(),{name:"NotAllowedError"});assert.equal(created,0);
});
