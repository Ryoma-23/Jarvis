"""Reject isolated wake-model score spikes without changing score thresholds."""
import math


class ScoreConfirmation:
    def __init__(self, threshold, required_frames):
        self.threshold = threshold
        self.required_frames = required_frames
        self.reset()

    def reset(self):
        self.consecutive_frames = 0

    def update(self, score):
        if math.isfinite(score) and score >= self.threshold:
            self.consecutive_frames += 1
        else:
            self.reset()
        return self.consecutive_frames >= self.required_frames
