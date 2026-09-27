"""Portable ``.cube`` 3D-LUT parsing and sampling.

The implementation follows the public Iridas/Adobe-style text format: the
red coordinate changes fastest in the data records, followed by green and
blue.  Domain ranges are honored, unlike the legacy tiled-image path.
"""

import os
from collections import OrderedDict

import numpy as np


# Parsed LUT resources are copied on return, so entries can safely be shared
# between preview/apply callers.  Keep the retained source data bounded across
# a long Blender session; oversized LUTs remain usable but are not cached.
_CUBE_CACHE = OrderedDict()
_CUBE_CACHE_MAX_ENTRIES = 8
_CUBE_CACHE_MAX_BYTES = 32 * 1024 * 1024

# Trilinear interpolation works a fixed number of pixels at a time.  The
# output image is necessarily full-sized, but coordinate and neighbor-color
# intermediates stay bounded independently of image dimensions.
_TRILINEAR_BATCH_POINTS = 65536


class CubeLUT:
    """Parsed 3D LUT with data indexed as ``[red, green, blue, channel]``."""

    def __init__(self, size, data, domain_min=(0.0, 0.0, 0.0), domain_max=(1.0, 1.0, 1.0), title=""):
        size = int(size)
        data = np.asarray(data, dtype=np.float32)
        if size < 2 or data.shape != (size, size, size, 3):
            raise ValueError("CubeLUT data must have shape (size, size, size, 3)")
        self.size = size
        self.data = np.clip(data, 0.0, 1.0).copy()
        self.domain_min = np.asarray(domain_min, dtype=np.float32).reshape(3)
        self.domain_max = np.asarray(domain_max, dtype=np.float32).reshape(3)
        if np.any(self.domain_max <= self.domain_min):
            raise ValueError(".cube DOMAIN_MAX must be greater than DOMAIN_MIN")
        self.title = str(title)

    def copy(self):
        return CubeLUT(
            self.size, self.data, self.domain_min, self.domain_max, self.title
        )

    def sample(self, rgb, interpolation="TRILINEAR"):
        """Sample an RGB image/array using nearest or trilinear interpolation."""
        rgb = np.asarray(rgb, dtype=np.float32)
        if rgb.ndim < 1 or rgb.shape[-1] < 3:
            raise ValueError("CubeLUT sample input must have an RGB channel axis")
        points = rgb[..., :3]
        mode = str(interpolation or "TRILINEAR").upper()
        if mode in ("NEAREST", "POINT"):
            coord = (points - self.domain_min) / (self.domain_max - self.domain_min)
            coord = np.clip(coord, 0.0, 1.0) * np.float32(self.size - 1)
            idx = np.rint(coord).astype(np.int64)
            return self.data[idx[..., 0], idx[..., 1], idx[..., 2]].astype(np.float32)
        if mode not in ("TRILINEAR", "LINEAR"):
            raise ValueError(f"unknown .cube interpolation {interpolation!r}")
        return self._sample_trilinear_batched(rgb)

    def _sample_trilinear_batched(self, rgb):
        """Return float32 trilinear samples without whole-image temporaries."""
        output = np.empty(rgb.shape[:-1] + (3,), dtype=np.float32)
        output_flat = output.reshape(-1, 3)
        count = output_flat.shape[0]
        flat_input = None
        if rgb.flags.c_contiguous:
            flat_input = rgb.reshape(-1, rgb.shape[-1])
        domain_scale = np.float32(1.0) / (self.domain_max - self.domain_min)
        grid_scale = np.float32(self.size - 1)
        one = np.float32(1.0)

        for start in range(0, count, _TRILINEAR_BATCH_POINTS):
            stop = min(start + _TRILINEAR_BATCH_POINTS, count)
            if flat_input is not None:
                chunk = flat_input[start:stop, :3]
            elif rgb.ndim == 1:
                chunk = rgb[np.newaxis, :3]
            else:
                flat_indices = np.arange(start, stop, dtype=np.intp)
                chunk = rgb[np.unravel_index(flat_indices, rgb.shape[:-1])][:, :3]

            coord = (chunk - self.domain_min) * domain_scale
            np.clip(coord, 0.0, 1.0, out=coord)
            coord *= grid_scale
            lo = np.floor(coord).astype(np.intp)
            hi = np.minimum(lo + 1, self.size - 1)
            t = coord - lo.astype(np.float32)
            tx, ty, tz = t[:, 0:1], t[:, 1:2], t[:, 2:3]

            c000 = self.data[lo[:, 0], lo[:, 1], lo[:, 2]]
            c100 = self.data[hi[:, 0], lo[:, 1], lo[:, 2]]
            c010 = self.data[lo[:, 0], hi[:, 1], lo[:, 2]]
            c110 = self.data[hi[:, 0], hi[:, 1], lo[:, 2]]
            c001 = self.data[lo[:, 0], lo[:, 1], hi[:, 2]]
            c101 = self.data[hi[:, 0], lo[:, 1], hi[:, 2]]
            c011 = self.data[lo[:, 0], hi[:, 1], hi[:, 2]]
            c111 = self.data[hi[:, 0], hi[:, 1], hi[:, 2]]
            c00 = c000 * (one - tx) + c100 * tx
            c10 = c010 * (one - tx) + c110 * tx
            c01 = c001 * (one - tx) + c101 * tx
            c11 = c011 * (one - tx) + c111 * tx
            c0 = c00 * (one - ty) + c10 * ty
            c1 = c01 * (one - ty) + c11 * ty
            np.clip(c0 * (one - tz) + c1 * tz, 0.0, 1.0, out=output_flat[start:stop])

        return output


