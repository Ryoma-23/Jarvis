# Third-party notices

## Three.js

- Version: 0.128.0
- Source: official `three` package from the npm registry
- License: MIT
- Runtime file: `static/vendor/three/three.min.js`
- Examples files:
  - `static/vendor/three/examples/js/postprocessing/Pass.js`
  - `static/vendor/three/examples/js/postprocessing/EffectComposer.js`
  - `static/vendor/three/examples/js/postprocessing/RenderPass.js`
  - `static/vendor/three/examples/js/postprocessing/ShaderPass.js`
  - `static/vendor/three/examples/js/postprocessing/UnrealBloomPass.js`
  - `static/vendor/three/examples/js/shaders/CopyShader.js`
  - `static/vendor/three/examples/js/shaders/LuminosityHighPassShader.js`

The post-processing files are unmodified official Examples sources from the
same Three.js 0.128.0 npm release. They are served locally; the application has
no runtime CDN dependency.

The complete upstream license text is stored in
`static/vendor/three/LICENSE`.

Visual Phase G adds no third-party runtime dependency. Its startup sequence,
micro-interactions, color grading, and lifecycle cleanup use local application
CSS and the existing Three.js shader/post-processing stack listed above.

## Chroma

- Package: `chromadb`
- Version: 1.5.9
- Source: official Python package from PyPI
- License: Apache License 2.0
- Runtime use: local regenerable vector index under `data/chroma/`

Chroma is introduced in Notion/RAG Phase 7. Notion remains the source of truth;
the local Chroma data contains only derived Chunk documents, Metadata, and
Embedding vectors and can be regenerated.
