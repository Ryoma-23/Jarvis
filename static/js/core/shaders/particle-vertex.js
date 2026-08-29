(function registerParticleVertexShader(global) {
"use strict";

const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const shaders = jarvisUI.coreShaders = jarvisUI.coreShaders || {};

shaders.particleVertex = `
uniform float uTime;
uniform float uStateBlend;
uniform float uAudioLevel;
uniform float uMotionIntensity;
uniform float uCoreScale;
uniform float uIntroProgress;
uniform float uPixelRatio;
uniform float uTransitionPulse;
uniform float uToolAccent;
uniform float uRotationSpeed;
uniform float uNoiseAmount;
uniform float uParticleRadius;
uniform float uAttraction;
uniform float uAudioResponse;
uniform float uResonanceMode;
uniform float uResonanceLevel;
uniform float uResonancePhase;
uniform float uParticleSizeScale;
uniform float uOrbitSync;
uniform float uAxisTilt;
uniform float uInwardFlow;
uniform float uOutwardWave;
uniform float uErrorBurst;

attribute vec3 aBasePosition;
attribute float aSeed;
attribute float aParticleSize;
attribute float aBrightness;
attribute float aSpeed;
attribute float aPhase;
attribute float aLayer;

varying float vBrightness;
varying float vDepthFade;
varying float vColorMix;
varying float vBloomWeight;
varying float vResonance;
varying float vIntroOpacity;

mat2 rotate2d(float angle) {
    float sine = sin(angle);
    float cosine = cos(angle);
    return mat2(cosine, -sine, sine, cosine);
}

vec3 organicField(vec3 point, float time, float seed) {
    vec3 samplePoint = point * 2.7 + vec3(seed * 5.31);
    return vec3(
        sin(samplePoint.y + time * 0.71) - cos(samplePoint.z * 1.17 - time * 0.43),
        sin(samplePoint.z * 0.91 - time * 0.57) - cos(samplePoint.x + time * 0.37),
        sin(samplePoint.x * 1.11 + time * 0.49) - cos(samplePoint.y * 0.83 - time * 0.61)
    ) * 0.5;
}

void main() {
    vec3 base = aBasePosition;
    float baseRadius = max(length(base), 0.001);
    vec3 radial = base / baseRadius;
    float time = uTime * (0.45 + aSpeed * 0.85);
    float formation = smoothstep(0.22, 0.82, uIntroProgress);

    float synchronizedPhase = mix(aPhase, floor(aPhase * 2.0) * 0.5, uOrbitSync);
    float orbit = time * uRotationSpeed * mix(0.65, 1.35, aLayer) + synchronizedPhase;
    base.xz = rotate2d(orbit) * base.xz;
    base.xy = rotate2d(orbit * (0.20 + uAxisTilt) * (aSeed - 0.5)) * base.xy;
    base *= uParticleRadius * mix(1.48, 1.0, formation);

    vec3 flow = organicField(base, time, aSeed);
    float innerWeight = 1.0 - aLayer;
    float convection = mix(0.025, 0.105, innerWeight) * uMotionIntensity * uNoiseAmount;
    float stateDisplacement = mix(0.55, 1.35, uStateBlend);
    vec3 displaced = base + flow * convection * stateDisplacement;
    displaced += radial * (1.0 - formation) * (0.18 + aSeed * 0.38);

    float convergence = sin(time * 1.7 + aPhase) * innerWeight * 0.065 - uAttraction * mix(0.018, 0.055, innerWeight);
    float outwardDrift = sin(time * 0.63 + aSeed * 19.0) * aLayer * 0.025;
    float inwardFlow = -uInwardFlow * aLayer * (0.018 + 0.018 * sin(time + aPhase));
    float audioExpansion = uAudioLevel * uAudioResponse * mix(0.07, 0.18, aLayer);
    float speakingWave = sin(baseRadius * 15.0 - time * 4.5 + aPhase) * uOutwardWave * (0.014 + uAudioLevel * 0.045);
    float returnFlight = pow(max(0.0, sin(time * 1.8 + aPhase)), 7.0) * uOutwardWave * step(0.82, aSeed) * 0.22;
    float errorScatter = uErrorBurst * (aSeed - 0.5) * 0.24;
    float listeningMask = 1.0 - step(1.5, uResonanceMode);
    listeningMask *= step(0.5, uResonanceMode);
    float speakingMask = step(1.5, uResonanceMode);
    float azimuth = atan(base.z, base.x);
    float intakeFocus = pow(max(0.0, 0.5 + 0.5 * cos(azimuth - uResonancePhase * 0.62 + sin(base.y * 4.0) * 0.42)), 7.0);
    float intakePull = -uResonanceLevel * intakeFocus * aLayer * 0.115 * listeningMask;
    float propagation = 0.5 + 0.5 * sin(baseRadius * 18.0 - uResonancePhase * 5.2 + aPhase * 0.18);
    float emissionFront = pow(propagation, 8.0) * uResonanceLevel * speakingMask;
    float emissionPush = emissionFront * mix(0.075, 0.125, aLayer);
    displaced += radial * (convergence + outwardDrift + inwardFlow + audioExpansion + speakingWave + returnFlight + errorScatter + intakePull + emissionPush) * uMotionIntensity;
    displaced += flow * intakeFocus * uResonanceLevel * listeningMask * innerWeight * 0.024;
    displaced += normalize(flow + vec3(0.001)) * uToolAccent * innerWeight * 0.055;
    displaced += radial * uTransitionPulse * (0.035 + aSeed * 0.025);
    displaced *= uCoreScale;

    vec4 viewPosition = modelViewMatrix * vec4(displaced, 1.0);
    float distanceScale = 260.0 / max(1.0, -viewPosition.z);
    gl_PointSize = clamp(aParticleSize * uParticleSizeScale * uPixelRatio * distanceScale * smoothstep(0.08, 0.48, uIntroProgress), 1.25, 22.0);
    gl_Position = projectionMatrix * viewPosition;

    vBrightness = aBrightness * (1.0 + uAudioLevel * 0.55);
    vDepthFade = 1.0 - smoothstep(2.4, 6.6, -viewPosition.z);
    vColorMix = clamp(aSeed * 0.58 + aLayer * 0.42, 0.0, 1.0);
    float highEnergy = smoothstep(0.84, 1.0, aBrightness);
    float nucleus = (1.0 - aLayer) * (1.0 - smoothstep(0.05, 0.62, baseRadius));
    vBloomWeight = clamp(highEnergy * 0.62 + nucleus * 0.92 + uAudioLevel * 0.52 + uTransitionPulse * 0.35 + uToolAccent * 0.28, 0.0, 1.65);
    vResonance = clamp(intakeFocus * uResonanceLevel * listeningMask + emissionFront * speakingMask, 0.0, 1.0);
    vIntroOpacity = smoothstep(0.10, 0.58, uIntroProgress);
}
`;
})(window);
