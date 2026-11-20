// Sends mono input to an observation-only ring buffer. Output is always silence.
class SpeakerCaptureProcessor extends AudioWorkletProcessor {
    constructor() { super(); this.buffer = new Float32Array(2048); this.used = 0; }
    process(inputs, outputs) {
        const channels = inputs[0];
        if (channels?.length) {
            for (let i = 0; i < channels[0].length; i++) {
                let value = 0;
                for (const channel of channels) value += channel[i] / channels.length;
                this.buffer[this.used++] = value;
                if (this.used === this.buffer.length) {
                    this.port.postMessage(this.buffer, [this.buffer.buffer]);
                    this.buffer = new Float32Array(2048); this.used = 0;
                }
            }
        }
        for (const output of outputs) for (const channel of output) channel.fill(0);
        return true;
    }
}
registerProcessor("speaker-capture", SpeakerCaptureProcessor);
