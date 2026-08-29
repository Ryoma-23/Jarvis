# Jarvis shader architecture

## Render pipeline

`shader-core-runtime.js` creates one Three.js Scene containing the spatial
background, three planar volumetric Glow layers, and one immutable particle
field. EffectComposer renders the scene through RenderPass and UnrealBloomPass;
failure falls back to direct WebGLRenderer output.

Particle positions are generated once in `particle-field.js`. The CPU updates
only uniforms. Vertex Shader animation combines rotation, organic flow,
attraction, drift, audio resonance, state waves, Tool direction, Error impulse,
and startup formation. Fragment Shader produces circular, depth-faded,
state-colored points with selective HDR energy for Bloom.

## Startup uniform

`uIntroProgress` is normalized from zero to one over 1650ms. Background alpha
rises first. Core particles then gain point size and opacity while contracting
from a dispersed radius. Volumetric Glow follows after the nucleus is visible.
The uniform stays at one after completion and does not become another animation
loop or state-machine state.

## Audio and state uniforms

Surface Resonance routes microphone input only while Listening and Jarvis output
only while Speaking. Noise gating and asymmetric easing prevent silent jitter.
State profiles provide motion, radius, attraction, Bloom, particle size, Aura,
direction, and two graded colors. Reduced Motion zeros continuous displacement,
audio resonance, parallax, and transient impulses.

## Resource lifecycle

The runtime owns and releases its requestAnimationFrame, ResizeObserver, state
subscription, DOM/media-query event handlers, Composer targets and passes,
Geometry, Material, Glow planes, background field, and WebGLRenderer. Hidden
documents skip rendering. Adaptive quality changes DPR without rebuilding scene
objects; compact widths reduce the background draw range without reallocating.
