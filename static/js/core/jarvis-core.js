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
const targetFrameDurationMs = 1000 / 30;

let renderer = null;
let scene = null;
let camera = null;
let particleSphere = null;
let particleMaterial = null;
let innerCore = null;
let innerAura = null;
let resizeObserver = null;
let unsubscribeState = null;
let animationFrameId = null;
let lastFrameAt = 0;
let disposed = false;


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
        const radius = 1.38 + (noise - 0.5) * 0.12;
        const offset = index * 3;

        positions[offset] = Math.cos(angle) * horizontalRadius * radius;
        positions[offset + 1] = y * radius;
        positions[offset + 2] = Math.sin(angle) * horizontalRadius * radius;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(positions, 3)
    );
    geometry.computeBoundingSphere();
    return geometry;
}


function createScene() {
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 20);
    camera.position.set(0, 0, 4.45);

    particleMaterial = new THREE.PointsMaterial({
        color: stateColors.idle,
        size: 0.024,
        sizeAttenuation: true,
        transparent: true,
        opacity: 0.78,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });
    particleSphere = new THREE.Points(
        createParticleGeometry(),
        particleMaterial
    );
    particleSphere.rotation.x = -0.16;
    scene.add(particleSphere);

    innerAura = new THREE.Mesh(
        new THREE.SphereGeometry(0.58, 36, 24),
        new THREE.MeshBasicMaterial({
            color: stateColors.idle,
            transparent: true,
            opacity: 0.075,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        })
    );
    scene.add(innerAura);

    innerCore = new THREE.Mesh(
        new THREE.SphereGeometry(0.23, 32, 20),
        new THREE.MeshBasicMaterial({
            color: 0xe8fcff,
            transparent: true,
            opacity: 0.72,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        })
    );
    scene.add(innerCore);
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


function animate(time) {
    animationFrameId = window.requestAnimationFrame(animate);

    if (time - lastFrameAt < targetFrameDurationMs) {
        return;
    }

    const deltaSeconds = Math.min((time - lastFrameAt) / 1000, 0.1);
    lastFrameAt = time;

    if (particleSphere) {
        particleSphere.rotation.y += deltaSeconds * 0.055;
    }
    if (innerAura) {
        innerAura.rotation.y -= deltaSeconds * 0.035;
    }

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

    if (particleMaterial) {
        particleMaterial.color.setHex(color);
    }
    if (innerAura) {
        innerAura.material.color.setHex(color);
    }

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
    disposeObject(innerAura);
    disposeObject(innerCore);

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
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
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
