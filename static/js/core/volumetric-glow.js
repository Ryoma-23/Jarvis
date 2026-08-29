(function initializeVolumetricGlow(global) {
"use strict";

const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const vertexShader = `
varying vec2 vUv;
void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;
const fragmentShader = `
uniform float uTime;
uniform float uAudioLevel;
uniform float uTransitionPulse;
uniform float uToolAccent;
uniform float uLayerOpacity;
uniform float uAuraDensity;
uniform vec3 uColorPrimary;
uniform vec3 uColorSecondary;
varying vec2 vUv;
float hash(vec2 point) { return fract(sin(dot(point, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 point) {
    vec2 cell = floor(point);
    vec2 local = fract(point);
    local = local * local * (3.0 - 2.0 * local);
    return mix(mix(hash(cell), hash(cell + vec2(1.0, 0.0)), local.x),
        mix(hash(cell + vec2(0.0, 1.0)), hash(cell + vec2(1.0)), local.x), local.y);
}
void main() {
    vec2 centered = vUv - 0.5;
    float radius = length(centered) * 2.0;
    if (radius > 1.0) discard;
    float turbulence = noise(centered * 4.0 + vec2(uTime * 0.045, -uTime * 0.032));
    float aura = pow(max(0.0, 1.0 - radius), 2.35) * mix(0.72, 1.12, turbulence);
    float ring = exp(-pow((radius - (0.48 + uTransitionPulse * 0.20)) * 10.0, 2.0));
    float energy = 0.72 + uAudioLevel * 0.75 + uToolAccent * 0.28;
    float alpha = (aura * energy + ring * uTransitionPulse * 0.18) * uLayerOpacity * uAuraDensity;
    vec3 color = mix(uColorSecondary, uColorPrimary, clamp(1.0 - radius * 0.72, 0.0, 1.0));
    color *= 0.78 + aura * 0.82 + uAudioLevel * 0.25;
    gl_FragColor = vec4(color, alpha);
}
`;

function createVolumetricGlow(options) {
    const THREE = global.THREE;
    if (!THREE) throw new Error("Three.js is unavailable.");
    const settings = options || {};
    const group = new THREE.Group();
    const geometry = new THREE.PlaneGeometry(2, 2);
    const shared = {
        uTime: { value: 0 }, uAudioLevel: { value: 0 },
        uTransitionPulse: { value: 0 }, uToolAccent: { value: 0 },
        uAuraDensity: { value: 0.58 },
        uColorPrimary: { value: new THREE.Color(settings.primaryColor || 0x55e6ff) },
        uColorSecondary: { value: new THREE.Color(settings.secondaryColor || 0x287bff) }
    };
    const layers = [
        { scale: 0.72, z: 0.12, opacity: 0.34 },
        { scale: 1.18, z: -0.12, opacity: 0.18 },
        { scale: 1.72, z: -0.30, opacity: 0.075 }
    ];
    const materials = [];
    layers.forEach((layer) => {
        const material = new THREE.ShaderMaterial({
            uniforms: Object.assign({}, shared, { uLayerOpacity: { value: layer.opacity } }),
            vertexShader, fragmentShader, transparent: true, depthWrite: false,
            depthTest: false, blending: THREE.AdditiveBlending
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.scale.setScalar(layer.scale);
        mesh.position.z = layer.z;
        mesh.renderOrder = -2;
        group.add(mesh);
        materials.push(material);
    });
    return {
        object: group,
        uniforms: shared,
        dispose() { geometry.dispose(); materials.forEach((material) => material.dispose()); }
    };
}

jarvisUI.volumetricGlow = Object.freeze({ createVolumetricGlow });
})(window);