def parse_cube(text):
    """Parse a ``.cube`` string into a :class:`CubeLUT`."""
    size = None
    domain_min = np.zeros(3, dtype=np.float32)
    domain_max = np.ones(3, dtype=np.float32)
    title = ""
    records = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("TITLE"):
            title = line[5:].strip().strip('"')
            continue
        fields = line.split()
        key = fields[0].upper()
        if key == "LUT_3D_SIZE":
            if len(fields) != 2:
                raise ValueError("invalid LUT_3D_SIZE in .cube file")
            size = int(fields[1])
            if size < 2 or size > 256:
                raise ValueError(".cube LUT_3D_SIZE must be between 2 and 256")
            continue
        if key in ("DOMAIN_MIN", "DOMAIN_MAX"):
            if len(fields) != 4:
                raise ValueError(f"invalid {key} in .cube file")
            values = np.asarray([float(value) for value in fields[1:]], dtype=np.float32)
            if key == "DOMAIN_MIN":
                domain_min = values
            else:
                domain_max = values
            continue
        if key == "LUT_1D_SIZE":
            raise ValueError("1D-only .cube LUTs are not supported; use a 3D LUT")
        if len(fields) != 3:
            raise ValueError(f"invalid .cube data row: {line!r}")
        records.append([float(value) for value in fields])
    if size is None:
        raise ValueError(".cube file is missing LUT_3D_SIZE")
    expected = size ** 3
    if len(records) != expected:
        raise ValueError(f".cube LUT_3D_SIZE {size} requires {expected} data rows, got {len(records)}")
    raw = np.asarray(records, dtype=np.float32).reshape(size, size, size, 3)
    # File order is blue-major, green-middle, red-minor; expose RGB indexing.
    data = raw.transpose(2, 1, 0, 3)
    return CubeLUT(size, data, domain_min, domain_max, title)


def file_stamp(path):
    """Return ``(absolute path, mtime_ns, size)`` identifying a file's content.

    Used as the parsed-LUT cache key and by preview caching, so editing a
    `.cube` file in place is noticed.  Returns ``None`` for a missing file.
    """
    path = os.path.abspath(os.fspath(path))
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (path, getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)), stat.st_size)


def load_cube(path):
    """Read and parse a user-selected `.cube` path."""
    key = file_stamp(path)
    if key is None:
        raise FileNotFoundError(f"no such .cube file: {os.fspath(path)}")
    path = key[0]
    cached = _CUBE_CACHE.get(key)
    if cached is not None:
        _CUBE_CACHE.move_to_end(key)
        return cached.copy()
    for old_key in tuple(_CUBE_CACHE):
        if old_key[0] == path and old_key != key:
            del _CUBE_CACHE[old_key]
    with open(path, "r", encoding="utf-8-sig") as handle:
        lut = parse_cube(handle.read())
    _cache_lut(key, lut)
    return lut.copy() if key in _CUBE_CACHE else lut


