(function initializeJarvisCore(global) {
"use strict";

const THREE = global.THREE;
const jarvisUI = global.JarvisUI;
const canvas = jarvisUI && jarvisUI.dom
    ? jarvisUI.dom.elements.coreCanvas
    : null;
const stage = canvas ? canvas.closest(".core-stage") : null;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const stateColors = Object.freeze({
    idle: 0x79e8ff,
    connecting: 0xf1bd6d,
    listening: 0x79e8ff,
    thinking: 0xa69aff,
    speaking: 0xa4f6df,
    error: 0xff6f7d
});
const particleCount = 1000;
const particleSphereRadius = 1.1178;
const particleSphereJitter = 0.0972;
const activeFrameDurationMs = 1000 / 30;
const idleFrameDurationMs = 1000 / 20;
const qualityDprCaps = Object.freeze([1.25, 1.5, 1.75]);
const qualitySampleSize = 90;
const qualityChangeCooldownMs = 15_000;
const stateProfiles = Object.freeze({
    idle: Object.freeze({ speed: 0.055, motion: 0.006, pulse: 0.008, coreMotion: 0.025, coreIntensity: 0.78 }),
    connecting: Object.freeze({ speed: 0.10, motion: 0.010, pulse: 0.014, coreMotion: 0.040, coreIntensity: 0.84 }),
    listening: Object.freeze({ speed: 0.085, motion: 0.014, pulse: 0.024, coreMotion: 0.055, coreIntensity: 0.92 }),
    thinking: Object.freeze({ speed: 0.18, motion: 0.020, pulse: 0.016, coreMotion: 0.070, coreIntensity: 0.98 }),
    speaking: Object.freeze({ speed: 0.12, motion: 0.016, pulse: 0.034, coreMotion: 0.065, coreIntensity: 1.0 }),
    error: Object.freeze({ speed: 0.025, motion: 0.004, pulse: 0.006, coreMotion: 0.018, coreIntensity: 0.72 })
});
const coreLayerConfigs = Object.freeze([
    Object.freeze({ count: 260, radius: 0.5832, jitter: 0.18, size: 0.034, opacity: 0.42, speed: 0.42, phase: 0.0, whiteMix: 0.08 }),
    Object.freeze({ count: 170, radius: 0.3483, jitter: 0.24, size: 0.043, opacity: 0.66, speed: -0.64, phase: 2.1, whiteMix: 0.20 }),
    Object.freeze({ count: 90, radius: 0.162, jitter: 0.32, size: 0.060, opacity: 0.88, speed: 0.88, phase: 4.2, whiteMix: 0.46 })
]);

let renderer = null;
let scene = null;
let camera = null;
let particleSphere = null;
let particleMaterial = null;
let particleBasePositions = null;
let coreLayers = [];
let particleTexture = null;
let resizeObserver = null;
let unsubscribeState = null;
let animationFrameId = null;
let lastFrameAt = 0;
let disposed = false;
let elapsedSeconds = 0;
let activeProfile = stateProfiles.idle;
let activeColor = stateColors.idle;
let activeJarvisState = "idle";
let audioLevel = 0;
let qualityLevel = qualityDprCaps.length - 1;
let qualitySampleCount = 0;
let slowFrameCount = 0;
let stableQualityWindows = 0;
let lastQualityChangeAt = 0;
let visualValues = { speed: 0.055, motion: 0.006, pulse: 0.008, coreMotion: 0.025, coreIntensity: 0.78 };


function createParticleTexture() {
    const textureCanvas = document.createElement("canvas");
    textureCanvas.width = 96;
    textureCanvas.height = 96;
    const context = textureCanvas.getContext("2d");
    const gradient = context.createRadialGradient(48, 48, 0, 48, 48, 47);

    gradient.addColorStop(0, "rgba(255, 255, 255, 1)");
    gradient.addColorStop(0.20, "rgba(255, 255, 255, 0.98)");
    gradient.addColorStop(0.55, "rgba(255, 255, 255, 0.58)");
    gradient.addColorStop(0.82, "rgba(255, 255, 255, 0.16)");
    gradient.addColorStop(1, "rgba(255, 255, 255, 0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 96, 96);

    const texture = new THREE.CanvasTexture(textureCanvas);
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = false;
    texture.needsUpdate = true;
    return texture;
}


function createParticleGeometry() {
    const positions = new Float32Array(particleCount * 3);
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));

    for (let index = 0; index < particleCount; index += 1) {
        const normalizedIndex = index / (particleCount - 1);
        const y = 1 - normalizedIndex * 2;
        const horizontalRadius = Math.sqrt(1 - y * y);
        const angle = goldenAngle * index;
        const noiseSeed = Math.sin(index * 12.9898) * 43758.5453;
        const noise = noiseSeed - Math.floor(noiseSeed);
        const radius = particleSphereRadius
            + (noise - 0.5) * particleSphereJitter;
        const offset = index * 3;

        positions[offset] = Math.cos(angle) * horizontalRadius * radius;
        positions[offset + 1] = y * radius;
        positions[offset + 2] = Math.sin(angle) * horizontalRadius * radius;
    }

    particleBasePositions = positions.slice();
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(positions, 3)
    );
    geometry.computeBoundingSphere();
    return geometry;
}


