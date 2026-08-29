(function initializeCoreMaterials(global) {
"use strict";

const jarvisUI = global.JarvisUI = global.JarvisUI || {};

function createParticleMaterial(options) {
    const THREE = global.THREE;
    const shaders = jarvisUI.coreShaders;
    if (!THREE || !shaders || !shaders.particleVertex || !shaders.particleFragment) {
        throw new Error("Particle shader dependencies are unavailable.");
    }

    const settings = options || {};
    return new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 },
            uStateBlend: { value: 0 },
            uAudioLevel: { value: 0 },
            uMotionIntensity: { value: 1 },
            uCoreScale: { value: 1 },
            uTransitionPulse: { value: 0 },
            uToolAccent: { value: 0 },
            uColorPrimary: { value: new THREE.Color(settings.primaryColor || 0x65e8ff) },
            uColorSecondary: { value: new THREE.Color(settings.secondaryColor || 0x3478ff) },
            uPixelRatio: { value: settings.pixelRatio || 1 }
        },
        vertexShader: shaders.particleVertex,
        fragmentShader: shaders.particleFragment,
        transparent: true,
        depthWrite: false,
        depthTest: true,
        blending: THREE.AdditiveBlending
    });
}

jarvisUI.coreMaterials = Object.freeze({ createParticleMaterial });
})(window);
