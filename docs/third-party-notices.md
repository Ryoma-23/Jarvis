# Third-party notices

## Local speaker observation (v1.50)

- Inference: existing sherpa-onnx 1.13.8, Apache-2.0.
- Model: WeSpeaker VoxCeleb ResNet34, `wespeaker_en_voxceleb_resnet34.onnx`.
- Distributor: https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models
- SHA-256: `5ef208a9da1453335308a6b6f4e6dfbd7e183a38b604de0a57664f45d257fe94`.
- Model attribution: WeSpeaker / WeNet community; trained on VoxCeleb.
- Upstream model-license statement: https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md
  specifies Creative Commons Attribution 4.0 International for VoxCeleb pretrained models:
  https://creativecommons.org/licenses/by/4.0/
- WeSpeaker code license (separate from model): Apache-2.0.
- The unmodified public model is downloaded into ignored local `data/speaker/models/`;
  it is not committed or bundled into the application sources.
- No user audio is sent to the model distributor. Japanese accuracy is unverified.

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
