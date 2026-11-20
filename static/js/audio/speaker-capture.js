(function(global) {
    "use strict";
    class Capture {
        constructor() { this.context = null; this.chunks = []; this.position = 0; this.rate = 48000; this.closed = false; }
        async start(stream) {
            this.context = new AudioContext();
            this.rate = this.context.sampleRate;
            try {
                await this.context.audioWorklet.addModule("/static/js/audio/speaker-capture-worklet.js?v=1.50");
                if (this.closed) throw Error("capture_closed");
                this.source = this.context.createMediaStreamSource(stream);
                this.node = new AudioWorkletNode(this.context, "speaker-capture");
                this.node.port.onmessage = event => {
                    if (this.closed) return;
                    this.chunks.push({start: this.position, samples: event.data});
                    this.position += event.data.length;
                    while (this.chunks.length && this.chunks[0].start < this.position - this.rate * 22) this.chunks.shift();
                };
                this.source.connect(this.node);
                this.node.connect(this.context.destination); // processor emits silence only
                await this.context.resume();
                if (this.context.state !== "running") throw Error("capture_suspended");
            } catch (error) { this.close(); throw error; }
        }
        wav(start = 0, end = this.position) {
            start = Math.max(0, Math.floor(start)); end = Math.min(this.position, Math.floor(end));
            if (!this.chunks.length || start < this.chunks[0].start || end <= start || end - start > this.rate * 15) {
                throw Error("capture_unavailable");
            }
            const audio = new Float32Array(end - start);
            for (const chunk of this.chunks) {
                const a = Math.max(start, chunk.start), b = Math.min(end, chunk.start + chunk.samples.length);
                if (b > a) audio.set(chunk.samples.subarray(a - chunk.start, b - chunk.start), a - start);
            }
            return encodeWav(audio, this.rate);
        }
        close() {
            this.closed = true;
            if (this.node) { this.node.port.onmessage = null; this.node.disconnect(); }
            if (this.source) this.source.disconnect();
            if (this.context && this.context.state !== "closed") void this.context.close().catch(() => {});
            this.chunks = [];
        }
    }
    function encodeWav(samples, rate) {
        const bytes = new ArrayBuffer(44 + samples.length * 2), view = new DataView(bytes);
        const text = (offset, value) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
        text(0, "RIFF"); view.setUint32(4, bytes.byteLength - 8, true); text(8, "WAVE"); text(12, "fmt ");
        view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
        view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
        text(36, "data"); view.setUint32(40, samples.length * 2, true);
        for (let i = 0; i < samples.length; i++) view.setInt16(44 + i * 2, Math.round(Math.max(-1, Math.min(1, samples[i])) * 32767), true);
        return new Blob([bytes], {type: "audio/wav"});
    }
    global.JarvisSpeakerCapture = {Capture, encodeWav};
})(window);
