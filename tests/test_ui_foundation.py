import unittest

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"


class UiFoundationContractTests(unittest.TestCase):
    def test_foundation_scripts_load_before_existing_application(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

        expected_scripts = (
            "/static/js/app-state.js",
            "/static/js/dom.js",
            "/static/js/ui/jarvis-state.js",
            "/static/js/ui/system-log.js",
            "/static/js/ui/status-bar.js",
            "/static/js/ui/ui-state-controller.js",
            "/static/script.js",
        )
        positions = [index.index(script) for script in expected_scripts]

        self.assertEqual(positions, sorted(positions))

    def test_required_dom_contract_is_centralized(self):
        dom = (STATIC_DIR / "js" / "dom.js").read_text(encoding="utf-8")
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

        required_ids = (
            "send-button",
            "new-conversation-button",
            "conversation-status",
            "message-input",
            "chat-area",
            "voice-connect-button",
            "voice-disconnect-button",
            "voice-reconnect-button",
            "voice-status",
        )

        for element_id in required_ids:
            self.assertIn(f'id="{element_id}"', index)
            self.assertIn(f'byId("{element_id}")', dom)

        self.assertIn("missingRequiredElements", dom)

    def test_optional_phase_two_elements_are_safe(self):
        dom = (STATIC_DIR / "js" / "dom.js").read_text(encoding="utf-8")
        system_log = (
            STATIC_DIR / "js" / "ui" / "system-log.js"
        ).read_text(encoding="utf-8")
        status_bar = (
            STATIC_DIR / "js" / "ui" / "status-bar.js"
        ).read_text(encoding="utf-8")

        for element_id in ("core-area", "core-state", "system-log", "status-bar"):
            self.assertIn(f'byId("{element_id}")', dom)

        self.assertIn("if (!logContainer)", system_log)
        self.assertIn("if (!statusBar)", status_bar)

    def test_phase_two_layout_exposes_core_log_chat_and_status_regions(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        style = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

        for expected in (
            '<header class="app-header">',
            'id="system-log"',
            'id="core-area"',
            'id="core-state"',
            'id="chat-area"',
            'id="status-bar"',
        ):
            self.assertIn(expected, index)

        self.assertIn('name="viewport"', index)
        self.assertIn("grid-template-columns:", style)
        self.assertIn("@media (max-width: 900px)", style)
        self.assertIn("@media (max-width: 680px)", style)
        self.assertIn("@media (prefers-reduced-motion: reduce)", style)

    def test_phase_two_controls_remain_accessible(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('for="message-input"', index)
        self.assertIn('aria-label="メッセージを送信"', index)
        self.assertIn('aria-label="音声コントロール"', index)
        self.assertIn('role="log"', index)

    def test_phase_three_status_surfaces_share_connection_state(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        dom = (STATIC_DIR / "js" / "dom.js").read_text(encoding="utf-8")
        status = (
            STATIC_DIR / "js" / "ui" / "status-bar.js"
        ).read_text(encoding="utf-8")

        self.assertIn('id="header-connection-status"', index)
        self.assertIn('data-status="microphone"', index)
        self.assertIn('byId("header-connection-status")', dom)
        self.assertIn("connectionLabels", status)
        self.assertIn("microphoneLabels", status)
        self.assertIn("headerStatus.dataset.connectionStatus", status)

    def test_phase_three_visual_states_and_accessibility_preferences_exist(self):
        style = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
        jarvis_state = (
            STATIC_DIR / "js" / "ui" / "jarvis-state.js"
        ).read_text(encoding="utf-8")

        for state in ("listening", "thinking", "speaking", "error"):
            self.assertIn(f'body[data-jarvis-state="{state}"]', style)

        self.assertIn("@media (prefers-contrast: more)", style)
        self.assertIn("#chat-area:empty::before", style)
        self.assertIn(".message-meta", style)
        self.assertIn("stateCaptions", jarvis_state)

    def test_phase_four_state_controller_has_explicit_priority_and_signals(self):
        controller = (
            STATIC_DIR / "js" / "ui" / "ui-state-controller.js"
        ).read_text(encoding="utf-8")
        script = (STATIC_DIR / "script.js").read_text(encoding="utf-8")

        priorities = (
            'signals.connectionStatus === "error"',
            "signals.listening",
            "signals.speaking",
            "signals.thinking || signals.toolDepth > 0",
            'signals.connectionStatus === "connecting"',
        )
        positions = [controller.index(value) for value in priorities]
        self.assertEqual(positions, sorted(positions))

        for method in (
            "speechStarted",
            "speechStopped",
            "speechFailed",
            "responseCreated",
            "responseDone",
            "audioStarted",
            "audioStopped",
            "toolStarted",
            "toolFinished",
            "reset",
        ):
            self.assertIn(f"{method}: {method}", controller)

        for call in (
            "controller.speechStarted()",
            "controller.speechStopped()",
            "controller.speechFailed()",
            "controller.responseCreated()",
            "controller.responseDone(isCompletedFunctionCall)",
            "controller.audioStarted()",
            "controller.audioStopped()",
            "controller.toolStarted(toolName)",
            "controller.toolFinished(",
            "controller.reset()",
        ):
            self.assertIn(call, script)

    def test_phase_four_connecting_state_is_renderable(self):
        jarvis_state = (
            STATIC_DIR / "js" / "ui" / "jarvis-state.js"
        ).read_text(encoding="utf-8")
        style = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn('"connecting"', jarvis_state)
        self.assertIn('body[data-jarvis-state="connecting"]', style)

    def test_phase_five_core_uses_local_three_module_with_css_fallback(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        dom = (STATIC_DIR / "js" / "dom.js").read_text(encoding="utf-8")
        style = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
        runtime = (
            STATIC_DIR / "js" / "core" / "shader-core-runtime.js"
        ).read_text(encoding="utf-8")
        field = (STATIC_DIR / "js" / "core" / "particle-field.js").read_text(encoding="utf-8")
        three_module = STATIC_DIR / "vendor" / "three" / "three.min.js"
        three_license = (
            STATIC_DIR / "vendor" / "three" / "LICENSE"
        ).read_text(encoding="utf-8")

        self.assertIn('id="jarvis-core-canvas"', index)
        self.assertNotIn('type="module"', index)
        self.assertIn('/static/vendor/three/three.min.js?v=0.128.0', index)
        self.assertIn("/static/js/core/jarvis-core.js", index)
        self.assertLess(
            index.index("/static/vendor/three/three.min.js"),
            index.index("/static/js/core/jarvis-core.js"),
        )
        self.assertIn('byId("jarvis-core-canvas")', dom)
        self.assertIn("const THREE = global.THREE;", runtime)
        self.assertIn("new THREE.WebGLRenderer", runtime)
        self.assertIn("new THREE.Points(", field)
        self.assertNotIn("new THREE.SphereGeometry", field)
        self.assertIn('stage.dataset.renderer = "webgl"', runtime)
        self.assertIn('stage.dataset.renderer = "fallback"', runtime)
        self.assertIn('.core-stage[data-renderer="webgl"] .core-canvas', style)
        self.assertGreater(three_module.stat().st_size, 300_000)
        self.assertIn("MIT License", three_license)
        self.assertIn("Copyright", three_license)

    def test_phase_five_core_limits_background_rendering_and_gpu_cost(self):
        core = (
            STATIC_DIR / "js" / "core" / "shader-core-runtime.js"
        ).read_text(encoding="utf-8")

        self.assertIn("const activeFrameDurationMs = 1000 / 30", core)
        self.assertIn("const idleFrameDurationMs = 1000 / 20", core)
        self.assertIn('powerPreference: "high-performance"', core)
        self.assertIn("qualityDprCaps[qualityLevel]", core)
        self.assertIn('document.addEventListener("visibilitychange"', core)
        self.assertIn("document.hidden", core)
        self.assertIn("reducedMotion.matches", core)
        self.assertIn("renderer.dispose()", core)

    def test_visual_phase_a_uses_shader_particles_and_static_geometry(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        material = (STATIC_DIR / "js" / "core" / "core-materials.js").read_text(encoding="utf-8")
        field = (STATIC_DIR / "js" / "core" / "particle-field.js").read_text(encoding="utf-8")
        runtime = (STATIC_DIR / "js" / "core" / "shader-core-runtime.js").read_text(encoding="utf-8")

        expected_order = ["particle-vertex.js", "particle-fragment.js", "core-materials.js", "particle-field.js", "shader-core-runtime.js"]
        self.assertEqual(sorted(expected_order, key=index.index), expected_order)
        self.assertIn("new THREE.ShaderMaterial", material)
        self.assertNotIn("THREE.PointsMaterial", material)
        for attribute in ("aBasePosition", "aSeed", "aParticleSize", "aBrightness", "aSpeed", "aPhase", "aLayer"):
            self.assertIn(attribute, field)
        self.assertIn("surface: 2200", field)
        self.assertIn("volume: 1600", field)
        self.assertIn("flow: 650", field)
        self.assertIn("cluster: 630", field)
        self.assertNotIn("needsUpdate", field)
        self.assertNotIn("needsUpdate", runtime)

    def test_visual_phase_a_shader_has_required_uniforms_and_round_glow(self):
        vertex = (STATIC_DIR / "js" / "core" / "shaders" / "particle-vertex.js").read_text(encoding="utf-8")
        fragment = (STATIC_DIR / "js" / "core" / "shaders" / "particle-fragment.js").read_text(encoding="utf-8")
        material = (STATIC_DIR / "js" / "core" / "core-materials.js").read_text(encoding="utf-8")

        for uniform in ("uTime", "uStateBlend", "uAudioLevel", "uMotionIntensity", "uCoreScale", "uColorPrimary", "uColorSecondary", "uPixelRatio"):
            self.assertIn(uniform, vertex + fragment)
            self.assertIn(uniform, material)
        self.assertIn("gl_PointCoord", fragment)
        self.assertIn("discard", fragment)
        self.assertIn("brightCore", fragment)
        self.assertIn("distanceScale", vertex)

    def test_visual_phase_b_uses_local_official_bloom_pipeline(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        post = (STATIC_DIR / "js" / "core" / "post-processing.js").read_text(encoding="utf-8")
        vendor = STATIC_DIR / "vendor" / "three" / "examples" / "js"
        expected = [
            "CopyShader.js", "LuminosityHighPassShader.js", "Pass.js",
            "EffectComposer.js", "RenderPass.js", "ShaderPass.js", "UnrealBloomPass.js",
        ]
        for filename in expected:
            self.assertIn(filename, index)
        self.assertLess(index.index("RenderPass.js"), index.index("UnrealBloomPass.js"))
        self.assertLess(index.index("UnrealBloomPass.js"), index.index("post-processing.js"))
        self.assertTrue((vendor / "postprocessing" / "EffectComposer.js").is_file())
        self.assertTrue((vendor / "postprocessing" / "UnrealBloomPass.js").is_file())
        self.assertIn("new THREE.EffectComposer(renderer)", post)
        self.assertIn("new THREE.RenderPass(scene, camera)", post)
        self.assertIn("new THREE.UnrealBloomPass", post)
        self.assertIn("bloomPass.threshold = 0.88", post)
        self.assertIn("bloomPass.strength = 0.72", post)
        self.assertIn("bloomPass.radius = 0.30", post)

    def test_visual_phase_b_glow_is_selective_resizable_and_disposable(self):
        vertex = (STATIC_DIR / "js" / "core" / "shaders" / "particle-vertex.js").read_text(encoding="utf-8")
        glow = (STATIC_DIR / "js" / "core" / "volumetric-glow.js").read_text(encoding="utf-8")
        runtime = (STATIC_DIR / "js" / "core" / "shader-core-runtime.js").read_text(encoding="utf-8")
        post = (STATIC_DIR / "js" / "core" / "post-processing.js").read_text(encoding="utf-8")

        self.assertIn("vBloomWeight", vertex)
        self.assertIn("highEnergy", vertex)
        self.assertIn("nucleus", vertex)
        self.assertIn("uTransitionPulse", vertex + glow)
        self.assertIn("uToolAccent", vertex + glow)
        self.assertIn("uAudioLevel", vertex + glow)
        self.assertIn("const layers = [", glow)
        self.assertIn("postProcessing.setSize", runtime)
        self.assertIn("composer.setPixelRatio(pixelRatio)", post)
        self.assertIn("bloomPass.dispose()", post)
        self.assertIn("composer.dispose()", post)
        self.assertIn("CORE_BLOOM_FALLBACK", runtime)
        self.assertIn("renderer.render(scene, camera)", runtime)

    def test_visual_phase_c_profiles_drive_motion_without_direct_jumps(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        transitions = (STATIC_DIR / "js" / "core" / "state-transitions.js").read_text(encoding="utf-8")
        runtime = (STATIC_DIR / "js" / "core" / "shader-core-runtime.js").read_text(encoding="utf-8")
        vertex = (STATIC_DIR / "js" / "core" / "shaders" / "particle-vertex.js").read_text(encoding="utf-8")

        self.assertLess(index.index("state-transitions.js"), index.index("shader-core-runtime.js"))
        for state in ("idle", "connecting", "listening", "thinking", "speaking", "error"):
            self.assertIn(f"{state}: Object.freeze", transitions)
        for value in ("rotationSpeed", "noiseAmount", "particleRadius", "attraction", "bloomStrength", "audioResponse", "particleSize", "auraDensity"):
            self.assertIn(value, transitions)
        self.assertIn("1 - Math.exp", transitions)
        self.assertIn("Math.max(0.4, Math.min(1.2", transitions)
        self.assertIn("transitions.update", runtime)
        self.assertIn("postProcessing.setBloomStrength", runtime)
        self.assertIn("uErrorBurst", vertex)
        self.assertIn("returnFlight", vertex)
        self.assertIn("uToolAccent", vertex)

    def test_surface_resonance_replaces_audio_ring_with_particle_only_motion(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        material = (STATIC_DIR / "js" / "core" / "core-materials.js").read_text(encoding="utf-8")
        vertex = (STATIC_DIR / "js" / "core" / "shaders" / "particle-vertex.js").read_text(encoding="utf-8")
        fragment = (STATIC_DIR / "js" / "core" / "shaders" / "particle-fragment.js").read_text(encoding="utf-8")
        runtime = (STATIC_DIR / "js" / "core" / "shader-core-runtime.js").read_text(encoding="utf-8")

        self.assertNotIn("audio-ring", index)
        self.assertFalse((STATIC_DIR / "js" / "core" / "audio-ring.js").exists())
        for uniform in ("uResonanceMode", "uResonanceLevel", "uResonancePhase"):
            self.assertIn(uniform, material)
            self.assertIn(uniform, vertex)
        self.assertIn("intakeFocus", vertex)
        self.assertIn("intakePull", vertex)
        self.assertIn("emissionFront", vertex)
        self.assertIn("emissionPush", vertex)
        self.assertIn("vResonance", fragment)
        self.assertIn("currentAudio > 0.035", runtime)
        self.assertIn('activeState === "listening" ? audioLevels.input || 0', runtime)
        self.assertIn('activeState === "speaking" ? audioLevels.output || 0', runtime)
        self.assertIn("uniforms.uResonanceLevel.value = 0", runtime)

    def test_visual_phase_e_spatial_background_is_dim_responsive_and_static_safe(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        background = (STATIC_DIR / "js" / "core" / "spatial-background.js").read_text(encoding="utf-8")
        vertex = (STATIC_DIR / "js" / "core" / "shaders" / "background-vertex.js").read_text(encoding="utf-8")
        fragment = (STATIC_DIR / "js" / "core" / "shaders" / "background-fragment.js").read_text(encoding="utf-8")
        runtime = (STATIC_DIR / "js" / "core" / "shader-core-runtime.js").read_text(encoding="utf-8")
        style = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

        expected_order = ["background-vertex.js", "background-fragment.js", "spatial-background.js", "shader-core-runtime.js"]
        self.assertEqual(sorted(expected_order, key=index.index), expected_order)
        self.assertNotIn("new THREE.Points", background)
        self.assertNotIn("geometry.setDrawRange", background)
        self.assertNotIn("starSeed", background)
        self.assertIn("uParallax", vertex + background)
        self.assertIn("uStateEnergy", vertex + background)
        self.assertIn("softness * vAlpha * 0.24", fragment)
        self.assertIn("spatialBackground.setCompact(width <= 680)", runtime)
        self.assertIn("reducedMotion.matches ? 0 : elapsedSeconds", runtime)
        self.assertIn("spatialBackground.dispose()", runtime)
        self.assertIn("repeating-conic-gradient", style)
        self.assertIn("@keyframes spatial-noise-drift", style)
        self.assertIn("animation: none", style)

    def test_phase_eight_audio_analysis_is_split_and_cleanup_safe(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        script = (STATIC_DIR / "script.js").read_text(encoding="utf-8")
        audio = (
            STATIC_DIR / "js" / "audio" / "audio-reactive.js"
        ).read_text(encoding="utf-8")

        self.assertIn("/static/js/audio/audio-reactive.js", index)
        self.assertLess(
            index.index("/static/js/audio/audio-reactive.js"),
            index.index("/static/script.js"),
        )
        self.assertIn("attachInput(currentLocalStream)", script)
        self.assertIn("attachOutput(event.streams[0])", script)
        self.assertIn("window.JarvisUI.audioReactive.reset()", script)
        self.assertIn("analyser.fftSize = 256", audio)
        self.assertIn("new Uint8Array(analyser.fftSize)", audio)
        self.assertIn("getByteTimeDomainData", audio)
        self.assertIn("source.connect(analyser)", audio)
        self.assertNotIn("audioContext.destination", audio)
        self.assertIn("contextToClose.close()", audio)

    def test_phase_eight_core_uses_state_specific_bounded_audio_level(self):
        core = (
            STATIC_DIR / "js" / "core" / "shader-core-runtime.js"
        ).read_text(encoding="utf-8")

        self.assertIn('activeState === "listening"', core)
        self.assertIn('activeState === "speaking"', core)
        self.assertIn('activeState === "listening" ? audioLevels.input || 0', core)
        self.assertIn('activeState === "speaking" ? audioLevels.output || 0', core)
        self.assertIn("uniforms.uAudioLevel.value", core)

    def test_phase_seven_adapts_fps_and_dpr_without_rebuilding_scene(self):
        core = (
            STATIC_DIR / "js" / "core" / "shader-core-runtime.js"
        ).read_text(encoding="utf-8")

        self.assertIn("const activeFrameDurationMs = 1000 / 30", core)
        self.assertIn("const idleFrameDurationMs = 1000 / 20", core)
        self.assertIn("const qualityDprCaps = Object.freeze([1.5, 2.0, 2.5])", core)
        self.assertIn("const qualitySampleSize = 90", core)
        self.assertIn("const qualityChangeCooldownMs = 15000", core)
        self.assertIn("function sampleQuality(frameDuration, now)", core)
        self.assertIn("average > 39 && qualityLevel > 0", core)
        self.assertIn("average < 28 && qualityLevel < qualityDprCaps.length - 1", core)
        self.assertIn("updateRendererDensity()", core)

    def test_existing_script_publishes_voice_status_to_ui_state(self):
        script = (STATIC_DIR / "script.js").read_text(encoding="utf-8")

        self.assertIn("window.JarvisUI.dom.elements", script)
        self.assertIn("window.JarvisUI.state.update({", script)
        self.assertIn("connectionStatus: status", script)
        self.assertIn("statusMessage: message", script)

    def test_system_log_uses_text_content_and_bounds_entries(self):
        system_log = (
            STATIC_DIR / "js" / "ui" / "system-log.js"
        ).read_text(encoding="utf-8")

        self.assertIn("const maximumEntries = 100", system_log)
        self.assertIn("content.textContent = classification.content", system_log)
        self.assertNotIn("innerHTML", system_log)

    def test_system_log_can_clear_only_rendered_entries(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        dom = (STATIC_DIR / "js" / "dom.js").read_text(encoding="utf-8")
        system_log = (
            STATIC_DIR / "js" / "ui" / "system-log.js"
        ).read_text(encoding="utf-8")

        self.assertIn('id="system-log-clear-button"', index)
        self.assertIn('aria-label="ログ表示をクリア"', index)
        self.assertIn('title="ログ表示をクリア"', index)
        self.assertIn('byId("system-log-clear-button")', dom)
        self.assertIn("logContainer.replaceChildren()", system_log)
        self.assertIn('clearButton.addEventListener("click", clear)', system_log)
        self.assertIn("clear: clear", system_log)

    def test_phase_eleven_integrates_tool_error_and_latency_surfaces(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        dom = (STATIC_DIR / "js" / "dom.js").read_text(encoding="utf-8")
        integration = (
            STATIC_DIR / "js" / "ui" / "integration-status.js"
        ).read_text(encoding="utf-8")
        status = (
            STATIC_DIR / "js" / "ui" / "status-bar.js"
        ).read_text(encoding="utf-8")
        system_log = (
            STATIC_DIR / "js" / "ui" / "system-log.js"
        ).read_text(encoding="utf-8")

        self.assertIn('id="core-tool-status"', index)
        self.assertIn('id="ui-notification"', index)
        self.assertIn('data-status="latency"', index)
        self.assertIn("/static/js/ui/integration-status.js", index)
        self.assertIn('byId("core-tool-status")', dom)
        self.assertIn('byId("ui-notification")', dom)
        self.assertIn("state.activeTool", integration)
        self.assertIn('state.connectionStatus === "error"', integration)
        self.assertIn('notification.setAttribute("role", isError ? "alert"', integration)
        self.assertIn("Number.isFinite(state.latencyMs)", status)
        self.assertIn("TOOL_START", system_log)
        self.assertIn("TOOL_END", system_log)

    def test_phase_eleven_bounds_chat_dom_and_exposes_busy_state(self):
        conversation = (
            STATIC_DIR / "js" / "ui" / "conversation-view.js"
        ).read_text(encoding="utf-8")

        self.assertIn("const maximumRenderedMessages = 200", conversation)
        self.assertIn("while (chatArea.children.length > maximumRenderedMessages)", conversation)
        self.assertIn("messageElementsById.delete(messageId)", conversation)
        self.assertIn('chatArea.setAttribute("aria-busy"', conversation)
        self.assertIn("pendingMessages.size > 0", conversation)

    def test_phase_eleven_manual_verification_document_covers_final_system(self):
        manual = (
            BASE_DIR / "docs" / "ui-manual-verification.md"
        ).read_text(encoding="utf-8")

        for section in (
            "Text and voice Conversation",
            "State, Tool, error, and log integration",
            "Core and Audio Reactive",
            "Accessibility",
            "Long-running operation",
            "Hardware-dependent acceptance",
        ):
            self.assertIn(section, manual)

    def test_visual_phase_f_polishes_panels_controls_and_tool_status_accessibly(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        style = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
        system_log = (STATIC_DIR / "js" / "ui" / "system-log.js").read_text(encoding="utf-8")
        conversation = (STATIC_DIR / "js" / "ui" / "conversation-view.js").read_text(encoding="utf-8")
        integration = (STATIC_DIR / "js" / "ui" / "integration-status.js").read_text(encoding="utf-8")

        for control_id in ("voice-connect-button", "voice-disconnect-button", "voice-reconnect-button"):
            self.assertIn(f'id="{control_id}"', index)
        self.assertIn('aria-label="音声接続"', index)
        self.assertIn('aria-label="音声を切断"', index)
        self.assertIn('aria-label="音声を再接続"', index)
        self.assertIn('class="visually-hidden">音声接続</span>', index)
        self.assertIn('class="tool-progress"', index)

        self.assertIn("function classify(message, level)", system_log)
        self.assertIn('label: "TOOL"', system_log)
        self.assertIn('label: "ERROR"', system_log)
        self.assertIn("entry.append(timestamp, type, content)", system_log)
        self.assertIn('entry.className = "system-log-entry log-entry-new"', system_log)
        self.assertIn("grid-template-columns: 58px 38px minmax(0, 1fr)", style)
        self.assertIn("nth-last-child", style)
        self.assertIn("@keyframes log-entry-arrival", style)

        self.assertIn('headerElement.className = "message-head"', conversation)
        self.assertIn('label.textContent = isUser ? "YOU" : "JARVIS"', conversation)
        self.assertIn("message-pending.ai-message .message-content::after", style)
        self.assertIn("max-width: 58ch", style)
        self.assertIn("position: sticky", style)

        self.assertIn("const toolLabels = Object.freeze", integration)
        self.assertIn('container.classList.add("is-completing")', integration)
        self.assertIn("}, 320)", integration)
        self.assertIn("tool-progress-scan", style)
        self.assertIn("tool-energy-flow", style)
        self.assertIn("button:active:not(:disabled)", style)
        self.assertIn("button:focus-visible", style)

    def test_core_is_full_viewport_scene_beneath_quiet_ui_overlays(self):
        style = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn(".app-shell {\n    position: relative;\n    isolation: isolate;\n    display: block;", style)
        self.assertIn(".workspace {\n    position: absolute;\n    z-index: 1;\n    inset: 0 0 28px;", style)
        self.assertIn(".core-area {\n    position: absolute;\n    z-index: 0;\n    inset: 0;", style)
        self.assertIn(".app-header {\n    position: absolute;\n    z-index: 10;", style)
        self.assertIn(".system-panel {\n    position: absolute;\n    z-index: 5;", style)
        self.assertIn(".conversation-panel {\n    position: absolute;\n    z-index: 5;", style)
        self.assertIn("background: linear-gradient(270deg", style)
        self.assertIn("@media (max-height: 520px) and (max-width: 680px)", style)

    def test_visual_phase_g_integrates_one_shot_cinematic_polish_and_cleanup(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        style = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
        runtime = (STATIC_DIR / "js" / "core" / "shader-core-runtime.js").read_text(encoding="utf-8")
        material = (STATIC_DIR / "js" / "core" / "core-materials.js").read_text(encoding="utf-8")
        vertex = (STATIC_DIR / "js" / "core" / "shaders" / "particle-vertex.js").read_text(encoding="utf-8")
        fragment = (STATIC_DIR / "js" / "core" / "shaders" / "particle-fragment.js").read_text(encoding="utf-8")
        conversation = (STATIC_DIR / "js" / "ui" / "conversation-view.js").read_text(encoding="utf-8")

        self.assertIn("1.44-no-background-points", index)
        self.assertIn("const introDurationMs = 1650", runtime)
        self.assertIn('document.body.dataset.coreIntro = "true"', runtime)
        self.assertIn('document.body.removeAttribute("data-core-intro")', runtime)
        self.assertIn("uIntroProgress", material)
        self.assertIn("uIntroProgress", vertex)
        self.assertIn("vIntroOpacity", fragment)
        self.assertIn('reducedMotion.addEventListener("change", handleReducedMotionChange)', runtime)
        self.assertIn('reducedMotion.removeEventListener("change", handleReducedMotionChange)', runtime)
        self.assertIn('document.removeEventListener("visibilitychange", handleVisibilityChange)', runtime)
        self.assertIn('canvas.removeEventListener("webglcontextlost", handleContextLost)', runtime)

        self.assertIn('element.classList.add("message-arrival")', conversation)
        self.assertIn("if (!renderingHistory)", conversation)
        self.assertIn("@keyframes cinematic-interface-reveal", style)
        self.assertIn("@keyframes message-arrival", style)
        self.assertIn("@media (max-width: 974px)", style)
        self.assertIn("@media (max-width: 480px)", style)

        for document_name in (
            "ui-architecture.md",
            "ui-state-machine.md",
            "ui-manual-verification.md",
            "third-party-notices.md",
            "visual-design-system.md",
            "shader-architecture.md",
        ):
            self.assertTrue((BASE_DIR / "docs" / document_name).exists())

    def test_neural_core_uses_high_density_derivative_antialiasing(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        field = (STATIC_DIR / "js" / "core" / "particle-field.js").read_text(encoding="utf-8")
        material = (STATIC_DIR / "js" / "core" / "core-materials.js").read_text(encoding="utf-8")
        fragment = (STATIC_DIR / "js" / "core" / "shaders" / "particle-fragment.js").read_text(encoding="utf-8")
        runtime = (STATIC_DIR / "js" / "core" / "shader-core-runtime.js").read_text(encoding="utf-8")

        self.assertIn("1.33-core-ultra-detail", index)
        self.assertIn("surface: 2200, volume: 1600, flow: 650, cluster: 630", field)
        self.assertIn('precision: "highp"', material)
        self.assertIn("extensions: { derivatives: true }", material)
        self.assertIn("fwidth(radius)", fragment)
        self.assertIn("float microCore", fragment)
        self.assertIn("float softHalo", fragment)
        self.assertIn("float haloFeather", fragment)
        self.assertIn("smoothstep(0.34, 0.92, radius)", fragment)
        glow = (STATIC_DIR / "js" / "core" / "volumetric-glow.js").read_text(encoding="utf-8")
        self.assertIn("pow(max(0.0, 1.0 - radius), 2.35)", glow)
        self.assertIn("{ scale: 0.72, z: 0.12, opacity: 0.34 }", glow)
        self.assertIn("{ scale: 1.72, z: -0.30, opacity: 0.075 }", glow)
        self.assertIn("[1.5, 2.0, 2.5]", runtime)
        self.assertNotIn("renderer.outputEncoding = THREE.sRGBEncoding", runtime)

    def test_spatial_background_adds_subtle_cosmic_depth_without_assets(self):
        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        style = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
        background_vertex = (STATIC_DIR / "js" / "core" / "shaders" / "background-vertex.js").read_text(encoding="utf-8")
        background_fragment = (STATIC_DIR / "js" / "core" / "shaders" / "background-fragment.js").read_text(encoding="utf-8")
        spatial = (STATIC_DIR / "js" / "core" / "spatial-background.js").read_text(encoding="utf-8")
        runtime = (STATIC_DIR / "js" / "core" / "shader-core-runtime.js").read_text(encoding="utf-8")

        self.assertIn("1.44-no-background-points", index)
        self.assertIn(".app-shell::before", style)
        self.assertIn(".app-shell::after", style)
        self.assertIn("isolation: isolate", style)
        self.assertIn("@keyframes cosmic-atmosphere-drift", style)
        self.assertIn("filter: blur(18px)", style)
        self.assertIn("48s ease-in-out infinite alternate", style)
        self.assertIn(".app-shell::before {\n    display: none;", style)
        self.assertIn("linear-gradient(126deg", style)
        self.assertIn(".workspace {\n    position: absolute;\n    z-index: 1;", style)
        self.assertIn("background-color: #020711", style)
        self.assertNotIn("rgba(190, 239, 255, 0.32)", style)
        self.assertNotIn("background-size: 181px 163px", style)
        self.assertIn("varying float vDepth", background_vertex)
        self.assertIn("uniform vec3 uColorAccent", background_fragment)
        self.assertIn("float accentMix", background_fragment)
        self.assertIn("uColorAccent", spatial)
        self.assertIn("spatialBackground.uniforms.uColorAccent", runtime)
        self.assertIn("const cosmicFragmentShader", spatial)
        self.assertIn("new THREE.PlaneGeometry(32, 18)", spatial)
        self.assertIn("cosmicBackdrop.position.z = -8.5", spatial)
        self.assertIn("group.add(cosmicBackdrop)", spatial)
        self.assertIn("cosmicGeometry.dispose()", spatial)
        self.assertNotIn("starSeed", spatial)
        self.assertNotIn("new THREE.Points", spatial)
        self.assertIn("vec3(0.008, 0.038, 0.076)", spatial)


if __name__ == "__main__":
    unittest.main()
