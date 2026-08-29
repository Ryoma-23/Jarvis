(function initializeSpatialBackground(global) {
"use strict";

const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const cosmicVertexShader = `
varying vec2 vUv;
void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;
const cosmicFragmentShader = `
uniform float uTime;
uniform vec3 uColor;
uniform vec3 uColorAccent;
varying vec2 vUv;

float cloud(vec2 uv, vec2 center, vec2 scale) {
    vec2 offset = (uv - center) / scale;
    return exp(-dot(offset, offset) * 2.2);
}

void main() {
    vec2 uv = vUv;
    float drift = sin(uTime * 0.018) * 0.012;
    float blueCloud = cloud(uv, vec2(0.20 + drift, 0.70), vec2(0.42, 0.52));
    float violetCloud = cloud(uv, vec2(0.80 - drift, 0.72), vec2(0.40, 0.46));
    float tealCloud = cloud(uv, vec2(0.68, 0.20 + drift), vec2(0.48, 0.42));
    float dustBand = exp(-pow((uv.y - (0.82 - uv.x * 0.58)) * 3.8, 2.0));

    vec3 color = vec3(0.003, 0.010, 0.022);
    color += vec3(0.008, 0.038, 0.076) * blueCloud;
    color += vec3(0.038, 0.015, 0.066) * violetCloud;
    color += vec3(0.006, 0.042, 0.048) * tealCloud;
    color += mix(uColor * 0.055, uColorAccent * 0.082, uv.x) * dustBand;

    float vignette = 1.0 - smoothstep(0.38, 0.82, length(uv - 0.5));
    color *= mix(0.38, 1.0, vignette);
    gl_FragColor = vec4(color, 1.0);
}
`;

function createSpatialBackground(options) {
    const THREE = global.THREE;
    if (!THREE) {
        throw new Error("Spatial background shader dependencies are unavailable.");
    }
    const settings = options || {};
    const sharedUniforms = {
            uTime: { value: 0 }, uStateEnergy: { value: 0 },
            uPixelRatio: { value: settings.pixelRatio || 1 },
            uParallax: { value: new THREE.Vector2() },
            uColor: { value: new THREE.Color(settings.color || 0x19445f) },
            uColorAccent: { value: new THREE.Color(settings.accentColor || 0x40346f) },
            uIntroProgress: { value: 1 }
    };
    const cosmicGeometry = new THREE.PlaneGeometry(32, 18);
    const cosmicMaterial = new THREE.ShaderMaterial({
        uniforms: {
            uTime: sharedUniforms.uTime,
            uColor: sharedUniforms.uColor,
            uColorAccent: sharedUniforms.uColorAccent
        },
        vertexShader: cosmicVertexShader,
        fragmentShader: cosmicFragmentShader,
        depthWrite: false,
        depthTest: false
    });
    const cosmicBackdrop = new THREE.Mesh(cosmicGeometry, cosmicMaterial);
    cosmicBackdrop.position.z = -8.5;
    cosmicBackdrop.renderOrder = -10;
    cosmicBackdrop.frustumCulled = false;
    const group = new THREE.Group();
    group.add(cosmicBackdrop);

    return {
        object: group,
        uniforms: sharedUniforms,
        setCompact() {},
        dispose() {
            cosmicGeometry.dispose();
            cosmicMaterial.dispose();
        }
    };
}

jarvisUI.spatialBackground = Object.freeze({ createSpatialBackground });
})(window);
