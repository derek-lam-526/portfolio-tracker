import time
import threading

class Timer:
    def __init__(self, description, enabled=True):
        self.description = description
        self.enabled = enabled

    def __enter__(self):
        if self.enabled:
            self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        if self.enabled:
            self.end = time.perf_counter()
            self.duration = self.end - self.start
            print(f"⏱️ {self.description} took {self.duration:.2f}s")

class TimingCollector:
    """Thread-safe collector for aggregating timings across parallel processes."""
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.timings = {}
        self.lock = threading.Lock()

    def record(self, category, duration):
        if not self.enabled:
            return
        with self.lock:
            if category not in self.timings:
                self.timings[category] = []
            self.timings[category].append(duration)

    def print_summary(self):
        if not self.enabled or not self.timings:
            return
        
        print("\n--- Granular Data Fetching Summary ---")
        for category, times in self.timings.items():
            total = sum(times)
            count = len(times)
            avg = total / count if count > 0 else 0
            # Total represents the wall-clock time if serial, but here it's aggregate across threads
            print(f"📊 {category}: {total:.2f}s aggregate ({count} symbols, avg {avg:.2f}s/symbol)")
        print("-" * 38)
