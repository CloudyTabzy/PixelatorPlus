"""Quantization stage: custom palette generation, per-channel reduction, and
LUT/palette application.

Custom palette generation is k-means clustering in RGB / CIELAB / Oklab
(spec: QuantizeType "Generate Custom Palette [Intensive]", Color_Mode).
Exact PixelatorPlus convergence behavior is bytecode-locked; QuantizeQuality is
mapped to sample count + Lloyd iterations as documented below. Initialize_Mode
maps to four init strategies (the original modes are unnamed in the XML).

Error diffusion (DIFFUSION_METHODS / diffuse_colors / apply_palette_diffusion /
per_channel_diffusion) is an add-on extra with no Substance spec counterpart:
classic Floyd-Steinberg / Atkinson / Sierra Lite / Jarvis-Judice-Ninke / Linear
dithering on the pixel grid, with an explicit serpentine-scan policy.
"""

import numpy as np

from .colorspace import from_space, gamma_apply, gamma_remove, lab_to_rgb, rgb_to_lab, to_space
from .palettes import resolve as resolve_builtin

# quality 0..8 -> max samples / Lloyd iterations
_MAX_SAMPLES = {q: min(2048 << q, 262144) for q in range(9)}
_ITERATIONS = {q: 5 + 3 * q for q in range(9)}


def _nearest_indices(values, codebook, chunk=4096, return_distances=False):
    """Chunked nearest-codebook lookup for (N,3) values and (K,3) codebook.

    Float32 keeps the full-resolution palette-application path compact while
    chunking bounds the temporary N-by-K distance matrix.  The two distance
    buffers are reused across chunks and accumulated in place, in the same
    ``dr² + dg² + db²`` order as the plain expression, so results (including
    argmin ties) are unchanged while memory traffic stays small.  When
    requested, also return the squared distance to the selected entry for
    k-means reseed decisions.
    """
    values = np.asarray(values, dtype=np.float32)
    codebook = np.asarray(codebook, dtype=np.float32)
    n = values.shape[0]
    out = np.empty(n, dtype=np.int32)
    distances = np.empty(n, dtype=np.float32) if return_distances else None
    dist_buf = np.empty((min(chunk, n), codebook.shape[0]), dtype=np.float32)
    term_buf = np.empty_like(dist_buf)
    for s in range(0, n, chunk):
        v = values[s : s + chunk]
        m = v.shape[0]
        d, term = dist_buf[:m], term_buf[:m]
        np.subtract(v[:, 0:1], codebook[:, 0], out=d)
        np.square(d, out=d)
        for axis in (1, 2):
            np.subtract(v[:, axis : axis + 1], codebook[:, axis], out=term)
            np.square(term, out=term)
            d += term
        idx = np.argmin(d, axis=1)
        out[s : s + m] = idx
        if return_distances:
            distances[s : s + m] = d[np.arange(m), idx]
    if return_distances:
        return out, distances
    return out


# ---------------------------------------------------------------------------
# k-means palette generation
# ---------------------------------------------------------------------------

def _init_centroids(samples, k, mode, rng):
    n = samples.shape[0]
    if mode == 2 or mode == "KMEANS++":
        centroids = np.empty((k, 3), dtype=np.float32)
        centroids[0] = samples[rng.integers(n)]
        closest_d2 = ((samples - centroids[0]) ** 2).sum(axis=1)
        for ci in range(1, k):
            total = closest_d2.sum(dtype=np.float64)
            if total <= 1e-12:
                sample_idx = rng.integers(n)
            else:
                sample_idx = rng.choice(n, p=closest_d2 / total)
            centroids[ci] = samples[sample_idx]
            d2 = ((samples - centroids[ci]) ** 2).sum(axis=1)
            np.minimum(closest_d2, d2, out=closest_d2)
        return centroids
    if mode == 3:  # luminance-spaced quantiles
        luma = samples @ np.array([0.2126, 0.7152, 0.0722])
        order = np.argsort(luma)
        idx = order[np.linspace(0, n - 1, k).astype(np.int64)]
        return samples[idx].copy()
    if mode == 4:  # shuffled unique colors
        uniq = np.unique(samples, axis=0)
        if uniq.shape[0] >= k:
            return uniq[rng.choice(uniq.shape[0], k, replace=False)]
        extra = rng.choice(n, k - uniq.shape[0], replace=True)
        return np.concatenate([uniq, samples[extra]], axis=0)
    # mode 1 (default): random samples
    return samples[rng.choice(n, k, replace=n < k)].copy()


