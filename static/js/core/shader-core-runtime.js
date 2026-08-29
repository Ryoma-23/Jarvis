(function initializeShaderCoreRuntime(global) {
"use strict";

const THREE = global.THREE;
const jarvisUI = global.JarvisUI;
const canvas = jarvisUI && jarvisUI.dom ? jarvisUI.dom.elements.coreCanvas : null;
const stage = canvas ? canvas.closest(".core-stage") : null;
const reducedMotion = global.matchMedia("(prefers-reduced-motion: reduce)");
if (!THREE || !canvas || !stage || !jarvisUI.particleField || !jarvisUI.coreStateTransitions || !jarvisUI.spatialBackground) return;

const activeFrameDurationMs = 1000 / 30;
const idleFrameDurationMs = 1000 / 20;
const qualityDprCaps = Object.freeze([1.25, 1.5, 1.75]);
const qualitySampleSize = 90;
const qualityChangeCooldownMs = 15000;
const introDurationMs = 1650;
let renderer;
let scene;
let camera;
let field;
let spatialBackground;
let glow;
let postProcessing;
let resizeObserver;
let unsubscribeState;
let animationFrameId;
let lastFrameAt = 0;
let elapsedSeconds = 0;
let activeState = "idle";
let realtimeConnected = false;
let toolAccentTarget = 0;
let transitionPulse = 0;
let audioPeak = 0;
let resonanceLevel = 0;
let postProcessingFailed = false;
const transitions = jarvisUI.coreStateTransitions.createStateTransitions("idle");
let qualityLevel = qualityDprCaps.length - 1;
let qualitySamples = 0;
let qualityFrameTotal = 0;
let lastQualityChangeAt = 0;
let disposed = false;
let introStartedAt = global.performance.now();
let introComplete = reducedMotion.matches;

function finishIntro() {
    if (introComplete) return;
    introComplete = true;
    document.body.removeAttribute("data-core-intro");
}

function introProgress(now) {
    if (introComplete || reducedMotion.matches) {
        finishIntro();
        return 1;
    }
    const progress = Math.min(1, Math.max(0, (now - introStartedAt) / introDurationMs));
    if (progress >= 1) finishIntro();
    return progress;
}

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
    spatialBackground.uniforms.uPixelRatio.value = ratio;
    if (postProcessing) {
        postProcessing.setSize(Math.max(1, stage.clientWidth), Math.max(1, stage.clientHeight), ratio);
    }
}

function resize() {
    const width = Math.max(1, stage.clientWidth);
    const height = Math.max(1, stage.clientHeight);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    spatialBackground.setCompact(width <= 680);
    updateRendererDensity();
    renderer.setSize(width, height, false);
}

function setState(snapshot) {
    const latestSnapshot = jarvisUI.state.getSnapshot ? jarvisUI.state.getSnapshot() : snapshot;
    const nextState = latestSnapshot && latestSnapshot.jarvisState;
    const previousState = activeState;
    activeState = jarvisUI.coreStateTransitions.profiles[nextState] ? nextState : "idle";
    transitions.setState(activeState);
    realtimeConnected = Boolean(latestSnapshot && latestSnapshot.connectionStatus === "connected");
    if (!realtimeConnected) {
        resonanceLevel = 0;
        if (field) field.uniforms.uResonanceLevel.value = 0;
    }
    if (previousState !== activeState) transitionPulse = 1;
    toolAccentTarget = latestSnapshot && latestSnapshot.activeTool ? 1 : 0;
}

function readAudioLevels() {
    const audio = jarvisUI.audioReactive;
    if (!audio || typeof audio.getLevels !== "function") return { input: 0, output: 0 };
    return audio.getLevels();
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
    const startupProgress = introProgress(now);
    const deltaSeconds = Math.min(frameDuration, 100) / 1000;
    const transition = transitions.update(deltaSeconds, reducedMotion.matches);
    const profile = transition.profile;
    uniforms.uStateBlend.value = profile.noiseAmount;
    uniforms.uMotionIntensity.value = reducedMotion.matches ? 0 : 1;
    const breathing = activeState === "idle" && !reducedMotion.matches ? Math.sin(elapsedSeconds * 0.72) * 0.008 : 0;
    uniforms.uCoreScale.value = 1 + breathing;
    uniforms.uIntroProgress.value = startupProgress;
    uniforms.uRotationSpeed.value = profile.rotationSpeed;
    uniforms.uNoiseAmount.value = profile.noiseAmount;
    uniforms.uParticleRadius.value = profile.particleRadius;
    uniforms.uAttraction.value = profile.attraction;
    uniforms.uAudioResponse.value = profile.audioResponse;
    uniforms.uParticleSizeScale.value = profile.particleSize;
    uniforms.uOrbitSync.value = profile.orbitSync;
    uniforms.uAxisTilt.value = profile.axisTilt;
    uniforms.uInwardFlow.value = profile.inwardFlow;
    uniforms.uOutwardWave.value = profile.outwardWave;
    uniforms.uErrorBurst.value = transition.errorBurst;
    const audioLevels = readAudioLevels();
    const currentAudio = realtimeConnected && activeState === "listening" ? audioLevels.input || 0 : realtimeConnected && activeState === "speaking" ? audioLevels.output || 0 : 0;
    const resonanceMode = activeState === "listening" ? 1 : activeState === "speaking" ? 2 : 0;
    const gatedResonance = currentAudio > 0.035 ? currentAudio : 0;
    if (!realtimeConnected || resonanceMode === 0 || reducedMotion.matches) resonanceLevel = 0;
    else resonanceLevel += (gatedResonance - resonanceLevel) * (gatedResonance > resonanceLevel ? 0.30 : 0.11);
    if (resonanceLevel < 0.004) resonanceLevel = 0;
    uniforms.uResonanceMode.value = reducedMotion.matches ? 0 : resonanceMode;
    uniforms.uResonanceLevel.value = resonanceLevel;
    uniforms.uResonancePhase.value = elapsedSeconds;
    audioPeak = Math.max(currentAudio * profile.audioResponse, audioPeak * 0.88);
    transitionPulse *= reducedMotion.matches ? 0 : 0.91;
    uniforms.uAudioLevel.value = ease(uniforms.uAudioLevel.value, audioPeak, 0.22);
    uniforms.uTransitionPulse.value = Math.max(transitionPulse * 0.35, transition.stabilityWave);
    uniforms.uToolAccent.value = ease(uniforms.uToolAccent.value, toolAccentTarget, 0.09);
    uniforms.uColorPrimary.value.setRGB(profile.primary[0], profile.primary[1], profile.primary[2]);
    uniforms.uColorSecondary.value.setRGB(profile.secondary[0], profile.secondary[1], profile.secondary[2]);
    if (!reducedMotion.matches) uniforms.uTime.value = elapsedSeconds;
    spatialBackground.uniforms.uTime.value = reducedMotion.matches ? 0 : elapsedSeconds;
    spatialBackground.uniforms.uIntroProgress.value = startupProgress;
    spatialBackground.uniforms.uStateEnergy.value = profile.noiseAmount * 0.12;
    spatialBackground.uniforms.uParallax.value.set(
        reducedMotion.matches ? 0 : Math.sin(elapsedSeconds * 0.045 + profile.axisTilt) * 0.035,
        reducedMotion.matches ? 0 : Math.cos(elapsedSeconds * 0.038 + profile.rotationSpeed) * 0.022
    );
    spatialBackground.uniforms.uColor.value.copy(uniforms.uColorSecondary.value).multiplyScalar(0.34);
    glow.uniforms.uTime.value = uniforms.uTime.value;
    glow.uniforms.uIntroProgress.value = startupProgress;
    glow.uniforms.uAudioLevel.value = uniforms.uAudioLevel.value;
    glow.uniforms.uTransitionPulse.value = uniforms.uTransitionPulse.value;
    glow.uniforms.uToolAccent.value = uniforms.uToolAccent.value;
    glow.uniforms.uAuraDensity.value = profile.auraDensity;
    glow.uniforms.uColorPrimary.value.copy(uniforms.uColorPrimary.value);
    glow.uniforms.uColorSecondary.value.copy(uniforms.uColorSecondary.value);
    if (postProcessing) postProcessing.setBloomStrength(profile.bloomStrength + audioPeak * 0.14 + uniforms.uToolAccent.value * 0.06);
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
    document.body.removeAttribute("data-core-intro");
    if (animationFrameId) global.cancelAnimationFrame(animationFrameId);
    if (resizeObserver) resizeObserver.disconnect();
    if (unsubscribeState) unsubscribeState();
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    reducedMotion.removeEventListener("change", handleReducedMotionChange);
    canvas.removeEventListener("webglcontextlost", handleContextLost);
    global.removeEventListener("beforeunload", dispose);
    if (postProcessing) postProcessing.dispose();
    if (spatialBackground) spatialBackground.dispose();
    if (glow) glow.dispose();
    field.dispose();
    renderer.dispose();
    stage.dataset.renderer = "fallback";
}

function handleVisibilityChange() {
    lastFrameAt = 0;
}

function handleReducedMotionChange() {
    if (reducedMotion.matches) finishIntro();
}

function handleContextLost(event) {
    event.preventDefault();
    report("warn", "CORE_CONTEXT_LOST", "Neural Core graphics context was lost; CSS fallback is active.");
    dispose();
}

try {
    if (!introComplete) document.body.dataset.coreIntro = "true";
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "high-performance" });
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 20);
    camera.position.z = 3.25;
    field = jarvisUI.particleField.createParticleField({ pixelRatio: pixelRatio() });
    spatialBackground = jarvisUI.spatialBackground.createSpatialBackground({ pixelRatio: pixelRatio() });
    glow = jarvisUI.volumetricGlow.createVolumetricGlow();
    scene.add(spatialBackground.object);
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
        setState(jarvisUI.state.getSnapshot());
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);
    reducedMotion.addEventListener("change", handleReducedMotionChange);
    global.addEventListener("beforeunload", dispose, { once: true });
    canvas.addEventListener("webglcontextlost", handleContextLost);
    stage.dataset.renderer = "webgl";
    jarvisUI.shaderCoreActive = true;
    animationFrameId = global.requestAnimationFrame(render);
    report("info", "CORE_SHADER_READY", postProcessing ? "GPU Neural Core and Bloom initialized." : "GPU Neural Core initialized without Bloom.");
} catch (error) {
    document.body.removeAttribute("data-core-intro");
    if (postProcessing) postProcessing.dispose();
    if (spatialBackground) spatialBackground.dispose();
    if (glow) glow.dispose();
    if (field) field.dispose();
    if (renderer) renderer.dispose();
    stage.dataset.renderer = "fallback";
    report("warn", "CORE_SHADER_FALLBACK", error && error.message ? error.message : "GPU Neural Core unavailable.");
}
})(window);
