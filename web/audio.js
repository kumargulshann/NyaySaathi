// Pure encoding functions are also exercised by offline Node tests.
export function resampleMono(samples, sourceRate, targetRate = 16000) {
  if (!Number.isFinite(sourceRate) || sourceRate < 8000 || sourceRate > 192000 || !Number.isFinite(targetRate) || targetRate < 8000 || targetRate > 48000) throw new Error("unsupported_sample_rate");
  if (sourceRate === targetRate) return samples.slice();
  const output = new Float32Array(Math.floor(samples.length * targetRate / sourceRate));
  // Windowed-sinc low-pass resampling; do not merely relabel the source rate.
  const radius = 16, cutoff = 0.47 * Math.min(1, targetRate / sourceRate), phases = new Map();
  for (let i = 0; i < output.length; i++) {
    const position = i * sourceRate / targetRate, base = Math.floor(position), fraction = position - base;
    const phase = Math.round(fraction * 1e6);
    let weights = phases.get(phase);
    if (!weights) {
      weights = new Float64Array(2 * radius + 1);
      for (let tap = -radius; tap <= radius; tap++) {
        const distance = tap - fraction, x = 2 * cutoff * distance;
        weights[tap + radius] = 2 * cutoff * (Math.abs(x) < 1e-9 ? 1 : Math.sin(Math.PI * x) / (Math.PI * x)) * (0.5 + 0.5 * Math.cos(Math.PI * distance / (radius + 1)));
      }
      phases.set(phase, weights);
    }
    let sum = 0, normalization = 0;
    for (let tap = -radius; tap <= radius; tap++) {
      const index = base + tap, weight = weights[tap + radius];
      if (index >= 0 && index < samples.length) { sum += samples[index] * weight; normalization += weight; }
    }
    output[i] = normalization ? sum / normalization : 0;
  }
  return output;
}

export function encodeWav(samples, sourceRate) {
  if (!samples.length || samples.length > sourceRate * 60) throw new Error("audio_duration");
  const mono = resampleMono(samples, sourceRate), size = 44 + mono.length * 2;
  if (!mono.length || size >= 2000000) throw new Error("audio_size");
  const buffer = new ArrayBuffer(size), view = new DataView(buffer);
  const text = (at, value) => { for (let i = 0; i < value.length; i++) view.setUint8(at + i, value.charCodeAt(i)); };
  text(0, "RIFF"); view.setUint32(4, size - 8, true); text(8, "WAVE"); text(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, mono.length * 2, true);
  for (let i = 0; i < mono.length; i++) {
    const sample = Math.max(-1, Math.min(1, Number.isFinite(mono[i]) ? mono[i] : 0));
    view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
  }
  return buffer;
}

export class WavRecorder {
  constructor(onTick, onStop, onError) {
    this.onTick = onTick; this.onStop = onStop; this.onError = onError;
    this.stream = null; this.context = null; this.node = null; this.timer = null;
    this.chunks = []; this.frames = 0; this.stopping = false;
  }
  async start() {
    const Audio = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (!globalThis.isSecureContext || !navigator.mediaDevices?.getUserMedia || !Audio || !globalThis.AudioWorkletNode) throw new Error("unsupported_browser");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}});
      this.context = new Audio();
      await this.context.audioWorklet.addModule("/static/pcm-worklet.js");
      this.source = this.context.createMediaStreamSource(this.stream);
      this.node = new AudioWorkletNode(this.context, "pcm-capture", {numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1]});
      this.node.port.onmessage = (event) => {
        if (event.data.type === "flushed") { this.flushed?.(); return; }
        if (event.data.type !== "chunk") return;
        const allowed = this.context.sampleRate * 60 - this.frames;
        const chunk = event.data.samples.slice(0, Math.max(0, allowed));
        this.chunks.push(chunk); this.frames += chunk.length;
        if (this.frames >= this.context.sampleRate * 60 && !this.stopping) this.stop().catch(this.onError);
      };
      this.mute = this.context.createGain(); this.mute.gain.value = 0;
      this.source.connect(this.node); this.node.connect(this.mute); this.mute.connect(this.context.destination);
      await this.context.resume();
      this.started = performance.now();
      this.timer = setInterval(() => {
        const seconds = Math.min(60, (performance.now() - this.started) / 1000); this.onTick(seconds);
        if (seconds >= 60 && !this.stopping) this.stop().catch(this.onError);
      }, 200);
    } catch (error) { await this.dispose(); throw error; }
  }
  async stop() {
    if (this.stopping) return;
    this.stopping = true; clearInterval(this.timer);
    const rate = this.context.sampleRate;
    try {
      await new Promise((resolve) => {
        const timeout = setTimeout(resolve, 500);
        this.flushed = () => { clearTimeout(timeout); resolve(); };
        this.node.port.postMessage("flush");
      });
      const samples = new Float32Array(this.frames); let offset = 0;
      for (const chunk of this.chunks) { samples.set(chunk, offset); offset += chunk.length; }
      await this.dispose();
      await this.onStop(new Blob([encodeWav(samples, rate)], {type: "audio/wav"}));
    } catch (error) { await this.dispose(); throw error; }
  }
  async dispose() {
    clearInterval(this.timer);
    this.stream?.getTracks().forEach((track) => track.stop());
    this.source?.disconnect(); this.node?.disconnect(); this.mute?.disconnect();
    if (this.context && this.context.state !== "closed") await this.context.close();
    this.chunks = []; this.frames = 0;
  }
}