function createCoreLayer(config) {
    const positions = new Float32Array(config.count * 3);
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));

    for (let index = 0; index < config.count; index += 1) {
        const normalizedIndex = index / Math.max(1, config.count - 1);
        const y = 1 - normalizedIndex * 2;
        const horizontalRadius = Math.sqrt(1 - y * y);
        const angle = goldenAngle * index + config.phase;
        const noise = (Math.sin(index * 31.17 + config.phase) + 1) * 0.5;
        const radius = config.radius * (1 + (noise - 0.5) * config.jitter);
        const offset = index * 3;

        positions[offset] = Math.cos(angle) * horizontalRadius * radius;
        positions[offset + 1] = y * radius;
        positions[offset + 2] = Math.sin(angle) * horizontalRadius * radius;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.userData.basePositions = positions.slice();
    const layerColor = new THREE.Color(activeColor).lerp(
        new THREE.Color(0xe8fcff),
        config.whiteMix
    );
    const material = new THREE.PointsMaterial({
        color: layerColor,
        size: config.size,
        map: particleTexture,
        sizeAttenuation: true,
        transparent: true,
        opacity: config.opacity * visualValues.coreIntensity,
        alphaTest: 0.015,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });
    const layer = new THREE.Points(geometry, material);
    layer.userData.config = config;
    return layer;
}


function createScene() {
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 20);
    camera.position.set(0, 0, 4.45);
    particleTexture = createParticleTexture();

    particleMaterial = new THREE.PointsMaterial({
        color: stateColors.idle,
        size: 0.027,
        map: particleTexture,
        sizeAttenuation: true,
        transparent: true,
        opacity: 0.86,
        alphaTest: 0.015,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });
    particleSphere = new THREE.Points(
        createParticleGeometry(),
        particleMaterial
    );
    particleSphere.rotation.x = -0.16;
    scene.add(particleSphere);

    coreLayers = coreLayerConfigs.map(function(config) {
        const layer = createCoreLayer(config);
        scene.add(layer);
        return layer;
    });
}


function approach(current, target, amount) {
    return current + (target - current) * amount;
}


function updateVisualValues(deltaSeconds) {
    const blend = Math.min(1, deltaSeconds * 4.5);
    Object.keys(visualValues).forEach(function(key) {
        visualValues[key] = approach(visualValues[key], activeProfile[key], blend);
    });
}


function updateAudioLevel(deltaSeconds) {
    const audioReactive = jarvisUI.audioReactive;
    const levels = audioReactive ? audioReactive.getLevels() : null;
    let targetLevel = 0;

    if (levels && activeJarvisState === "listening") {
        targetLevel = levels.input;
    } else if (levels && activeJarvisState === "speaking") {
        targetLevel = levels.output;
    }

    const responseSpeed = targetLevel > audioLevel ? 12 : 5;
    audioLevel = approach(
        audioLevel,
        targetLevel,
        Math.min(1, deltaSeconds * responseSpeed)
    );
}


function updateParticleMovement() {
    if (!particleSphere || !particleBasePositions) {
        return;
    }

    const positionAttribute = particleSphere.geometry.attributes.position;
    const positions = positionAttribute.array;
    for (let index = 0; index < particleCount; index += 1) {
        const offset = index * 3;
        const wave = Math.sin(elapsedSeconds * 0.9 + index * 0.37);
        const scale = 1 + wave * (visualValues.motion + audioLevel * 0.018);
        positions[offset] = particleBasePositions[offset] * scale;
        positions[offset + 1] = particleBasePositions[offset + 1] * scale;
        positions[offset + 2] = particleBasePositions[offset + 2] * scale;
    }
    positionAttribute.needsUpdate = true;
}


