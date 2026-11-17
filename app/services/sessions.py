"""Group detections into series independently from audio/model/HTTP code."""
class SessionTracker:
    def __init__(self, history, gap_seconds=90, min_count=2, min_duration=0):
        self.history = history
        self.gap_seconds = gap_seconds
        self.min_count = min_count
        self.min_duration = min_duration
        self.start = self.last = self.last_tick = None
        self.count = 0

    def update(self, is_bark, timestamp, tick):
        if self.start is not None and tick - self.last_tick > self.gap_seconds:
            self.finish()
        if is_bark:
            if self.start is None:
                self.start = timestamp
            self.last, self.last_tick = timestamp, tick
            self.count += 1

    def finish(self):
        if self.start is None:
            return
        seconds = max(0, (self.last - self.start).total_seconds())
        if self.count >= self.min_count and seconds >= self.min_duration:
            self.history.bark_session(self.start, self.last, seconds, self.count)
            print(f'[BARK SESSION] {seconds:.1f} seconds, {self.count} detections', flush=True)
        self.start = self.last = self.last_tick = None
        self.count = 0
