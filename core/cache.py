"""Small deterministic caches for interactive PixelatorPlus work.

Blender property updates run on Blender's main thread.  This module therefore
uses a bounded, single-threaded LRU cache deliberately: it never starts a
worker thread and cannot race Blender's data API.  Apply and Export do not use
this cache, so their NumPy results remain authoritative and independent of
preview lifetime.
"""

from collections import OrderedDict
import hashlib
import json

import numpy as np


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return {"shape": tuple(value.shape), "dtype": str(value.dtype), "sha1": array_digest(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def array_digest(array):
    """Return a stable digest for a small or capped preview array."""
    arr = np.ascontiguousarray(np.asarray(array))
    digest = hashlib.sha1()
    digest.update(str(arr.dtype).encode("ascii"))
    digest.update(repr(arr.shape).encode("ascii"))
    digest.update(arr.tobytes())
    return digest.hexdigest()


def preview_key(source, params, images=None, mode="FINAL"):
    """Build a content key for a preview result."""
    payload = {
        "source": {"shape": tuple(np.asarray(source).shape), "sha1": array_digest(source)},
        "params": _jsonable(params),
        "images": {key: _jsonable(value) for key, value in sorted((images or {}).items())},
        "mode": str(mode),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


class PreviewCache:
    """Bounded result cache storing copies of NumPy preview results."""

    def __init__(self, max_items=3, max_bytes=64 * 1024 * 1024):
        self.max_items = max(1, int(max_items))
        self.max_bytes = max(1, int(max_bytes))
        self._items = OrderedDict()
        self._bytes = 0

    def clear(self):
        self._items.clear()
        self._bytes = 0

    def _size(self, result):
        return sum(value.nbytes for value in result.values() if isinstance(value, np.ndarray))

    def get(self, key):
        value = self._items.get(key)
        if value is None:
            return None
        self._items.move_to_end(key)
        return {
            name: (value.copy() if isinstance(value, np.ndarray) else value)
            for name, value in value.items()
        }

    def put(self, key, result):
        arrays = {
            name: (value.copy() if isinstance(value, np.ndarray) else value)
            for name, value in result.items()
        }
        size = self._size(arrays)
        if size > self.max_bytes:
            return
        old = self._items.pop(key, None)
        if old is not None:
            self._bytes -= self._size(old)
        self._items[key] = arrays
        self._bytes += size
        while len(self._items) > self.max_items or self._bytes > self.max_bytes:
            _, removed = self._items.popitem(last=False)
            self._bytes -= self._size(removed)
