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

The production field contains 5,080 immutable particles across surface,
volume, flow, and clustered distributions. Point sprites use high-precision
fragment calculations and derivative-based edge coverage, so their circular
silhouette remains smooth across particle size and DPR changes. Separate
micro-core, luminous body, and soft color Halo terms preserve fine structure
without replacing state color with broad white highlights. A wide alpha feather
between normalized radii 0.34 and 0.92 dissolves the particle Halo well before
the precise sprite boundary. The Core-wide volumetric Aura retains its original
power-curve falloff and closely nested low-opacity layers. It deliberately uses
the established Composer output path rather than forcing renderer-level sRGB
encoding, which made subtle additive layer differences read as separate bands
at high DPR. Adaptive DPR steps remain 1.5, 2.0, and 2.5 for particle detail.

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
