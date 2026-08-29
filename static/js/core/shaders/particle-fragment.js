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
    if (radius > 1.0) discard;

    float brightCore = 1.0 - smoothstep(0.0, 0.28, radius);
    float softHalo = 1.0 - smoothstep(0.18, 1.0, radius);
    float edgeMask = 1.0 - smoothstep(0.82, 1.0, radius);
    float alpha = (brightCore * 0.88 + softHalo * 0.62) * edgeMask;
    alpha *= vBrightness * mix(0.48, 1.0, vDepthFade) * vIntroOpacity;

    vec3 color = mix(uColorPrimary, uColorSecondary, vColorMix);
    color = mix(color, uColorPrimary * 1.12, vResonance * 0.38);
    color *= 0.92 + brightCore * 0.58 + vBloomWeight * brightCore * 0.78;
    gl_FragColor = vec4(color, alpha * (1.0 + vResonance * 0.36));
}
`;
})(window);