def kmeans_palette(rgb, k, space="RGB", quality=2, init_mode=1, gamma=1.0,
                   force_colors="NONE", seed=1, chroma_importance=None):
    """Cluster pixel colors into a palette of k colors.

    rgb: (N, 3) float 0..1 source pixels (already pixelated/dithered per the
    pipeline). Returns (k, 3) float 0..1 RGB palette.

    `chroma_importance` (v2.01's "Color Importance", 0..50, default 35) is a
    documented reconstruction: clustering switches to CIELAB with the a/b
    axes weighted by importance/35, so 0 clusters on luminance alone and 50
    slightly over-weights chroma. Overrides `space` when set.
    """
    k = int(np.clip(k, 2, 256))
    rng = np.random.default_rng(seed)
    chroma_w = None if chroma_importance is None else float(chroma_importance) / 35.0

    def project(colors):
        """Map gamma-adjusted RGB into the clustering space."""
        if chroma_w is None:
            return to_space(colors, space).astype(np.float32)
        lab = rgb_to_lab(colors).astype(np.float32)
        lab[:, 1:] *= chroma_w
        return lab

    pts = project(gamma_apply(np.asarray(rgb, dtype=np.float32), gamma))

    n = pts.shape[0]
    if n == 0:
        raise ValueError("cannot generate a palette from an empty image")
    max_samples = _MAX_SAMPLES[int(np.clip(quality, 0, 8))]
    if n > max_samples:
        pts = pts[rng.choice(n, max_samples, replace=False)]
    iterations = _ITERATIONS[int(np.clip(quality, 0, 8))]

    centroids = _init_centroids(pts, k, init_mode, rng)
    for _ in range(iterations):
        idx, nearest_d2 = _nearest_indices(pts, centroids, return_distances=True)
        new = centroids.copy()
        counts = np.bincount(idx, minlength=k)
        populated = counts > 0
        for axis in range(3):
            sums = np.bincount(idx, weights=pts[:, axis], minlength=k)
            new[populated, axis] = sums[populated] / counts[populated]
        if not np.all(populated):
            farthest = np.argsort(nearest_d2)[::-1]
            for offset, ci in enumerate(np.flatnonzero(~populated)):
                new[ci] = pts[farthest[offset % n]]
        shift = np.abs(new - centroids).max()
        centroids = new
        if shift < 1e-4:
            break

    if chroma_w is not None:
        centroids[:, 1:] /= max(chroma_w, 1e-6)
        palette = gamma_remove(lab_to_rgb(centroids), gamma)
    else:
        palette = gamma_remove(from_space(centroids, space), gamma)

    force_colors = str(force_colors).upper()
    if force_colors in ("BLACK_WHITE", "DARKEST_BRIGHTEST"):
        if force_colors == "BLACK_WHITE":
            forced = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], dtype=np.float32)
        else:
            luma = np.asarray(rgb, dtype=np.float32) @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
            forced = np.stack([rgb[np.argmin(luma)], rgb[np.argmax(luma)]]).astype(np.float32)
        # replace the two least-populated palette entries
        idx = _nearest_indices(pts, project(gamma_apply(palette, gamma)))
        counts = np.bincount(idx, minlength=k)
        least = np.argsort(counts)[:2]
        palette[least] = forced
    return palette.astype(np.float32)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def apply_palette(img, palette, apply_space="RGB", return_indices=False):
    """Snap every pixel to its nearest palette color in the given space.

    img: (h, w, 3) float 0..1. palette: (K, 3) float 0..1 RGB.
    Returns (h, w, 3) float32, or ``(image, indices)`` when
    ``return_indices`` is true.  Indices are canonicalized so duplicate
    palette colors retain the same output-palette encoding as a fresh lookup.
    """
    h, w = img.shape[:2]
    flat = img[..., :3].reshape(-1, 3)
    pts = to_space(flat, apply_space)
    pal_pts = to_space(palette[:, :3], apply_space)
    idx = _nearest_indices(pts, pal_pts)
    out = palette[idx].reshape(h, w, 3).astype(np.float32)
    if return_indices:
        canonical = _nearest_indices(pal_pts, pal_pts)
        return out, canonical[idx].reshape(h, w)
    return out


