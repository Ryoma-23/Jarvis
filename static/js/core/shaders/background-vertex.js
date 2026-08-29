(function registerBackgroundVertexShader(global) {
"use strict";
const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const shaders = jarvisUI.coreShaders = jarvisUI.coreShaders || {};
shaders.backgroundVertex = `
uniform float uTime;
uniform float uStateEnergy;
uniform float uPixelRatio;
uniform vec2 uParallax;
attribute float aSeed;
attribute float aSize;
attribute float aDrift;
varying float vAlpha;
varying float vSeed;
varying float vDepth;

void main() {
    vec3 point = position;
    float depthFactor = clamp((-point.z - 1.0) / 6.0, 0.0, 1.0);
    point.x += sin(uTime * aDrift + aSeed * 17.0) * (0.035 + depthFactor * 0.055);
    point.y += cos(uTime * aDrift * 0.73 + aSeed * 23.0) * (0.025 + depthFactor * 0.040);
    point.xy += uParallax * mix(0.15, 0.75, depthFactor);
    point.z += sin(uTime * 0.035 + aSeed * 29.0) * 0.045;

    vec4 viewPosition = modelViewMatrix * vec4(point, 1.0);
    float perspective = 150.0 / max(1.0, -viewPosition.z);
    gl_PointSize = clamp(aSize * uPixelRatio * perspective, 0.65, 3.2);
    gl_Position = projectionMatrix * viewPosition;
    vAlpha = mix(0.18, 0.48, 1.0 - depthFactor) * (1.0 + uStateEnergy * 0.18);
    vSeed = aSeed;
    vDepth = depthFactor;
}
`;
})(window);
