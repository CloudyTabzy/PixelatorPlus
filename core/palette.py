"""Palette extraction and editing utilities inspired by Pixel Composer.

These helpers are clean-room, deterministic NumPy implementations.  A
``PaletteAsset`` is a small serializable record rather than a Blender ID block,
so the same palette workflow works in unit tests, Apply, and compositor bake.
The JSON representation is intentionally plain and portable for Blender asset
libraries and version-controlled style recipes.
"""

import json

import numpy as np

from .colorspace import from_space, to_space
from .quantize import _ITERATIONS, _MAX_SAMPLES, kmeans, kmeans_palette


class PaletteAsset:
    """Editable palette record containing RGB colors and lightweight metadata."""

    def __init__(self, colors, name="Untitled Palette", metadata=None):
        colors = np.asarray(colors, dtype=np.float32)
        if colors.ndim != 2 or colors.shape[1] < 3:
            raise ValueError("palette colors must have shape (K, 3)")
        colors = np.clip(colors[:, :3], 0.0, 1.0)
        if colors.shape[0] == 0 or colors.shape[0] > 256:
            raise ValueError("palette must contain between 1 and 256 colors")
        self.colors = colors.copy()
        self.name = str(name)
        self.metadata = dict(metadata or {})

    def as_dict(self):
        return {
            "name": self.name,
            "colors": self.colors.copy(),
            "metadata": dict(self.metadata),
        }

    def copy(self, name=None):
        return PaletteAsset(self.colors, name if name is not None else self.name, self.metadata)

    def to_dict(self):
        """Return a JSON-compatible palette record."""
        return {
            "format": "PixelatorPlus Palette",
            "version": 1,
            "name": self.name,
            "colors": np.rint(self.colors * 255.0).astype(np.uint8).tolist(),
            "metadata": dict(self.metadata),
        }

    def to_json(self, indent=2):
        """Serialize this palette without embedding NumPy objects."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, value):
        """Load a validated palette record from a JSON-compatible mapping.

        Tagged PixelatorPlus Palette records have an explicit v1 RGB8
        contract, so their values are never inferred from their magnitude.
        Untagged dictionaries retain unambiguous legacy RGB8 values above one
        and normalized float convenience values.  Integer-only values in the
        shared 0..1 range remain ambiguous and must declare NORMALIZED or
        RGB8 encoding.
        """
        if not isinstance(value, dict):
            raise ValueError("not a PixelatorPlus palette record")
        tagged = value.get("format")
        if tagged not in (None, "PixelatorPlus Palette"):
            raise ValueError("not a PixelatorPlus palette record")
        if tagged == "PixelatorPlus Palette" and value.get("version") != 1:
            raise ValueError("unsupported PixelatorPlus palette version")

        raw_colors = value.get("colors")
        colors = np.asarray(raw_colors, dtype=np.float32)
        if colors.ndim != 2 or colors.shape[1] < 3:
            raise ValueError("palette JSON colors must be an array of RGB entries")
        colors = colors[:, :3]
        if not np.all(np.isfinite(colors)):
            raise ValueError("palette JSON colors must be finite RGB values")

        if tagged == "PixelatorPlus Palette":
            if np.any(colors < 0.0) or np.any(colors > 255.0):
                raise ValueError("PixelatorPlus Palette v1 colors must be RGB8 values")
            if not np.all(colors == np.rint(colors)):
                raise ValueError("PixelatorPlus Palette v1 colors must be integer RGB8 values")
            colors /= np.float32(255.0)
        else:
            encoding = value.get("encoding", value.get("color_encoding"))
            if encoding is not None:
                encoding = str(encoding).upper()
                if encoding not in ("NORMALIZED", "RGB8"):
                    raise ValueError("untagged palette colors must declare normalized or RGB8 encoding")
            explicit_float = np.issubdtype(np.asarray(raw_colors).dtype, np.floating)
            if np.any(colors < 0.0):
                raise ValueError("untagged palette colors must be non-negative")
            if encoding == "RGB8" or (encoding is None and np.any(colors > 1.0)):
                if np.any(colors > 255.0) or not np.all(colors == np.rint(colors)):
                    raise ValueError("untagged RGB8 palette colors must be integer values from 0 to 255")
                colors /= np.float32(255.0)
            elif encoding is None and not explicit_float:
                raise ValueError(
                    "ambiguous untagged palette colors; use normalized floats "
                    "or declare encoding='normalized'"
                )
            if np.any(colors > 1.0):
                raise ValueError("untagged palette colors must be normalized to 0..1")
        return cls(colors[:, :3], value.get("name", "Untitled Palette"), value.get("metadata", {}))

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(str(text)))

    def save_json(self, path):
        """Write a portable palette file to a user-selected path."""
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(self.to_json())

    @classmethod
    def load_json(cls, path):
        with open(path, "r", encoding="utf-8-sig") as handle:
            return cls.from_json(handle.read())


def _flatten_colors(image):
    image = np.asarray(image, dtype=np.float32)
    if image.ndim == 2 and image.shape[1] >= 3:
        return np.clip(image[:, :3], 0.0, 1.0)
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("image colors must have shape (h,w,3|4) or (n,3)")
    flat = np.clip(image[..., :3], 0.0, 1.0).reshape(-1, 3)
    if image.shape[2] > 3:
        alpha = image[..., 3].reshape(-1)
        flat = flat[alpha > 1e-6]
    return flat


def extract_exact(image, max_colors=256):
    """Return unique 8-bit colors ordered by descending frequency."""
    flat = _flatten_colors(image)
    if flat.shape[0] == 0:
        raise ValueError("cannot extract a palette from an empty image")
    values = np.rint(flat * 255.0).astype(np.uint8)
    unique, counts = np.unique(values, axis=0, return_counts=True)
    order = np.argsort(-counts, kind="stable")[:max(1, min(int(max_colors), 256))]
    return (unique[order].astype(np.float32) / 255.0).astype(np.float32)


def extract_frequency(image, max_colors=32):
    """Extract the most frequent exact display colors."""
    return extract_exact(image, max_colors)


def extract_palette(image, method="KMEANS", max_colors=32, space="RGB", quality=2,
                    seed=1, gamma=1.0, force_colors="NONE"):
    """Extract a palette using K-means, frequency, or exact-color analysis."""
    method = str(method or "KMEANS").upper()
    if method in ("FREQUENCY", "EXACT"):
        return extract_exact(image, max_colors)
    flat = _flatten_colors(image)
    return kmeans_palette(
        flat, max_colors, space=space, quality=quality, gamma=gamma,
        force_colors=force_colors, seed=seed,
    )


# ---------------------------------------------------------------------------
# Color ramps (PixelatorPlus-native; hand-built pixel-art palette practice)
# ---------------------------------------------------------------------------

# Oklab hue angles that shadows and highlights lean toward: cool blue-violet
# and warm yellow, the usual pixel-art "hue shifting" directions.
_COOL_HUE = np.radians(264.0)
_WARM_HUE = np.radians(100.0)
# Families this flat still get a usable spread of shades.
_MIN_RAMP_SPAN = 0.3
# Below this Oklab chroma a family is neutral: its hue is noise, not color.
_NEUTRAL_CHROMA = 0.02


def _rotate_toward(hue, target, amount):
    """Rotate ``hue`` toward ``target`` by up to ``amount`` radians, no overshoot."""
    delta = (target - hue + np.pi) % (2.0 * np.pi) - np.pi
    return hue + np.sign(delta) * min(abs(delta), amount)


def extract_ramps(colors, ramps=4, steps=4, hue_shift=20.0, seed=1, quality=2):
    """Build a palette of ``ramps`` hue families with ``steps`` shades each.

    Colors are clustered in Oklab with lightness down-weighted, so families
    form by hue and chroma.  Each family becomes a dark-to-light ramp across
    its own lightness range (widened when the family is nearly flat).  Shades
    rotate their hue by up to ``hue_shift`` degrees toward cool blue in the
    shadows and warm yellow in the highlights, and lose a little chroma at
    the extremes (15% at most); neutral families stay neutral.  Returns ``(K, 3)`` float32
    RGB ordered by family, then dark to light (``K <= ramps * steps``).
    """
    samples = to_space(np.asarray(colors, dtype=np.float32)[:, :3], "OKLAB").astype(np.float32)
    if samples.shape[0] == 0:
        raise ValueError("cannot build color ramps from an empty image")
    ramps = int(np.clip(ramps, 1, 32))
    steps = int(np.clip(steps, 2, 16))
    quality = int(np.clip(quality, 0, 8))
    rng = np.random.default_rng(seed)
    if samples.shape[0] > _MAX_SAMPLES[quality]:
        samples = samples[rng.choice(samples.shape[0], _MAX_SAMPLES[quality], replace=False)]
    weights = np.array([0.35, 1.0, 1.0], dtype=np.float32)
    families = min(ramps, samples.shape[0])
    _centroids, labels = kmeans(samples * weights, families, _ITERATIONS[quality], 2, rng,
                                return_labels=True)
    max_shift = np.radians(float(np.clip(hue_shift, 0.0, 90.0)))
    shade = np.linspace(-1.0, 1.0, steps)  # -1 darkest ... 1 lightest
    palette = []
    for family in range(families):
        members = samples[labels == family]
        if members.shape[0] == 0:
            continue
        low, high = np.percentile(members[:, 0], (5.0, 95.0))
        middle = 0.5 * (low + high)
        half = max(0.5 * (high - low), 0.5 * _MIN_RAMP_SPAN)
        low, high = max(middle - half, 0.08), min(middle + half, 0.97)
        # The median member chroma keeps a family as saturated as its pixels;
        # the length of the mean a/b vector shrinks whenever hues vary.
        chroma = float(np.median(np.hypot(members[:, 1], members[:, 2])))
        hue = float(np.arctan2(members[:, 2].mean(), members[:, 1].mean()))
        for t in shade:
            lightness = low + (t + 1.0) * 0.5 * (high - low)
            if chroma < _NEUTRAL_CHROMA:
                shade_hue = hue
            else:
                target = _COOL_HUE if t < 0 else _WARM_HUE
                shade_hue = _rotate_toward(hue, target, abs(t) * max_shift)
            shade_chroma = chroma * (1.0 - 0.15 * t * t)
            palette.append((lightness, shade_chroma * np.cos(shade_hue),
                            shade_chroma * np.sin(shade_hue)))
    rgb = from_space(np.asarray(palette, dtype=np.float32), "OKLAB")
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def _rgb_to_hsv(rgb):
    rgb = np.asarray(rgb, dtype=np.float32)
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    delta = mx - mn
    hue = np.zeros_like(mx)
    safe = delta > 1e-8
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.where(safe & (mx == r), ((g - b) / np.maximum(delta, 1e-8)) % 6.0, hue)
    hue = np.where(safe & (mx == g), (b - r) / np.maximum(delta, 1e-8) + 2.0, hue)
    hue = np.where(safe & (mx == b), (r - g) / np.maximum(delta, 1e-8) + 4.0, hue)
    hue = hue / 6.0
    sat = np.where(mx <= 1e-8, 0.0, delta / np.maximum(mx, 1e-8))
    return np.stack([hue, sat, mx], axis=-1)


def sort_palette(colors, mode="NONE", reverse=False):
    """Sort colors by luminance, hue, saturation, or RGB components."""
    colors = np.asarray(colors, dtype=np.float32)[:, :3]
    mode = str(mode or "NONE").upper()
    if mode == "NONE":
        return colors.copy()
    if mode in ("LUMINANCE", "BRIGHTNESS"):
        keys = (colors @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32),)
    elif mode == "HUE":
        hsv = _rgb_to_hsv(colors)
        keys = (hsv[:, 0], hsv[:, 1], hsv[:, 2])
    elif mode == "SATURATION":
        hsv = _rgb_to_hsv(colors)
        keys = (hsv[:, 1], hsv[:, 2], hsv[:, 0])
    elif mode == "RGB":
        keys = (colors[:, 0], colors[:, 1], colors[:, 2])
    else:
        raise ValueError(f"unknown palette sort mode {mode!r}")
    order = np.lexsort(tuple(np.asarray(key) for key in reversed(keys)))
    if reverse:
        order = order[::-1]
    return colors[order].astype(np.float32)


def shift_palette(colors, amount):
    """Cyclically rotate palette indices."""
    colors = np.asarray(colors, dtype=np.float32)[:, :3]
    if colors.shape[0] == 0:
        return colors.copy()
    return np.roll(colors, int(amount) % colors.shape[0], axis=0).astype(np.float32)


def trim_palette(colors, tolerance=1.0 / 255.0):
    """Remove near-duplicate colors while preserving first-seen order."""
    colors = np.asarray(colors, dtype=np.float32)[:, :3]
    kept = []
    tol2 = float(max(tolerance, 0.0)) ** 2
    for color in colors:
        if not kept:
            kept.append(color)
            continue
        existing = np.asarray(kept, dtype=np.float32)
        if np.min(((existing - color) ** 2).sum(axis=1)) > tol2:
            kept.append(color)
    return np.asarray(kept, dtype=np.float32).reshape(-1, 3)


def shrink_palette(colors, target, method="KMEANS", space="RGB", seed=1):
    """Reduce an existing palette with deterministic k-means or histogram order."""
    colors = trim_palette(colors)
    target = max(1, min(int(target), 256))
    if colors.shape[0] <= target:
        return colors.copy()
    if str(method).upper() in ("HISTOGRAM", "FREQUENCY"):
        return colors[:target].copy()
    return kmeans_palette(colors, target, space=space, quality=2, seed=seed)


def replace_palette(source, target, threshold=1.0, space="RGB"):
    """Replace source entries by nearest target entries within a distance limit."""
    source = np.asarray(source, dtype=np.float32)[:, :3]
    target = np.asarray(target, dtype=np.float32)[:, :3]
    if source.shape[0] == 0 or target.shape[0] == 0:
        raise ValueError("source and target palettes must not be empty")
    src_space = to_space(source, space)
    dst_space = to_space(target, space)
    distances = ((src_space[:, None, :] - dst_space[None, :, :]) ** 2).sum(axis=2)
    indices = np.argmin(distances, axis=1)
    # CIELAB/Oklab have different native scales; interpret threshold as a
    # normalized control while retaining useful perceptual separation.
    scale = {"RGB": 1.0, "CIELAB": 100.0, "OKLAB": 1.0}.get(str(space).upper(), 1.0)
    limit = (float(threshold) * scale) ** 2
    out = source.copy()
    close = distances[np.arange(source.shape[0]), indices] <= limit
    out[close] = target[indices[close]]
    return out.astype(np.float32)


def per_channel_palette(bits):
    """Return the complete RGB cube for a per-channel bit depth."""
    bits = max(1, min(int(bits), 8))
    levels = np.linspace(0.0, 1.0, 1 << bits, dtype=np.float32)
    r, g, b = np.meshgrid(levels, levels, levels, indexing="ij")
    return np.stack([r, g, b], axis=-1).reshape(-1, 3).astype(np.float32)