function updateCoreMovement(deltaSeconds) {
    coreLayers.forEach(function(layer, layerIndex) {
        const config = layer.userData.config;
        const basePositions = layer.geometry.userData.basePositions;
        const positionAttribute = layer.geometry.attributes.position;
        const positions = positionAttribute.array;

        for (let index = 0; index < config.count; index += 1) {
            const offset = index * 3;
            const phase = elapsedSeconds * (1.15 + layerIndex * 0.18)
                + index * 0.43 + config.phase;
            const reactiveMotion = visualValues.coreMotion + audioLevel * 0.045;
            const radialWave = 1 + Math.sin(phase) * reactiveMotion;
            const drift = Math.cos(phase * 0.63) * reactiveMotion * 0.08;
            positions[offset] = basePositions[offset] * radialWave - basePositions[offset + 2] * drift;
            positions[offset + 1] = basePositions[offset + 1] * (1 + Math.cos(phase * 0.81) * visualValues.coreMotion);
            positions[offset + 2] = basePositions[offset + 2] * radialWave + basePositions[offset] * drift;
        }

        positionAttribute.needsUpdate = true;
        layer.rotation.y += deltaSeconds * config.speed * visualValues.speed * 2.4;
        layer.rotation.x = Math.sin(elapsedSeconds * 0.22 + config.phase) * 0.12;
        layer.rotation.z = Math.cos(elapsedSeconds * 0.17 + config.phase) * 0.06;
        layer.material.opacity = Math.min(
            1,
            config.opacity * (visualValues.coreIntensity + audioLevel * 0.16)
        );
    });
}


function resize() {
    if (!renderer || !camera || !stage) {
        return;
    }

    const bounds = stage.getBoundingClientRect();
    const width = Math.max(1, Math.round(bounds.width));
    const height = Math.max(1, Math.round(bounds.height));

    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    render();
}


function render() {
    if (renderer && scene && camera && !disposed) {
        renderer.render(scene, camera);
    }
}


function getTargetFrameDurationMs() {
    if (
        activeJarvisState === "listening" ||
        activeJarvisState === "thinking" ||
        activeJarvisState === "speaking"
    ) {
        return activeFrameDurationMs;
    }
    return idleFrameDurationMs;
}


function applyQualityLevel(nextLevel, time) {
    const boundedLevel = Math.max(
        0,
        Math.min(qualityDprCaps.length - 1, nextLevel)
    );
    if (boundedLevel === qualityLevel || !renderer) {
        return;
    }

    qualityLevel = boundedLevel;
    lastQualityChangeAt = time;
    renderer.setPixelRatio(Math.min(
        window.devicePixelRatio || 1,
        qualityDprCaps[qualityLevel]
    ));
    resize();
}


function recordFrameTiming(frameInterval, targetDuration, time) {
    qualitySampleCount += 1;
    if (frameInterval > targetDuration * 1.5) {
        slowFrameCount += 1;
    }

    if (qualitySampleCount < qualitySampleSize) {
        return;
    }

    const slowRatio = slowFrameCount / qualitySampleCount;
    const cooldownComplete = (
        time - lastQualityChangeAt >= qualityChangeCooldownMs
    );

    if (slowRatio > 0.20 && cooldownComplete && qualityLevel > 0) {
        applyQualityLevel(qualityLevel - 1, time);
        stableQualityWindows = 0;
    } else if (slowRatio < 0.03) {
        stableQualityWindows += 1;
        if (
            stableQualityWindows >= 4 &&
            cooldownComplete &&
            qualityLevel < qualityDprCaps.length - 1
        ) {
            applyQualityLevel(qualityLevel + 1, time);
            stableQualityWindows = 0;
        }
    } else {
        stableQualityWindows = 0;
    }

    qualitySampleCount = 0;
    slowFrameCount = 0;
}


