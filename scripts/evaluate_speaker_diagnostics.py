"""Read-only threshold comparison. Never changes live settings or infers labels."""
import argparse
import json
import math
from collections import Counter
from pathlib import Path


def evaluate(document, thresholds=(.6, .8, .85, .9, .95)):
    if any(not math.isfinite(t) or not -1 <= t <= 1 for t in thresholds):
        raise ValueError("Thresholds must be finite numbers between -1 and 1")
    turns, labels, results = {}, {}, {}
    for event in document["events"]:
        key = (event.get("session", ""), event.get("item", ""))
        if not key[1]:
            continue
        if event["kind"] == "speech_start":
            turns[key] = event
        elif event["kind"] == "speaker_label":
            labels[key] = event.get("speaker_label", "unknown")
        elif event["kind"] == "speaker_result":
            results[key] = event
    rows = []
    for key, turn in turns.items():
        result = results.get(key, {})
        score = result.get("score")
        if score is not None and (not isinstance(score, (int, float)) or not math.isfinite(score) or not -1 <= score <= 1):
            raise ValueError("Invalid similarity score")
        rows.append({"session": key[0], "item": key[1], "scenario": turn.get("scenario"),
                     "label": labels.get(key, "unknown"), "score": score,
                     "profile": result.get("profile"), "reason": result.get("reason") or result.get("value", "not_measured")})
    comparisons = []
    for threshold in thresholds:
        owner = [r for r in rows if r["label"] == "owner" and r["score"] is not None]
        video = [r for r in rows if r["label"] == "video" and r["score"] is not None]
        rejected = sum(r["score"] < threshold for r in owner)
        passed = sum(r["score"] >= threshold for r in video)
        comparisons.append({"threshold": threshold, "owner_scored": len(owner), "owner_rejected": rejected,
                            "owner_reject_rate": rejected / len(owner) if owner else None,
                            "video_scored": len(video), "video_passed": passed,
                            "video_pass_rate": passed / len(video) if video else None})
    return {"id": document.get("id"), "complete": document.get("complete", False),
            "turns": len(rows), "labels": dict(Counter(r["label"] for r in rows)),
            "unscored_by_label": dict(Counter(r["label"] for r in rows if r["score"] is None)),
            "unscored_reasons": dict(Counter(r["reason"] for r in rows if r["score"] is None)),
            "profiles": sorted({r["profile"] for r in rows if r["profile"]}),
            "comparisons": comparisons, "rows": rows,
            "notes": ["Latest explicit label wins; scenario and response marks never imply identity.",
                      "Mixed and unknown labels are excluded from binary threshold comparisons.",
                      "Unscored turns are reported separately, never treated as rejects or successes.",
                      "These are retrospective sample counts, not validated production thresholds."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--thresholds", type=float, nargs="+", default=[.6, .8, .85, .9, .95])
    args = parser.parse_args()
    try:
        # Separate each run to avoid pooling profiles and counting repeated files together.
        reports = [evaluate(json.loads(p.read_text(encoding="utf-8")), args.thresholds) for p in args.files]
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(reports, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
