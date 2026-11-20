(function(global) {
    "use strict";
    const list = document.getElementById("diagnostic-turns"), rows = new Map();
    let onLabel = null, active = false;
    const scenarios = {quiet: "静か", video_only: "動画だけ", video_and_me: "動画＋本人", interrupt: "割り込み"};
    const decisions = {owner_candidate: "本人候補", other_candidate: "別話者候補", uncertain: "判定保留",
        insufficient: "材料不足", capture_unavailable: "音声取得不可", skipped_busy: "処理中のため未計測"};
    const reasons = {insufficient_audio: "有音区間が不足", clipped_audio: "音割れ", missing_or_overlong_segment: "区間欠落または長すぎる音声"};
    global.JarvisDiagnosticTurns = Object.freeze({
        reset(callback) { rows.clear(); list.replaceChildren(); onLabel = callback; },
        setActive(value) { active = value; for (const row of rows.values()) row.select.disabled = !value; },
        update(event) {
            const key = JSON.stringify([event.session, event.item]);
            if (event.kind === "speech_start" && event.item && !rows.has(key)) {
                const li = document.createElement("li"), info = document.createElement("span"), select = document.createElement("select");
                const title = `発話 ${rows.size + 1}／${(event.ms / 1000).toFixed(1)}秒／試行 ${event.trial}／${scenarios[event.scenario]}`;
                const heading = document.createElement("div"); heading.textContent = title; li.appendChild(heading);
                info.textContent = "照合結果待ち（照合オフ時は未計測）"; li.appendChild(info);
                for (const [value, name] of [["unknown", "不明・未指定"], ["owner", "本人"], ["video", "動画"], ["mixed", "両方が重なった"]]) {
                    const option = document.createElement("option"); option.value = value; option.textContent = name; select.appendChild(option);
                }
                select.value = "unknown"; select.disabled = !active; select.setAttribute("aria-label", title + "の話者");
                select.addEventListener("change", () => { if (active) onLabel?.(event.session, event.item, select.value); });
                li.appendChild(select); list.appendChild(li); rows.set(key, {select, info});
            }
            if (event.kind === "speaker_result" && rows.has(key)) {
                const details = [decisions[event.value] || "照合できませんでした", `類似度 ${event.score ?? "—"}`];
                if (event.reason) details.push(reasons[event.reason] || "判定できませんでした");
                if (event.energy_s != null) details.push(`有音 ${event.energy_s}秒`);
                rows.get(key).info.textContent = details.join("／");
            }
        }
    });
})(window);
