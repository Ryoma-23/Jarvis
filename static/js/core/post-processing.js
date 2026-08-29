(function initializeCorePostProcessing(global) {
"use strict";

const jarvisUI = global.JarvisUI = global.JarvisUI || {};

function createPostProcessing(renderer, scene, camera) {
    const THREE = global.THREE;
    if (!THREE || !THREE.EffectComposer || !THREE.RenderPass || !THREE.UnrealBloomPass) {
        throw new Error("Three.js post-processing dependencies are unavailable.");
    }

    renderer.toneMapping = THREE.ReinhardToneMapping;
    renderer.toneMappingExposure = 0.92;
    const composer = new THREE.EffectComposer(renderer);
    const renderPass = new THREE.RenderPass(scene, camera);
    const bloomPass = new THREE.UnrealBloomPass(new THREE.Vector2(1, 1), 0.72, 0.30, 0.88);
    bloomPass.threshold = 0.88;
    bloomPass.strength = 0.72;
    bloomPass.radius = 0.30;
    composer.addPass(renderPass);
    composer.addPass(bloomPass);

    return {
        render() { composer.render(); },
        setSize(width, height, pixelRatio) {
            composer.setPixelRatio(pixelRatio);
            composer.setSize(width, height);
        },
        dispose() {
            bloomPass.dispose();
            composer.dispose();
        }
    };
}

jarvisUI.corePostProcessing = Object.freeze({ createPostProcessing });
})(window);
