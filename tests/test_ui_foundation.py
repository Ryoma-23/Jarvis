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
        self.assertIn('[data-message-source="voice"]::after', style)
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
        core = (
            STATIC_DIR / "js" / "core" / "jarvis-core.js"
        ).read_text(encoding="utf-8")
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
        self.assertIn("const THREE = global.THREE;", core)
        self.assertIn("CORE_WEBGL_DEPENDENCY_UNAVAILABLE", core)
        self.assertIn("new THREE.WebGLRenderer", core)
        self.assertIn("new THREE.Points(", core)
        self.assertIn("new THREE.SphereGeometry", core)
        self.assertIn('stage.dataset.renderer = "webgl"', core)
        self.assertIn('stage.dataset.renderer = "fallback"', core)
        self.assertIn('.core-stage[data-renderer="webgl"] .core-canvas', style)
        self.assertGreater(three_module.stat().st_size, 300_000)
        self.assertIn("MIT License", three_license)
        self.assertIn("Copyright", three_license)

    def test_phase_five_core_limits_background_rendering_and_gpu_cost(self):
        core = (
            STATIC_DIR / "js" / "core" / "jarvis-core.js"
        ).read_text(encoding="utf-8")

        self.assertIn("const particleCount = 1000", core)
        self.assertIn("const targetFrameDurationMs = 1000 / 30", core)
        self.assertIn('powerPreference: "low-power"', core)
        self.assertIn("Math.min(window.devicePixelRatio || 1, 1.5)", core)
        self.assertIn('document.addEventListener("visibilitychange"', core)
        self.assertIn("document.hidden", core)
        self.assertIn("reducedMotion.matches", core)
        self.assertIn("renderer.dispose()", core)

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
        self.assertIn("content.textContent = String(message)", system_log)
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


if __name__ == "__main__":
    unittest.main()
