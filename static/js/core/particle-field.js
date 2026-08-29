(function initializeParticleField(global) {
"use strict";

const jarvisUI = global.JarvisUI = global.JarvisUI || {};
const PARTICLE_GROUPS = Object.freeze({ surface: 1050, volume: 720, flow: 300, cluster: 260 });

function createRandom(seed) {
    let state = seed >>> 0;
    return function random() {
        state = (state * 1664525 + 1013904223) >>> 0;
        return state / 4294967296;
    };
}

function directionOnSphere(random) {
    const y = random() * 2 - 1;
    const angle = random() * Math.PI * 2;
    const planar = Math.sqrt(Math.max(0, 1 - y * y));
    return [planar * Math.cos(angle), y, planar * Math.sin(angle)];
}

function writeParticle(targets, index, point, layer, random, sizeRange, speedRange) {
    const offset = index * 3;
    targets.positions[offset] = point[0];
    targets.positions[offset + 1] = point[1];
    targets.positions[offset + 2] = point[2];
    targets.seeds[index] = random();
    targets.sizes[index] = sizeRange[0] + random() * (sizeRange[1] - sizeRange[0]);
    targets.brightness[index] = 0.55 + random() * 0.45;
    targets.speeds[index] = speedRange[0] + random() * (speedRange[1] - speedRange[0]);
    targets.phases[index] = random() * Math.PI * 2;
    targets.layers[index] = layer;
}

function createParticleField(options) {
    const THREE = global.THREE;
    if (!THREE || !jarvisUI.coreMaterials) throw new Error("Particle field dependencies are unavailable.");

    const counts = PARTICLE_GROUPS;
    const total = counts.surface + counts.volume + counts.flow + counts.cluster;
    const targets = {
        positions: new Float32Array(total * 3), seeds: new Float32Array(total),
        sizes: new Float32Array(total), brightness: new Float32Array(total),
        speeds: new Float32Array(total), phases: new Float32Array(total), layers: new Float32Array(total)
    };
    const random = createRandom(0x4a415256);
    let index = 0;

    for (let i = 0; i < counts.surface; i += 1, index += 1) {
        const direction = directionOnSphere(random);
        const radius = 0.91 + (random() - 0.5) * 0.13;
        writeParticle(targets, index, direction.map((value) => value * radius), 1, random, [0.042, 0.075], [0.32, 0.72]);
    }

    for (let i = 0; i < counts.volume; i += 1, index += 1) {
        const direction = directionOnSphere(random);
        const radius = 0.12 + Math.pow(random(), 0.72) * 0.72;
        writeParticle(targets, index, direction.map((value) => value * radius), 0.08, random, [0.035, 0.068], [0.48, 1.05]);
    }

    for (let i = 0; i < counts.flow; i += 1, index += 1) {
        const progress = i / counts.flow;
        const radius = 0.92 - progress * 0.78 + (random() - 0.5) * 0.08;
        const angle = progress * Math.PI * 9 + random() * 0.65;
        const y = (0.5 - progress) * 1.2 + (random() - 0.5) * 0.16;
        writeParticle(targets, index, [Math.cos(angle) * radius, y, Math.sin(angle) * radius], 0.34, random, [0.038, 0.072], [0.68, 1.18]);
    }

    const clusterCenters = Array.from({ length: 7 }, () => {
        const direction = directionOnSphere(random);
        const radius = 0.26 + random() * 0.55;
        return direction.map((value) => value * radius);
    });
    for (let i = 0; i < counts.cluster; i += 1, index += 1) {
        const center = clusterCenters[i % clusterCenters.length];
        const spread = 0.035 + random() * 0.13;
        const direction = directionOnSphere(random);
        const point = center.map((value, axis) => value + direction[axis] * spread);
        writeParticle(targets, index, point, 0.62, random, [0.045, 0.082], [0.42, 0.92]);
    }

    const geometry = new THREE.BufferGeometry();
    const basePosition = new THREE.BufferAttribute(targets.positions, 3);
    geometry.setAttribute("position", basePosition);
    geometry.setAttribute("aBasePosition", basePosition);
    geometry.setAttribute("aSeed", new THREE.BufferAttribute(targets.seeds, 1));
    geometry.setAttribute("aParticleSize", new THREE.BufferAttribute(targets.sizes, 1));
    geometry.setAttribute("aBrightness", new THREE.BufferAttribute(targets.brightness, 1));
    geometry.setAttribute("aSpeed", new THREE.BufferAttribute(targets.speeds, 1));
    geometry.setAttribute("aPhase", new THREE.BufferAttribute(targets.phases, 1));
    geometry.setAttribute("aLayer", new THREE.BufferAttribute(targets.layers, 1));
    geometry.computeBoundingSphere();

    const material = jarvisUI.coreMaterials.createParticleMaterial(options);
    const points = new THREE.Points(geometry, material);
    points.frustumCulled = false;

    return {
        points,
        material,
        uniforms: material.uniforms,
        dispose() {
            geometry.dispose();
            material.dispose();
        }
    };
}

jarvisUI.particleField = Object.freeze({ createParticleField, PARTICLE_GROUPS });
})(window);
