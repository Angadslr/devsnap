from __future__ import annotations

import collections
import threading
from typing import Dict, List, Optional


class RingBuffer:
    def __init__(self, capacity: int = 500) -> None:
        self.capacity = capacity
        self._buffer: collections.deque[str] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()

    def append(self, line: str) -> None:
        with self._lock:
            self._buffer.append(line.rstrip("\r\n"))

    def get_lines(self, count: Optional[int] = None) -> List[str]:
        with self._lock:
            if count is None or count >= len(self._buffer):
                return list(self._buffer)
            return list(self._buffer)[-count:]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


class LogManager:
    _instance: Optional[LogManager] = None
    _global_lock = threading.Lock()

    def __init__(self) -> None:
        self._buffers: Dict[str, RingBuffer] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> LogManager:
        with cls._global_lock:
            if cls._instance is None:
                cls._instance = LogManager()
            return cls._instance

    def get_buffer(self, service: str, capacity: int = 500) -> RingBuffer:
        with self._lock:
            if service not in self._buffers:
                self._buffers[service] = RingBuffer(capacity=capacity)
            return self._buffers[service]

    def log(self, service: str, line: str) -> None:
        buf = self.get_buffer(service)
        buf.append(line)

    def get_logs(self, service: str, lines: int = 50) -> List[str]:
        buf = self.get_buffer(service)
        return buf.get_lines(lines)

    def get_all_services(self) -> List[str]:
        with self._lock:
            return list(self._buffers.keys())
