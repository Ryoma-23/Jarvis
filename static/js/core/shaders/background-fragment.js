(function registerBackgroundFragmentShader(global) {
"use strict";
const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const shaders = jarvisUI.coreShaders = jarvisUI.coreShaders || {};
shaders.backgroundFragment = `
uniform vec3 uColor;
uniform vec3 uColorAccent;
uniform float uIntroProgress;
varying float vAlpha;
varying float vSeed;
varying float vDepth;
void main() {
    float radius = length(gl_PointCoord - vec2(0.5)) * 2.0;
    if (radius > 1.0) discard;
    float softness = 1.0 - smoothstep(0.12, 1.0, radius);
    float brightness = mix(0.42, 0.86, vSeed);
    float introOpacity = smoothstep(0.0, 0.28, uIntroProgress);
    float accentMix = smoothstep(0.68, 0.98, vSeed) * mix(0.18, 0.46, 1.0 - vDepth);
    vec3 starColor = mix(uColor, uColorAccent, accentMix);
    gl_FragColor = vec4(starColor * brightness, softness * vAlpha * 0.24 * introOpacity);
}
`;
})(window);