def palette_index_image(img, palette, apply_space="RGB", indices=None):
    """Encode nearest-palette indices as a grayscale RGBA image.

    This is the v2.72 ``Output_Palette`` reconstruction.  Each pixel stores
    its palette index normalized to 0..1 in RGB, with opaque alpha.  The
    palette swatch remains available separately through ``palette_swatch``.
    """
    h, w = img.shape[:2]
    if indices is None:
        flat = img[..., :3].reshape(-1, 3)
        pts = to_space(flat, apply_space)
        pal_pts = to_space(palette[:, :3], apply_space)
        idx = _nearest_indices(pts, pal_pts).reshape(h, w)
    else:
        idx = np.asarray(indices, dtype=np.int32)
        if idx.shape != (h, w):
            raise ValueError("palette indices must match the image dimensions")
    denom = max(palette.shape[0] - 1, 1)
    encoded = (idx.astype(np.float32) / denom).reshape(h, w, 1)
    rgb = np.repeat(encoded, 3, axis=-1)
    alpha = np.ones((h, w, 1), dtype=np.float32)
    return np.concatenate([rgb, alpha], axis=-1).astype(np.float32)


def per_channel_levels(colors_or_bits="COLORS", n_colors=256, n_bits=8):
    """Per-channel level count for Colors/Bits Per Channel, clamped to 2..256."""
    if str(colors_or_bits).upper() == "BITS":
        levels = 1 << int(n_bits)
    else:
        levels = int(n_colors)
    return max(2, min(levels, 256))


def per_channel(img, colors_or_bits="COLORS", n_colors=256, n_bits=8,
                range_adaptive=False):
    """Reduce each channel to N levels (Colors Per Channel / Bits Per Channel).

    range_adaptive maps the observed per-channel min..max range onto the
    levels instead of the full 0..1 range (spec: UseRangeAdaptive).
    """
    x = img[..., :3].astype(np.float32)
    levels = per_channel_levels(colors_or_bits, n_colors, n_bits)
    if range_adaptive:
        lo = x.reshape(-1, 3).min(axis=0)
        hi = x.reshape(-1, 3).max(axis=0)
        span = np.maximum(hi - lo, 1e-6)
        q = np.round((x - lo) / span * (levels - 1)) / (levels - 1)
        out = q * span + lo
    else:
        out = np.round(x * (levels - 1)) / (levels - 1)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def reduce_bits(img, bits):
    """Bit-depth reduction (used for the Gameboy Color 15-bit builtin)."""
    return per_channel(img, "BITS", n_bits=bits)


def apply_builtin(img, name, apply_space="RGB"):
    """Apply a built-in retro palette/reducer from core.palettes."""
    name = name.upper()
    # These palettes are uniform RGB cubes, so per-channel reduction gives
    # the exact same nearest result without allocating a large distance matrix.
    if name == "MASTER_SYSTEM":
        return per_channel(img, "COLORS", n_colors=4)
    if name == "WEB":
        return per_channel(img, "COLORS", n_colors=6)
    kind, data = resolve_builtin(name)
    if kind == "reduce":
        return reduce_bits(img, data)
    return apply_palette(img, data, apply_space)


def palette_from_image(palette_img):
    """Extract the opaque unique colors of a user-supplied palette image.

    Returns (N, 3) float32 0..1, at most 256 entries (matching the add-on's
    palette controls and keeping photographic inputs from exhausting memory).
    """
    palette_img = np.asarray(palette_img, dtype=np.float32)
    px = palette_img[..., :3].reshape(-1, 3)
    if palette_img.shape[-1] >= 4:
        px = px[palette_img[..., 3].reshape(-1) > 1e-6]
    palette = np.unique(np.round(px, decimals=6), axis=0)
    if palette.shape[0] == 0:
        raise ValueError("custom palette image has no opaque colors")
    if palette.shape[0] > 256:
        raise ValueError(
            f"custom palette image has {palette.shape[0]} opaque colors; maximum is 256"
        )
    return palette.astype(np.float32)


