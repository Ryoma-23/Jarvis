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

void main() {
    vec2 centered = gl_PointCoord - vec2(0.5);
    float radius = length(centered) * 2.0;
    if (radius > 1.0) discard;

    float brightCore = 1.0 - smoothstep(0.0, 0.28, radius);
    float softHalo = 1.0 - smoothstep(0.18, 1.0, radius);
    float edgeMask = 1.0 - smoothstep(0.82, 1.0, radius);
    float alpha = (brightCore * 0.88 + softHalo * 0.62) * edgeMask;
    alpha *= vBrightness * mix(0.48, 1.0, vDepthFade);

    vec3 color = mix(uColorPrimary, uColorSecondary, vColorMix);
    color *= 0.92 + brightCore * 0.58 + vBloomWeight * brightCore * 0.78;
    gl_FragColor = vec4(color, alpha);
}
`;
})(window);