def clear_cache():
    """Clear parsed `.cube` resources, primarily for tests and file watchers."""
    _CUBE_CACHE.clear()


def _cache_lut(key, lut):
    """Retain a parsed LUT only while it fits the small LRU data budget."""
    data_bytes = lut.data.nbytes + lut.domain_min.nbytes + lut.domain_max.nbytes
    if data_bytes > _CUBE_CACHE_MAX_BYTES:
        return
    _CUBE_CACHE[key] = lut
    _CUBE_CACHE.move_to_end(key)
    while len(_CUBE_CACHE) > _CUBE_CACHE_MAX_ENTRIES or _cube_cache_bytes() > _CUBE_CACHE_MAX_BYTES:
        _CUBE_CACHE.popitem(last=False)


def _cube_cache_bytes():
    """Return the retained NumPy payload bytes for the parsed-LUT cache."""
    return sum(
        lut.data.nbytes + lut.domain_min.nbytes + lut.domain_max.nbytes
        for lut in _CUBE_CACHE.values()
    )


def cube_from_tiled_lut(lut, size=16, title="PixelatorPlus 4K LUT"):
    """Sample a native 4096x4096 tiled LUT into a compact :class:`CubeLUT`.

    A 16 or 32 lattice is enough for portable interchange and avoids ever
    expanding a compact `.cube` file into a 4K image during preview.
    """
    lut = np.asarray(lut, dtype=np.float32)
    if lut.shape[:2] != (4096, 4096) or lut.shape[2] < 3:
        raise ValueError("tiled LUT must have shape (4096, 4096, 3|4)")
    size = int(size)
    if size < 2 or size > 256:
        raise ValueError("cube export size must be between 2 and 256")
    index = np.rint(np.linspace(0.0, 255.0, size)).astype(np.int32)
    r, g, b = np.meshgrid(index, index, index, indexing="ij")
    py = (b // 16) * 256 + g
    px = (b % 16) * 256 + r
    return CubeLUT(size, lut[py, px, :3], title=title)


def cube_from_palette(palette, size=16, title="PixelatorPlus Palette LUT"):
    """Create a compact nearest-color 3D LUT from a palette."""
    palette = np.asarray(palette, dtype=np.float32)[:, :3]
    if palette.ndim != 2 or palette.shape[0] == 0:
        raise ValueError("palette must contain RGB colors")
    size = int(size)
    if size < 2 or size > 256:
        raise ValueError("cube export size must be between 2 and 256")
    ramp = np.linspace(0.0, 1.0, size, dtype=np.float32)
    r, g, b = np.meshgrid(ramp, ramp, ramp, indexing="ij")
    points = np.stack([r, g, b], axis=-1).reshape(-1, 3)
    output = np.empty_like(points)
    for start in range(0, len(points), 8192):
        chunk = points[start:start + 8192]
        distance = ((chunk[:, None, :] - palette[None, :, :]) ** 2).sum(axis=-1)
        output[start:start + len(chunk)] = palette[np.argmin(distance, axis=1)]
    return CubeLUT(size, output.reshape(size, size, size, 3), title=title)


def export_cube(lut, path, title=None):
    """Write a :class:`CubeLUT` using standard blue-major `.cube` ordering."""
    if not isinstance(lut, CubeLUT):
        raise TypeError("export_cube expects a CubeLUT")
    raw = lut.data.transpose(2, 1, 0, 3).reshape(-1, 3)
    name = str(title if title is not None else lut.title)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f'TITLE "{name.replace(chr(34), chr(39))}"\n')
        handle.write(f"LUT_3D_SIZE {lut.size}\n")
        handle.write("DOMAIN_MIN %.9g %.9g %.9g\n" % tuple(lut.domain_min))
        handle.write("DOMAIN_MAX %.9g %.9g %.9g\n" % tuple(lut.domain_max))
        for row in raw:
            handle.write("%.9g %.9g %.9g\n" % tuple(row))


def sample(rgb, lut, interpolation="TRILINEAR", strength=1.0):
    """Sample a :class:`CubeLUT` and blend with the input by ``strength``."""
    rgb = np.asarray(rgb, dtype=np.float32)
    result = lut.sample(rgb, interpolation)
    amount = float(np.clip(strength, 0.0, 1.0))
    return np.clip(rgb[..., :3] * (1.0 - amount) + result * amount, 0.0, 1.0).astype(np.float32)
