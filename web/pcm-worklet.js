// AudioWorklet performs capture only. Encoding/resampling happens in audio.js.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super(); this.buffer = new Float32Array(4096); this.position = 0;
    this.port.onmessage = (event) => {
      if (event.data === "flush") { this.flush(); this.port.postMessage({type: "flushed"}); }
    };
  }
  flush() {
    if (!this.position) return;
    const samples = this.buffer.slice(0, this.position);
    this.port.postMessage({type: "chunk", samples}, [samples.buffer]);
    this.position = 0;
  }
  process(inputs) {
    const channels = inputs[0];
    if (!channels?.length) return true;
    for (let i = 0; i < channels[0].length; i++) {
      let mono = 0;
      for (const channel of channels) mono += channel[i] / channels.length;
      this.buffer[this.position++] = mono;
      if (this.position === this.buffer.length) this.flush();
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
