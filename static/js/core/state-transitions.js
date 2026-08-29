(function initializeCoreStateTransitions(global) {
"use strict";

const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const profiles = Object.freeze({
    idle: Object.freeze({ duration: 1.05, rotationSpeed: 0.10, noiseAmount: 0.42, particleRadius: 0.94, attraction: 0.10, bloomStrength: 0.42, audioResponse: 0.00, particleSize: 0.94, auraDensity: 0.58, orbitSync: 0.05, axisTilt: 0.02, inwardFlow: 0.06, outwardWave: 0.03, primary: [0.33, 0.90, 1.00], secondary: [0.16, 0.48, 1.00] }),
    connecting: Object.freeze({ duration: 0.82, rotationSpeed: 0.16, noiseAmount: 0.30, particleRadius: 0.91, attraction: 0.72, bloomStrength: 0.58, audioResponse: 0.00, particleSize: 0.96, auraDensity: 0.66, orbitSync: 0.88, axisTilt: 0.03, inwardFlow: 0.46, outwardWave: 0.02, primary: [1.00, 0.72, 0.25], secondary: [1.00, 0.39, 0.16] }),
    listening: Object.freeze({ duration: 0.52, rotationSpeed: 0.18, noiseAmount: 0.63, particleRadius: 0.99, attraction: 0.34, bloomStrength: 0.68, audioResponse: 0.42, particleSize: 1.02, auraDensity: 0.76, orbitSync: 0.22, axisTilt: 0.05, inwardFlow: 0.78, outwardWave: 0.08, primary: [0.20, 0.96, 1.00], secondary: [0.10, 0.51, 1.00] }),
    thinking: Object.freeze({ duration: 0.46, rotationSpeed: 0.42, noiseAmount: 0.96, particleRadius: 0.95, attraction: 0.92, bloomStrength: 0.76, audioResponse: 0.00, particleSize: 0.98, auraDensity: 0.82, orbitSync: 0.36, axisTilt: 0.22, inwardFlow: 0.62, outwardWave: 0.04, primary: [0.65, 0.43, 1.00], secondary: [0.18, 0.78, 1.00] }),
    speaking: Object.freeze({ duration: 0.48, rotationSpeed: 0.25, noiseAmount: 0.72, particleRadius: 1.01, attraction: 0.18, bloomStrength: 0.86, audioResponse: 0.92, particleSize: 1.06, auraDensity: 0.92, orbitSync: 0.20, axisTilt: 0.08, inwardFlow: 0.08, outwardWave: 0.88, primary: [0.27, 1.00, 0.76], secondary: [0.08, 0.68, 1.00] }),
    error: Object.freeze({ duration: 0.40, rotationSpeed: 0.045, noiseAmount: 0.54, particleRadius: 0.93, attraction: 0.06, bloomStrength: 0.62, audioResponse: 0.00, particleSize: 0.96, auraDensity: 0.64, orbitSync: 0.02, axisTilt: 0.11, inwardFlow: 0.02, outwardWave: 0.12, primary: [1.00, 0.22, 0.31], secondary: [1.00, 0.48, 0.20] })
});
const numericKeys = Object.freeze(["rotationSpeed", "noiseAmount", "particleRadius", "attraction", "bloomStrength", "audioResponse", "particleSize", "auraDensity", "orbitSync", "axisTilt", "inwardFlow", "outwardWave"]);

function copyProfile(profile) {
    const copy = {};
    numericKeys.forEach((key) => { copy[key] = profile[key]; });
    copy.primary = profile.primary.slice();
    copy.secondary = profile.secondary.slice();
    return copy;
}

function createStateTransitions(initialState) {
    let state = profiles[initialState] ? initialState : "idle";
    let target = profiles[state];
    const current = copyProfile(target);
    let stabilityWave = 0;
    let errorBurst = 0;

    function setState(nextState) {
        const resolved = profiles[nextState] ? nextState : "idle";
        if (resolved === state) return false;
        const previous = state;
        state = resolved;
        target = profiles[state];
        if (previous === "connecting" && state !== "error") stabilityWave = 1;
        if (state === "error") errorBurst = 1;
        return true;
    }

    function update(deltaSeconds, reducedMotion) {
        const duration = Math.max(0.4, Math.min(1.2, target.duration));
        const damping = reducedMotion ? 1 : 1 - Math.exp(-deltaSeconds * 4.6 / duration);
        numericKeys.forEach((key) => { current[key] += (target[key] - current[key]) * damping; });
        for (let index = 0; index < 3; index += 1) {
            current.primary[index] += (target.primary[index] - current.primary[index]) * damping;
            current.secondary[index] += (target.secondary[index] - current.secondary[index]) * damping;
        }
        stabilityWave *= reducedMotion ? 0 : Math.exp(-deltaSeconds * 3.8);
        errorBurst *= reducedMotion ? 0 : Math.exp(-deltaSeconds * 7.5);
        return { profile: current, stabilityWave, errorBurst, state };
    }

    return Object.freeze({ setState, update, getState: () => state });
}

jarvisUI.coreStateTransitions = Object.freeze({ createStateTransitions, profiles });
})(window);