function animate(time) {
    animationFrameId = window.requestAnimationFrame(animate);
    const targetFrameDurationMs = getTargetFrameDurationMs();
    const frameInterval = time - lastFrameAt;

    if (frameInterval < targetFrameDurationMs) {
        return;
    }

    const deltaSeconds = Math.min(frameInterval / 1000, 0.1);
    lastFrameAt = time - (frameInterval % targetFrameDurationMs);
    recordFrameTiming(frameInterval, targetFrameDurationMs, time);
    elapsedSeconds += deltaSeconds;
    updateVisualValues(deltaSeconds);
    updateAudioLevel(deltaSeconds);
    updateParticleMovement();
    updateCoreMovement(deltaSeconds);

    if (particleSphere) {
        particleSphere.rotation.y += deltaSeconds * visualValues.speed;
    }
    const pulseScale = 1
        + Math.sin(elapsedSeconds * 1.8) * visualValues.pulse
        + audioLevel * 0.105;
    particleSphere.scale.setScalar(pulseScale);
    coreLayers.forEach(function(layer, index) {
        layer.scale.setScalar(1 + (pulseScale - 1) * (1.2 + index * 0.4));
    });

    render();
}


function stopAnimation() {
    if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }
}


function startAnimation() {
    if (
        disposed ||
        document.hidden ||
        reducedMotion.matches ||
        animationFrameId !== null
    ) {
        render();
        return;
    }

    lastFrameAt = performance.now();
    animationFrameId = window.requestAnimationFrame(animate);
}


function applyState(state) {
    const color = stateColors[state.jarvisState] || stateColors.idle;
    activeJarvisState = state.jarvisState;
    activeColor = color;
    activeProfile = stateProfiles[state.jarvisState] || stateProfiles.idle;

    if (particleMaterial) {
        particleMaterial.color.setHex(color);
    }
    coreLayers.forEach(function(layer) {
        const config = layer.userData.config;
        layer.material.color.setHex(color);
        layer.material.color.lerp(new THREE.Color(0xe8fcff), config.whiteMix);
    });

    render();
}


function disposeObject(object) {
    if (!object) {
        return;
    }
    if (object.geometry) {
        object.geometry.dispose();
    }
    if (object.material) {
        object.material.dispose();
    }
}


function dispose() {
    if (disposed) {
        return;
    }

    disposed = true;
    stopAnimation();
    if (resizeObserver) {
        resizeObserver.disconnect();
    }
    if (unsubscribeState) {
        unsubscribeState();
    }

    disposeObject(particleSphere);
    coreLayers.forEach(disposeObject);
    coreLayers = [];
    if (particleTexture) {
        particleTexture.dispose();
        particleTexture = null;
    }

    if (renderer) {
        renderer.dispose();
    }
    if (stage) {
        stage.dataset.renderer = "fallback";
    }
}


function handleVisibilityChange() {
    if (document.hidden) {
        stopAnimation();
    } else {
        startAnimation();
    }
}


function initialize() {
    if (!THREE || !jarvisUI || !jarvisUI.state || !canvas || !stage) {
        if (jarvisUI && jarvisUI.systemLog) {
            jarvisUI.systemLog.append("CORE_WEBGL_DEPENDENCY_UNAVAILABLE", "error");
        }
        return false;
    }

    try {
        renderer = new THREE.WebGLRenderer({
            canvas: canvas,
            alpha: true,
            antialias: true,
            powerPreference: "low-power"
        });
        renderer.setPixelRatio(Math.min(
            window.devicePixelRatio || 1,
            qualityDprCaps[qualityLevel]
        ));
        renderer.setClearColor(0x000000, 0);
        createScene();

        resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(stage);
        unsubscribeState = jarvisUI.state.subscribe(applyState);
        applyState(jarvisUI.state.getSnapshot());

        canvas.addEventListener("webglcontextlost", function(event) {
            event.preventDefault();
            dispose();
            if (jarvisUI.systemLog) {
                jarvisUI.systemLog.append("CORE_WEBGL_CONTEXT_LOST", "error");
            }
        });
        document.addEventListener("visibilitychange", handleVisibilityChange);
        reducedMotion.addEventListener("change", function() {
            stopAnimation();
            startAnimation();
        });
        window.addEventListener("beforeunload", dispose, { once: true });

        stage.dataset.renderer = "webgl";
        resize();
        startAnimation();

        jarvisUI.core = Object.freeze({
            render: render,
            dispose: dispose,
            isAvailable: function() {
                return !disposed;
            }
        });

        if (jarvisUI.systemLog) {
            jarvisUI.systemLog.append("CORE_WEBGL_READY");
        }
        return true;
    } catch (error) {
        console.error("Jarvis Core WebGL initialization failed:", error);
        dispose();
        if (jarvisUI && jarvisUI.systemLog) {
            jarvisUI.systemLog.append("CORE_WEBGL_UNAVAILABLE", "error");
        }
        return false;
    }
}


initialize();
})(window);
