/**
 * PCM processor — runs in the AudioWorklet thread.
 * Converts Float32 samples to Int16 PCM and posts the buffer to the main thread.
 */
class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;

    const int16 = new Int16Array(channel.length);
    for (let i = 0; i < channel.length; i++) {
      int16[i] = Math.max(-32768, Math.min(32767, channel[i] * 32768));
    }
    // Transfer the underlying buffer (zero-copy)
    this.port.postMessage(int16.buffer, [int16.buffer]);
    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);