def apply_custom_palette_image(img, palette_img, apply_space="RGB"):
    """Apply opaque unique colors from a user-supplied palette image.

    Transparent pixels are layout padding rather than colors.
    """
    return apply_palette(img, palette_from_image(palette_img), apply_space)


def palette_swatch(palette, cell=16):
    """Render a palette as a swatch-grid RGBA image (for Output_Palette).

    Up to 16 columns, 16px cells; unused cells are transparent.
    """
    palette = np.asarray(palette, dtype=np.float32)[:, :3]
    k = palette.shape[0]
    cols = min(16, k)
    rows = -(-k // cols)
    img = np.zeros((rows * cell, cols * cell, 4), dtype=np.float32)
    for i, color in enumerate(palette):
        r, c = divmod(i, cols)
        img[r * cell : (r + 1) * cell, c * cell : (c + 1) * cell, :3] = color
        img[r * cell : (r + 1) * cell, c * cell : (c + 1) * cell, 3] = 1.0
    return img


# ---------------------------------------------------------------------------
# Error diffusion (add-on extra, not from the Substance spec)
# ---------------------------------------------------------------------------

DIFFUSION_METHODS = (
    "NONE", "FLOYD_STEINBERG", "ATKINSON", "SIERRA_LITE", "JJN", "LINEAR",
)

# (dy, dx, weight) error-propagation kernels; dx is mirrored on right-to-left
# serpentine rows.
_DIFFUSION_KERNELS = {
    "FLOYD_STEINBERG": ((0, 1, 7 / 16), (1, -1, 3 / 16), (1, 0, 5 / 16), (1, 1, 1 / 16)),
    "ATKINSON": (
        (0, 1, 1 / 8), (0, 2, 1 / 8),
        (1, -1, 1 / 8), (1, 0, 1 / 8), (1, 1, 1 / 8),
        (2, 0, 1 / 8),
    ),
    "SIERRA_LITE": ((0, 1, 2 / 4), (1, -1, 1 / 4), (1, 0, 1 / 4)),
    # Jarvis-Judice-Ninke: broad, soft error distribution.
    "JJN": (
        (0, 1, 7 / 48), (0, 2, 5 / 48),
        (1, -2, 3 / 48), (1, -1, 5 / 48), (1, 0, 7 / 48),
        (1, 1, 5 / 48), (1, 2, 3 / 48),
        (2, -2, 1 / 48), (2, -1, 3 / 48), (2, 0, 5 / 48),
        (2, 1, 3 / 48), (2, 2, 1 / 48),
    ),
    # Linear is a deliberately restrained one-dimensional reconstruction: it
    # carries the error to the next scan pixel, useful for line-art ramps.
    "LINEAR": ((0, 1, 1.0),),
}
# Widest kernel reach (Atkinson/JJN: dy <= 2, |dx| <= 2).  The diffusion work
# buffer carries a zero border this wide so out-of-image error lands in
# padding instead of needing a bounds check per neighbor.
_DIFFUSION_PAD = max(
    max(dy, abs(dx)) for kernel in _DIFFUSION_KERNELS.values() for dy, dx, _w in kernel
)


def diffuse_colors(grid, snap_fn, method="FLOYD_STEINBERG", strength=1.0, serpentine=True):
    """Error-diffuse `grid` (gh, gw, 3) float 0..1, snapping each pixel with
    snap_fn(points (N,3) -> snapped (N,3) float 0..1). Serpentine scan;
    `strength` (0..1) scales the propagated error (Atkinson's classic look is
    strength 1.0 with its 6-neighbor 1/8 kernel). Returns (gh, gw, 3) float32.

    This is an add-on extra with no Substance spec counterpart.  Error
    diffusion is inherently sequential, so it runs on the (small) pixel grid
    with a Python loop over pixels; each pixel's kernel neighbors are updated
    with one vectorized gather/scatter on a zero-padded flat buffer.  The scan
    is deterministic and optionally boustrophedon.  The accumulator is clipped
    to 0..1 as errors propagate.
    """
    grid = np.asarray(grid, dtype=np.float32)[..., :3]
    gh, gw = grid.shape[:2]
    method = str(method).upper()
    if method == "NONE":
        return np.asarray(snap_fn(grid.reshape(-1, 3)), dtype=np.float32).reshape(gh, gw, 3)
    if method not in _DIFFUSION_KERNELS:
        raise ValueError(
            f"unknown diffusion method {method!r}; expected one of {DIFFUSION_METHODS}"
        )
    kernel = _DIFFUSION_KERNELS[method]
    strength = float(np.clip(strength, 0.0, 1.0))
    pad = _DIFFUSION_PAD
    stride = gw + 2 * pad
    weights = np.array([w for _dy, _dx, w in kernel], dtype=np.float64)[:, None]
    # Flat neighbor offsets; dx is mirrored on right-to-left serpentine rows.
    forward = np.array([dy * stride + dx for dy, dx, _w in kernel], dtype=np.intp)
    backward = np.array([dy * stride - dx for dy, dx, _w in kernel], dtype=np.intp)
    padded = np.zeros((gh + pad, stride, 3), dtype=np.float64)
    padded[:gh, pad:pad + gw] = grid
    work = padded.reshape(-1, 3)
    out = np.empty((gh, gw, 3), dtype=np.float32)
    for y in range(gh):
        left_to_right = (y % 2) == 0 or not serpentine
        offsets = forward if left_to_right else backward
        row = y * stride + pad
        for x in (range(gw) if left_to_right else range(gw - 1, -1, -1)):
            pos = row + x
            # minimum/maximum is np.clip without its per-call Python overhead,
            # which dominates on 3-element arrays.
            current = np.minimum(np.maximum(work[pos], 0.0), 1.0)
            snapped = np.asarray(snap_fn(current[None, :]), dtype=np.float64)[0]
            out[y, x] = snapped
            err = (current - snapped) * strength
            targets = offsets + pos
            work[targets] = np.minimum(np.maximum(work[targets] + err * weights, 0.0), 1.0)
    return out


def apply_palette_diffusion(grid, palette, method="FLOYD_STEINBERG", strength=1.0,
                            apply_space="RGB", serpentine=True):
    """Diffuse `grid` (gh, gw, 3) onto `palette` (K, 3) RGB 0..1; nearest-color
    lookup in `apply_space` (RGB/CIELAB/OKLAB via to_space), error math in RGB.

    Add-on extra, not from the Substance spec; see diffuse_colors.
    """
    snap_fn = palette_snap_fn(palette, apply_space)
    return diffuse_colors(grid, snap_fn, method, strength, serpentine)


def per_channel_diffusion(grid, levels, method="FLOYD_STEINBERG", strength=1.0, serpentine=True):
    """Diffuse `grid` onto `levels` evenly spaced levels per channel (1-bit
    per channel = levels 2 is the classic Macintosh look).

    Add-on extra, not from the Substance spec; see diffuse_colors.
    """
    return diffuse_colors(grid, per_channel_snap_fn(levels), method, strength, serpentine)


def palette_snap_fn(palette, apply_space="RGB"):
    """Return a ``points (N,3) -> nearest palette colors (N,3)`` function.

    The palette is projected into ``apply_space`` once, so the returned
    function is cheap enough to call per pixel inside :func:`diffuse_colors`.
    """
    palette = np.asarray(palette, dtype=np.float32)[:, :3]
    pal_pts = to_space(palette, apply_space)

    def snap_fn(points):
        pts = to_space(np.asarray(points, dtype=np.float32), apply_space)
        return palette[_nearest_indices(pts, pal_pts)]

    return snap_fn


def per_channel_snap_fn(levels):
    """Return a ``points (N,3) -> nearest of `levels` steps per channel`` function."""
    levels = max(2, int(levels))

    def snap_fn(points):
        pts = np.asarray(points, dtype=np.float32)
        return np.round(pts * (levels - 1)) / (levels - 1)

    return snap_fn
