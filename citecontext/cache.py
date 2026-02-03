from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any


def now_ts() -> float:
    return time.time()


def safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


@dataclass(frozen=True)
class CacheConfig:
    cache_dir: str
    ttl_hours: float | None


class JsonDiskCache:
    def __init__(self, cfg: CacheConfig):
        self.cfg = cfg
        safe_mkdir(cfg.cache_dir)

    def _path_for_key(self, key: str) -> str:
        return os.path.join(self.cfg.cache_dir, f"{key}.json")

    def get(self, key: str) -> Any | None:
        path = self._path_for_key(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:  # noqa: BLE001
            return None

        fetched_at = payload.get("fetched_at")
        if self.cfg.ttl_hours is not None and fetched_at is not None:
            age_sec = now_ts() - float(fetched_at)
            if age_sec > self.cfg.ttl_hours * 3600.0:
                return None
        return payload.get("response")

    def set(self, key: str, response: Any) -> None:
        path = self._path_for_key(key)
        tmp = f"{path}.tmp"
        payload = {"fetched_at": now_ts(), "response": response}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)

