(function initializeShaderCoreRuntime(global) {
"use strict";

const THREE = global.THREE;
const jarvisUI = global.JarvisUI;
const canvas = jarvisUI && jarvisUI.dom ? jarvisUI.dom.elements.coreCanvas : null;
const stage = canvas ? canvas.closest(".core-stage") : null;
const reducedMotion = global.matchMedia("(prefers-reduced-motion: reduce)");
if (!THREE || !canvas || !stage || !jarvisUI.particleField) return;

const activeFrameDurationMs = 1000 / 30;
const idleFrameDurationMs = 1000 / 20;
const qualityDprCaps = Object.freeze([1.25, 1.5, 1.75]);
const qualitySampleSize = 90;
const qualityChangeCooldownMs = 15000;
const stateProfiles = Object.freeze({
    idle: { blend: 0.12, motion: 0.72, scale: 0.94, primary: 0x55e6ff, secondary: 0x287bff },
    connecting: { blend: 0.42, motion: 0.90, scale: 0.96, primary: 0xffc46b, secondary: 0xff7d55 },
    listening: { blend: 0.62, motion: 1.08, scale: 0.98, primary: 0x54edff, secondary: 0x318cff },
    thinking: { blend: 1.00, motion: 1.35, scale: 1.00, primary: 0xa98cff, secondary: 0x43d9ff },
    speaking: { blend: 0.82, motion: 1.18, scale: 1.01, primary: 0x68ffd1, secondary: 0x36bfff },
    error: { blend: 0.22, motion: 0.48, scale: 0.92, primary: 0xff6478, secondary: 0xff9b62 }
});

let renderer;
let scene;
let camera;
let field;
let glow;
let postProcessing;
let resizeObserver;
let unsubscribeState;
let animationFrameId;
let lastFrameAt = 0;
let elapsedSeconds = 0;
let activeState = "idle";
let toolAccentTarget = 0;
let transitionPulse = 0;
let audioPeak = 0;
let postProcessingFailed = false;
let targetProfile = stateProfiles.idle;
let qualityLevel = qualityDprCaps.length - 1;
let qualitySamples = 0;
let qualityFrameTotal = 0;
let lastQualityChangeAt = 0;
let disposed = false;
const primaryTarget = new THREE.Color(targetProfile.primary);
const secondaryTarget = new THREE.Color(targetProfile.secondary);

function report(level, code, message) {
    if (jarvisUI.log && typeof jarvisUI.log[level] === "function") jarvisUI.log[level](code, message);
}

function pixelRatio() {
    return Math.min(global.devicePixelRatio || 1, qualityDprCaps[qualityLevel]);
}

function updateRendererDensity() {
    const ratio = pixelRatio();
    renderer.setPixelRatio(ratio);
    field.uniforms.uPixelRatio.value = ratio;
    if (postProcessing) {
        postProcessing.setSize(Math.max(1, stage.clientWidth), Math.max(1, stage.clientHeight), ratio);
    }
}

function resize() {
    const width = Math.max(1, stage.clientWidth);
    const height = Math.max(1, stage.clientHeight);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    updateRendererDensity();
    renderer.setSize(width, height, false);
}

function setState(snapshot) {
    const nextState = snapshot && snapshot.jarvisState;
    const previousState = activeState;
    activeState = stateProfiles[nextState] ? nextState : "idle";
    targetProfile = stateProfiles[activeState];
    if (previousState !== activeState) transitionPulse = 1;
    toolAccentTarget = snapshot && snapshot.activeTool ? 1 : 0;
    primaryTarget.setHex(targetProfile.primary);
    secondaryTarget.setHex(targetProfile.secondary);
}

function readAudioLevel() {
    const audio = jarvisUI.audioReactive;
    if (!audio || typeof audio.getLevels !== "function") return 0;
    const levels = audio.getLevels();
    if (activeState === "listening") return levels.input || 0;
    if (activeState === "speaking") return levels.output || 0;
    return 0;
}

function ease(current, target, amount) {
    return current + (target - current) * amount;
}

function sampleQuality(frameDuration, now) {
    qualityFrameTotal += frameDuration;
    qualitySamples += 1;
    if (qualitySamples < qualitySampleSize) return;
    const average = qualityFrameTotal / qualitySamples;
    qualityFrameTotal = 0;
    qualitySamples = 0;
    if (now - lastQualityChangeAt < qualityChangeCooldownMs) return;
    if (average > 39 && qualityLevel > 0) qualityLevel -= 1;
    else if (average < 28 && qualityLevel < qualityDprCaps.length - 1) qualityLevel += 1;
    else return;
    lastQualityChangeAt = now;
    updateRendererDensity();
}

function render(now) {
    if (disposed) return;
    animationFrameId = global.requestAnimationFrame(render);
    if (document.hidden) return;
    const frameLimit = activeState === "idle" ? idleFrameDurationMs : activeFrameDurationMs;
    const frameDuration = lastFrameAt ? now - lastFrameAt : frameLimit;
    if (frameDuration < frameLimit) return;
    lastFrameAt = now;
    elapsedSeconds += Math.min(frameDuration, 100) / 1000;
    sampleQuality(frameDuration, now);

    const uniforms = field.uniforms;
    const easing = reducedMotion.matches ? 1 : 0.055;
    uniforms.uStateBlend.value = ease(uniforms.uStateBlend.value, targetProfile.blend, easing);
    uniforms.uMotionIntensity.value = ease(uniforms.uMotionIntensity.value, reducedMotion.matches ? 0 : targetProfile.motion, easing);
    uniforms.uCoreScale.value = ease(uniforms.uCoreScale.value, targetProfile.scale, easing);
    const currentAudio = readAudioLevel();
    audioPeak = Math.max(currentAudio, audioPeak * 0.88);
    transitionPulse *= reducedMotion.matches ? 0 : 0.91;
    uniforms.uAudioLevel.value = ease(uniforms.uAudioLevel.value, audioPeak, 0.22);
    uniforms.uTransitionPulse.value = transitionPulse;
    uniforms.uToolAccent.value = ease(uniforms.uToolAccent.value, toolAccentTarget, 0.09);
    uniforms.uColorPrimary.value.lerp(primaryTarget, 0.07);
    uniforms.uColorSecondary.value.lerp(secondaryTarget, 0.07);
    if (!reducedMotion.matches) uniforms.uTime.value = elapsedSeconds;
    glow.uniforms.uTime.value = uniforms.uTime.value;
    glow.uniforms.uAudioLevel.value = uniforms.uAudioLevel.value;
    glow.uniforms.uTransitionPulse.value = uniforms.uTransitionPulse.value;
    glow.uniforms.uToolAccent.value = uniforms.uToolAccent.value;
    glow.uniforms.uColorPrimary.value.copy(uniforms.uColorPrimary.value);
    glow.uniforms.uColorSecondary.value.copy(uniforms.uColorSecondary.value);
    if (postProcessing) {
        try {
            postProcessing.render();
        } catch (error) {
            postProcessing.dispose();
            postProcessing = null;
            if (!postProcessingFailed) {
                postProcessingFailed = true;
                report("warn", "CORE_BLOOM_FALLBACK", "Bloom unavailable; standard Core rendering remains active.");
            }
            renderer.render(scene, camera);
        }
    } else renderer.render(scene, camera);
}

function dispose() {
    if (disposed) return;
    disposed = true;
    if (animationFrameId) global.cancelAnimationFrame(animationFrameId);
    if (resizeObserver) resizeObserver.disconnect();
    if (unsubscribeState) unsubscribeState();
    if (postProcessing) postProcessing.dispose();
    if (glow) glow.dispose();
    field.dispose();
    renderer.dispose();
    stage.dataset.renderer = "fallback";
}

try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "high-performance" });
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 20);
    camera.position.z = 3.25;
    field = jarvisUI.particleField.createParticleField({ pixelRatio: pixelRatio() });
    glow = jarvisUI.volumetricGlow.createVolumetricGlow();
    scene.add(glow.object);
    scene.add(field.points);
    try {
        postProcessing = jarvisUI.corePostProcessing.createPostProcessing(renderer, scene, camera);
    } catch (error) {
        postProcessing = null;
        postProcessingFailed = true;
        report("warn", "CORE_BLOOM_FALLBACK", "Bloom unavailable; standard Core rendering remains active.");
    }
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(stage);
    resize();
    if (jarvisUI.state && typeof jarvisUI.state.subscribe === "function") {
        unsubscribeState = jarvisUI.state.subscribe(setState);
    }
    document.addEventListener("visibilitychange", () => { lastFrameAt = 0; });
    global.addEventListener("beforeunload", dispose, { once: true });
    canvas.addEventListener("webglcontextlost", (event) => {
        event.preventDefault();
        report("warn", "CORE_CONTEXT_LOST", "Neural Core graphics context was lost; CSS fallback is active.");
        dispose();
    });
    stage.dataset.renderer = "webgl";
    jarvisUI.shaderCoreActive = true;
    animationFrameId = global.requestAnimationFrame(render);
    report("info", "CORE_SHADER_READY", postProcessing ? "GPU Neural Core and Bloom initialized." : "GPU Neural Core initialized without Bloom.");
} catch (error) {
    if (postProcessing) postProcessing.dispose();
    if (glow) glow.dispose();
    if (field) field.dispose();
    if (renderer) renderer.dispose();
    stage.dataset.renderer = "fallback";
    report("warn", "CORE_SHADER_FALLBACK", error && error.message ? error.message : "GPU Neural Core unavailable.");
}
})(window);
