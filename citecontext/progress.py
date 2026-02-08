from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any, TypeVar

T = TypeVar("T")


def tqdm(iterable: Iterable[T] | None = None, **kwargs: Any) -> Iterator[T] | Any:
    """Optional tqdm wrapper.

    - If `tqdm` is installed: returns a real tqdm iterator/progress bar.
    - Otherwise: returns the iterable unchanged (or a no-op context-like object).
    """
    try:
        from tqdm import tqdm as _tqdm  # type: ignore[import-untyped]
    except Exception:  # noqa: BLE001
        if iterable is None:
            return _NoOpTqdm(**kwargs)
        return iter(iterable)
    return _tqdm(iterable, **kwargs)


class _NoOpTqdm:
    def __init__(self, *args: Any, **kwargs: Any):
        self.total = kwargs.get("total")

    def update(self, _n: int = 1) -> None:
        return None

    def close(self) -> None:
        return None

    def __enter__(self) -> "_NoOpTqdm":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()
        return None

