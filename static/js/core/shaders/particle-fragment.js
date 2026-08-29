(function registerParticleFragmentShader(global) {
"use strict";

const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const shaders = jarvisUI.coreShaders = jarvisUI.coreShaders || {};

shaders.particleFragment = `
uniform vec3 uColorPrimary;
uniform vec3 uColorSecondary;

varying float vBrightness;
varying float vDepthFade;
varying float vColorMix;
varying float vBloomWeight;
varying float vResonance;
varying float vIntroOpacity;

void main() {
    vec2 centered = gl_PointCoord - vec2(0.5);
    float radius = length(centered) * 2.0;
    float edgeWidth = max(fwidth(radius) * 1.15, 0.008);
    float circleMask = 1.0 - smoothstep(1.0 - edgeWidth, 1.0, radius);
    if (circleMask <= 0.0) discard;

    float microCore = exp(-radius * radius * 31.0);
    float brightCore = exp(-radius * radius * 9.5);
    float softHalo = exp(-radius * radius * 2.8);
    float haloFeather = 1.0 - smoothstep(0.34, 0.92, radius);
    float alpha = (microCore * 0.34 + brightCore * 0.62 + softHalo * 0.34) * haloFeather * circleMask;
    alpha *= vBrightness * mix(0.48, 1.0, vDepthFade) * vIntroOpacity;

    vec3 color = mix(uColorPrimary, uColorSecondary, vColorMix);
    color = mix(color, uColorPrimary * 1.12, vResonance * 0.38);
    vec3 spectralCore = mix(color, uColorPrimary * 1.22, microCore * 0.72);
    color = mix(color, spectralCore, microCore);
    color *= 0.88 + brightCore * 0.54 + vBloomWeight * (microCore * 0.82 + brightCore * 0.28);
    gl_FragColor = vec4(color, alpha * (1.0 + vResonance * 0.36));
}
`;
})(window);
