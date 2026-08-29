(function initializeJarvisAudioReactive(global) {
    "use strict";

    const jarvisUI = global.JarvisUI || {};
    const AudioContextClass = global.AudioContext || global.webkitAudioContext;
    const channels = {
        input: null,
        output: null
    };
    let audioContext = null;

    function createChannel(stream) {
        if (!AudioContextClass || !stream) {
            return null;
        }

        if (!audioContext || audioContext.state === "closed") {
            audioContext = new AudioContextClass();
        }

        const source = audioContext.createMediaStreamSource(stream);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.72;
        source.connect(analyser);

        if (audioContext.state === "suspended") {
            void audioContext.resume().catch(function(error) {
                console.warn("Audio visualization resume error:", error);
            });
        }

        return {
            source: source,
            analyser: analyser,
            samples: new Uint8Array(analyser.fftSize),
            level: 0
        };
    }

    function disconnectChannel(name) {
        const channel = channels[name];
        channels[name] = null;

        if (!channel) {
            return;
        }

        try {
            channel.source.disconnect();
            channel.analyser.disconnect();
        } catch (error) {
            console.warn(`Audio visualization ${name} cleanup error:`, error);
        }
    }

    function attach(name, stream) {
        disconnectChannel(name);

        try {
            channels[name] = createChannel(stream);
            return Boolean(channels[name]);
        } catch (error) {
            console.warn(`Audio visualization ${name} setup error:`, error);
            channels[name] = null;
            return false;
        }
    }

    function sampleChannel(channel) {
        if (!channel || !audioContext || audioContext.state !== "running") {
            return 0;
        }

        channel.analyser.getByteTimeDomainData(channel.samples);
        let sumSquares = 0;

        for (let index = 0; index < channel.samples.length; index += 1) {
            const centered = (channel.samples[index] - 128) / 128;
            sumSquares += centered * centered;
        }

        const rms = Math.sqrt(sumSquares / channel.samples.length);
        const normalized = Math.max(0, Math.min(1, (rms - 0.012) / 0.20));
        channel.level += (normalized - channel.level) * (
            normalized > channel.level ? 0.42 : 0.16
        );
        return channel.level;
    }

    function getLevels() {
        return {
            input: sampleChannel(channels.input),
            output: sampleChannel(channels.output)
        };
    }

    function reset() {
        disconnectChannel("input");
        disconnectChannel("output");

        if (audioContext) {
            const contextToClose = audioContext;
            audioContext = null;
            if (contextToClose.state !== "closed") {
                void contextToClose.close().catch(function(error) {
                    console.warn("Audio visualization context close error:", error);
                });
            }
        }
    }

    jarvisUI.audioReactive = Object.freeze({
        attachInput: function(stream) {
            return attach("input", stream);
        },
        attachOutput: function(stream) {
            return attach("output", stream);
        },
        getLevels: getLevels,
        reset: reset,
        isSupported: function() {
            return Boolean(AudioContextClass);
        }
    });
    global.JarvisUI = jarvisUI;
})(window);
