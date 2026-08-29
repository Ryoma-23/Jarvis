(function initializeSpatialBackground(global) {
"use strict";

const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const desktopParticleCount = 520;
const compactParticleCount = 220;

function createRandom(seed) {
    let state = seed >>> 0;
    return function random() {
        state = (state * 1664525 + 1013904223) >>> 0;
        return state / 4294967296;
    };
}

function createSpatialBackground(options) {
    const THREE = global.THREE;
    const shaders = jarvisUI.coreShaders;
    if (!THREE || !shaders || !shaders.backgroundVertex || !shaders.backgroundFragment) {
        throw new Error("Spatial background shader dependencies are unavailable.");
    }
    const settings = options || {};
    const random = createRandom(0x53504143);
    const positions = new Float32Array(desktopParticleCount * 3);
    const seeds = new Float32Array(desktopParticleCount);
    const sizes = new Float32Array(desktopParticleCount);
    const drift = new Float32Array(desktopParticleCount);

    for (let index = 0; index < desktopParticleCount; index += 1) {
        const offset = index * 3;
        positions[offset] = (random() - 0.5) * 7.2;
        positions[offset + 1] = (random() - 0.5) * 4.6;
        positions[offset + 2] = -1.4 - Math.pow(random(), 0.72) * 6.0;
        seeds[index] = random();
        sizes[index] = 0.028 + random() * 0.040;
        drift[index] = 0.025 + random() * 0.055;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
    geometry.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
    geometry.setAttribute("aDrift", new THREE.BufferAttribute(drift, 1));
    geometry.setDrawRange(0, desktopParticleCount);
    const material = new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 }, uStateEnergy: { value: 0 },
            uPixelRatio: { value: settings.pixelRatio || 1 },
            uParallax: { value: new THREE.Vector2() },
            uColor: { value: new THREE.Color(settings.color || 0x19445f) }
        },
        vertexShader: shaders.backgroundVertex,
        fragmentShader: shaders.backgroundFragment,
        transparent: true,
        depthWrite: false,
        depthTest: true,
        blending: THREE.NormalBlending
    });
    const points = new THREE.Points(geometry, material);
    points.frustumCulled = false;
    points.renderOrder = -5;

    return {
        object: points,
        uniforms: material.uniforms,
        setCompact(compact) { geometry.setDrawRange(0, compact ? compactParticleCount : desktopParticleCount); },
        dispose() { geometry.dispose(); material.dispose(); }
    };
}

jarvisUI.spatialBackground = Object.freeze({ createSpatialBackground, desktopParticleCount, compactParticleCount });
})(window);
