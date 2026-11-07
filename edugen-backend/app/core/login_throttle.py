"""Chặn dò mật khẩu: đếm lần đăng nhập sai theo khóa (IP + email) trong cửa sổ trượt.

Lưu trong bộ nhớ tiến trình: đủ cho một worker. Chạy nhiều worker/instance thì chuyển sang Redis.
"""

import threading
import time
from collections import deque

from app.core.config import settings

_MAX_KEYS = 10_000  # quá ngưỡng thì dọn các khóa đã hết hạn


class LoginThrottle:
    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _window() -> float:
        return settings.login_window_minutes * 60

    def _prune(self, key: str, now: float) -> deque[float] | None:
        times = self._failures.get(key)
        if times is None:
            return None
        while times and times[0] <= now - self._window():
            times.popleft()
        if not times:
            del self._failures[key]
            return None
        return times

    def retry_after(self, key: str) -> int:
        """Số giây phải chờ; 0 nghĩa là được thử đăng nhập."""
        now = time.monotonic()
        with self._lock:
            times = self._prune(key, now)
            if times is None or len(times) < settings.login_max_failures:
                return 0
            return max(1, int(times[0] + self._window() - now) + 1)

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._failures) >= _MAX_KEYS:
                for k in list(self._failures):
                    self._prune(k, now)
            self._failures.setdefault(key, deque()).append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._failures.clear()
            else:
                self._failures.pop(key, None)


login_throttle = LoginThrottle()
