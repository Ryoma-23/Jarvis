(function registerBackgroundFragmentShader(global) {
"use strict";
const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const shaders = jarvisUI.coreShaders = jarvisUI.coreShaders || {};
shaders.backgroundFragment = `
uniform vec3 uColor;
varying float vAlpha;
varying float vSeed;
void main() {
    float radius = length(gl_PointCoord - vec2(0.5)) * 2.0;
    if (radius > 1.0) discard;
    float softness = 1.0 - smoothstep(0.12, 1.0, radius);
    float brightness = mix(0.46, 0.82, vSeed);
    gl_FragColor = vec4(uColor * brightness, softness * vAlpha * 0.24);
}
`;
})(window);
