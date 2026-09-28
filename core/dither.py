"""Dithering stage: threshold-map generation, blending, and masking.

Pipeline position: after pixelation, before quantization (spec section 4/9).

Blend modes (spec: DitherBlendMode): Overlay / Soft Light, each evaluable in
sRGB space (display-referred, like the default) or in linear light. The dither
threshold map is treated as a blend color centered on 0.5 (neutral).

Mask (spec: DitherMaskType, default None in v2.72): multi-scale Sobel edge
strength weighted by the seven frequency weights (Huge .. Pixel_Perfect),
gamma-adjusted and thresholded by DitherCutoff. Exact PixelatorPlus mask math is
bytecode-locked; this is a documented reconstruction.

Pattern / Amogus maps are built-in reconstructions (the originals are embedded
textures in the .sbsar type-1 chunk and are not shipped here).

BAYER_2X2 / BAYER_4X4, the HALFTONE_* / CROSSHATCH screens, the SUZANNE monkey
portrait map, and the LUMINANCE / SATURATION / GRADIENT / RADIAL mask sources are
add-on extras of this port — they do not come from the Substance spec.
"""

import os
from functools import lru_cache

import numpy as np

from .colorspace import linear_to_srgb, srgb_to_linear, to_space
from .pixelate import resample_bilinear

_BLUE_NOISE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "blue_noise_64.npy",
)


# ---------------------------------------------------------------------------
# Threshold maps
# ---------------------------------------------------------------------------

def _bayer_int(n):
    """Unnormalized Bayer matrix (integer ranks) of size n (power of two)."""
    if n == 2:
        return np.array([[0, 2], [3, 1]], dtype=np.int64)
    half = _bayer_int(n // 2)
    return np.block([[4 * half, 4 * half + 2], [4 * half + 3, 4 * half + 1]])


@lru_cache(maxsize=None)
def bayer_matrix(n):
    """Ordered Bayer matrix of size n (power of two), normalized to 0..1."""
    m = _bayer_int(n)
    return ((m + 0.5) / (n * n)).astype(np.float32)


@lru_cache(maxsize=None)
def cluster_dot_matrix(n=8):
    """Clustered-dot ordered pattern (halftone-style), normalized to 0..1.

    Ranks cells by distance from the center — a documented reconstruction of
    PixelatorPlus's built-in 'Pattern' dither.
    """
    ax = np.arange(n, dtype=np.float64) + 0.5
    yy, xx = np.meshgrid(ax, ax, indexing="ij")
    d = np.sqrt((yy - n / 2) ** 2 + (xx - n / 2) ** 2)
    order = np.argsort(d.ravel())
    m = np.empty(n * n, dtype=np.float32)
    m[order] = np.arange(n * n, dtype=np.float32)
    return ((m.reshape(n, n) + 0.5) / (n * n)).astype(np.float32)


@lru_cache(maxsize=None)
def amogus_matrix(n=16):
    """Crewmate threshold pattern (PixelatorPlus 2.72's joke option 'Amogus').

    A hand-drawn crewmate silhouette (plus visor and backpack) is filled with
    an ordered ramp in the lower threshold half; the background takes the
    upper half, so the shape emerges in mid-tone dithering.
    """
    body = [
        "................",
        "....XXXXXX......",
        "...XXXXXXXX.....",
        "..XXXVVVVXXX....",
        "..XXVVVVVVXX....",
        "..XXVVVVVVXX....",
        "..XXXXXXXXXX....",
        "..XXXXXXXXXX....",
        ".BBXXXXXXXXX....",
        ".BBXXXXXXXXX....",
        ".BBXXXXXXXXX....",
        "..XXXXXXXXXX....",
        "..XXX....XXX....",
        "..XXX....XXX....",
        "................",
        "................",
    ]
    mask_body = np.array([[c == "X" for c in row] for row in body])
    mask_visor = np.array([[c == "V" for c in row] for row in body])
    inside = mask_body | mask_visor

    ramp = bayer_matrix(8)  # 0..1
    ramp = np.kron(ramp, np.ones((2, 2)))  # -> 16x16
    m = np.zeros((n, n), dtype=np.float32)
    # visor slightly darker than body within the lower half
    m[mask_visor] = ramp[mask_visor] * 0.20
    m[mask_body] = 0.20 + ramp[mask_body] * 0.25
    m[~inside] = 0.5 + ramp[~inside] * 0.5
    return m


@lru_cache(maxsize=None)
def halftone_dot_matrix(n=8):
    """45-degree rotated halftone dot screen on an n-px tile, 0..1.

    Add-on extra (not from the Substance spec). Rotated coordinates
    u = x + y, v = x - y with a cosine product; the integer-frequency phases
    make the tile seamless and the product spans the full 0..1 range.
    """
    ax = np.arange(n, dtype=np.float64)
    yy, xx = np.meshgrid(ax, ax, indexing="ij")
    phase = 2.0 * np.pi / n
    m = 0.5 + 0.5 * np.cos((xx + yy) * phase) * np.cos((xx - yy) * phase)
    return m.astype(np.float32)


@lru_cache(maxsize=None)
def halftone_line_matrix(n=8):
    """Diagonal halftone line screen (sine bands along x + y), 0..1.

    Add-on extra (not from the Substance spec). Two lines per tile; the
    integer frequency keeps the tile seamless.
    """
    ax = np.arange(n, dtype=np.float64)
    yy, xx = np.meshgrid(ax, ax, indexing="ij")
    m = 0.5 + 0.5 * np.sin((xx + yy) * (4.0 * np.pi / n))
    return m.astype(np.float32)


@lru_cache(maxsize=None)
def crosshatch_matrix(n=8):
    """Crosshatch screen: two perpendicular diagonal sine bands, 0..1.

    Add-on extra (not from the Substance spec). Seamless n-px tile.
    """
    ax = np.arange(n, dtype=np.float64)
    yy, xx = np.meshgrid(ax, ax, indexing="ij")
    phase = 4.0 * np.pi / n
    m = 0.5 + 0.25 * (np.sin((xx + yy) * phase) + np.sin((xx - yy) * phase))
    return m.astype(np.float32)


def _ellipse(xx, yy, cx, cy, rx, ry):
    """Return a vectorized filled ellipse in normalized image coordinates."""
    return ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0


def _triangle(xx, yy, a, b, c):
    """Return a vectorized filled triangle using barycentric coordinates."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    u = ((by - cy) * (xx - cx) + (cx - bx) * (yy - cy)) / den
    v = ((cy - ay) * (xx - cx) + (ax - cx) * (yy - cy)) / den
    return (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0)


def _capsule(xx, yy, a, b, radius):
    """Return a vectorized rounded line segment (a capsule)."""
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    t = np.clip(((xx - ax) * vx + (yy - ay) * vy) / (vx * vx + vy * vy), 0.0, 1.0)
    dx = xx - (ax + t * vx)
    dy = yy - (ay + t * vy)
    return dx * dx + dy * dy <= radius * radius


@lru_cache(maxsize=2)
def suzanne_frame(h, w):
    """Build a centered, non-tiled Suzanne likeness as an ordered threshold map.

    Add-on extra (not from the Substance spec). The silhouette, recessed ear
    cups, heavy brow, eye rings, broad muzzle, nostrils, and smile are described
    procedurally in normalized coordinates. Low thresholds shade the monkey
    first; the background stays bright so the face resolves as dither density
    changes. Returned rows are bottom-up for Blender image buffers.
    """
    h, w = int(h), int(w)
    if h <= 0 or w <= 0:
        raise ValueError("Suzanne frame dimensions must be positive")

    # Use the shorter side as the unit so a wide image does not squash the
    # monkey. y increases toward the top of the displayed image here; the
    # finished map is flipped below for Blender's bottom-up pixel order.
    unit = float(min(h, w))
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    x += 0.5 - w * 0.5
    # Express landmarks in display coordinates (positive y points up), then
    # flip the finished map to Blender's bottom-up pixel-buffer convention.
    y = h * 0.5 - y - 0.5
    x /= unit
    y /= unit

    crown = _ellipse(x, y, 0.0, 0.055, 0.30, 0.32)
    cheeks = _ellipse(x, y, 0.0, -0.085, 0.32, 0.25)
    jaw = _ellipse(x, y, 0.0, -0.235, 0.215, 0.135)
    left_ear = _ellipse(x, y, -0.355, 0.015, 0.135, 0.18)
    right_ear = _ellipse(x, y, 0.355, 0.015, 0.135, 0.18)
    ears = left_ear | right_ear
    silhouette = crown | cheeks | jaw | ears
    del crown, cheeks, jaw, left_ear, right_ear

    # A small Bayer grain keeps the threshold surface alive without the
    # coarse checker effect of the previous 8x8 ramp.
    ramp = _tile(bayer_matrix(4), h, w)
    m = (0.83 + 0.14 * ramp).astype(np.float32)
    m[silhouette] = 0.24 + 0.16 * ramp[silhouette]
    del silhouette

    # Suzanne's round ears have an inner bowl and a raised outer rim.
    feature = _ellipse(x, y, -0.375, 0.025, 0.067, 0.105) | _ellipse(
        x, y, 0.375, 0.025, 0.067, 0.105
    )
    m[feature] = 0.57 + 0.08 * ramp[feature]
    feature = _capsule(x, y, (-0.425, -0.08), (-0.41, 0.105), 0.016) | _capsule(
        x, y, (0.425, -0.08), (0.41, 0.105), 0.016
    )
    m[feature] = 0.08 + 0.06 * ramp[feature]

    # Heavy brow ridges sit over recessed eyes; lighter eyeballs and dark
    # pupils make the face survive at thumbnail size.
    feature = _capsule(x, y, (-0.255, 0.165), (-0.055, 0.205), 0.038) | _capsule(
        x, y, (0.055, 0.205), (0.255, 0.165), 0.038
    )
    m[feature] = 0.08 + 0.08 * ramp[feature]

    feature = _ellipse(x, y, -0.135, 0.065, 0.112, 0.125) | _ellipse(
        x, y, 0.135, 0.065, 0.112, 0.125
    )
    m[feature] = 0.12 + 0.08 * ramp[feature]
    feature = _ellipse(x, y, -0.135, 0.055, 0.068, 0.080) | _ellipse(
        x, y, 0.135, 0.055, 0.068, 0.080
    )
    m[feature] = 0.62 + 0.08 * ramp[feature]
    feature = _ellipse(x, y, -0.125, 0.055, 0.027, 0.042) | _ellipse(
        x, y, 0.125, 0.055, 0.027, 0.042
    )
    m[feature] = 0.015 + 0.035 * ramp[feature]
    feature = _ellipse(x, y, -0.145, 0.082, 0.010, 0.014) | _ellipse(
        x, y, 0.145, 0.082, 0.010, 0.014
    )
    m[feature] = 0.94

    # A short bridge leads into the broad, two-lobed muzzle and rounded nose.
    feature = _capsule(x, y, (0.0, 0.055), (0.0, -0.105), 0.040)
    m[feature] = 0.34 + 0.08 * ramp[feature]
    muzzle = _ellipse(x, y, -0.082, -0.17, 0.13, 0.09) | _ellipse(
        x, y, 0.082, -0.17, 0.13, 0.09
    )
    m[muzzle] = 0.58 + 0.06 * ramp[muzzle]
    nose = _ellipse(x, y, 0.0, -0.105, 0.085, 0.057) | _triangle(
        x, y, (-0.075, -0.095), (0.075, -0.095), (0.0, -0.175)
    )
    m[nose] = 0.025 + 0.035 * ramp[nose]
    nostrils = _ellipse(x, y, -0.038, -0.11, 0.019, 0.013) | _ellipse(
        x, y, 0.038, -0.11, 0.019, 0.013
    )
    m[nostrils] = 0.0

    # Two curved mouth corners meet below the muzzle to form Suzanne's grin.
    smile = _capsule(x, y, (-0.145, -0.22), (0.0, -0.255), 0.014) | _capsule(
        x, y, (0.0, -0.255), (0.145, -0.22), 0.014
    )
    m[smile] = 0.02 + 0.035 * ramp[smile]
    lower_lip = _capsule(x, y, (-0.09, -0.285), (0.09, -0.285), 0.012)
    m[lower_lip] = 0.64 + 0.06 * ramp[lower_lip]
    return np.clip(m[::-1], 0.0, 1.0).astype(np.float32)


@lru_cache(maxsize=32)
def suzanne_matrix(n=64):
    """Square convenience wrapper for :func:`suzanne_frame`."""
    n = int(n)
    return suzanne_frame(n, n)


@lru_cache(maxsize=1)
def _load_blue_noise():
    """Load the bundled tile once; callers treat the cached array as read-only."""
    base = np.load(_BLUE_NOISE_PATH)
    base.setflags(write=False)
    return base


def _tile(m2, h, w):
    reps = [-(-h // m2.shape[0]), -(-w // m2.shape[1])] + [1] * (m2.ndim - 2)
    return np.tile(m2, reps)[:h, :w]


def _luma(rgb):
    return (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]).astype(np.float32)


def dither_map(kind, h, w, seed=0, custom=None, custom_res=(8, 8)):
    """Build the RGB threshold map (h, w, 3) in 0..1 for the given DitherType.

    Besides the spec kinds (WHITE_NOISE, BLUE_NOISE, BAYER, PATTERN, AMOGUS,
    CUSTOM*) this port adds BAYER_2X2 / BAYER_4X4, HALFTONE_DOT,
    HALFTONE_LINE and CROSSHATCH as tiled grayscale maps, plus SUZANNE as a
    centered frame-sized grayscale map, all repeated across RGB.

    `custom` is an (ch, cw, 3|4) float image for kind == CUSTOM; it is resampled
    to a (2**rx, 2**ry) tile per Custom_Dither_Resolution and tiled over the
    image. Raises ValueError if CUSTOM is selected without an image.
    """
    kind = kind.upper()
    if kind == "WHITE_NOISE":
        rng = np.random.default_rng(seed)
        return rng.random((h, w, 3), dtype=np.float32)

    if kind == "BLUE_NOISE":
        base = _load_blue_noise()  # 64x64, tileable
        # Decorrelate channels with toroidal offsets of the same tileable map.
        m = np.stack(
            [np.roll(base, (o, (o * 2 + 7) % 64), axis=(0, 1)) for o in (0, 21, 43)],
            axis=-1,
        )
        return _tile(m, h, w).astype(np.float32)

    if kind == "BAYER":
        return np.repeat(_tile(bayer_matrix(8), h, w)[..., None], 3, axis=-1)

    if kind == "PATTERN":
        return np.repeat(_tile(cluster_dot_matrix(8), h, w)[..., None], 3, axis=-1)

    if kind == "AMOGUS":
        return np.repeat(_tile(amogus_matrix(16), h, w)[..., None], 3, axis=-1)

    # --- add-on extras (not from the Substance spec) ---
    if kind == "BAYER_2X2":
        return np.repeat(_tile(bayer_matrix(2), h, w)[..., None], 3, axis=-1)

    if kind == "BAYER_4X4":
        return np.repeat(_tile(bayer_matrix(4), h, w)[..., None], 3, axis=-1)

    if kind == "HALFTONE_DOT":
        return np.repeat(_tile(halftone_dot_matrix(8), h, w)[..., None], 3, axis=-1)

    if kind == "HALFTONE_LINE":
        return np.repeat(_tile(halftone_line_matrix(8), h, w)[..., None], 3, axis=-1)

    if kind == "CROSSHATCH":
        return np.repeat(_tile(crosshatch_matrix(8), h, w)[..., None], 3, axis=-1)

    if kind == "SUZANNE":
        return np.repeat(suzanne_frame(h, w)[..., None], 3, axis=-1)

    if kind in ("CUSTOM", "CUSTOM_8X8", "CUSTOM_16X16"):
        # CUSTOM_8X8 / CUSTOM_16X16 are the v2.01 fixed-size variants (their
        # resolution is implied by the type, ignoring Custom_Dither_Resolution)
        if custom is None:
            raise ValueError("custom dither pattern image required")
        if kind == "CUSTOM_8X8":
            tw = th = 8
        elif kind == "CUSTOM_16X16":
            tw = th = 16
        else:
            rx, ry = int(custom_res[0]), int(custom_res[1])
            tw, th = 2 ** rx, 2 ** ry
        src = custom[..., :3]
        if src.shape[0] != th or src.shape[1] != tw:
            src = resample_bilinear(src, tw, th)
        return _tile(src, h, w).astype(np.float32)

    raise ValueError(f"unknown dither type: {kind}")


# ---------------------------------------------------------------------------
# Blend modes
# ---------------------------------------------------------------------------

def blend_overlay(base, blend):
    return np.where(
        base <= 0.5, 2.0 * base * blend, 1.0 - 2.0 * (1.0 - base) * (1.0 - blend)
    )


def blend_soft_light(base, blend):
    # W3C compositing soft-light
    d = np.where(base <= 0.25, ((16.0 * base - 12.0) * base + 4.0) * base, np.sqrt(np.maximum(base, 0.0)))
    return np.where(
        blend <= 0.5,
        base - (1.0 - 2.0 * blend) * base * (1.0 - base),
        base + (2.0 * blend - 1.0) * (d - base),
    )


# ---------------------------------------------------------------------------
# Mask
# ---------------------------------------------------------------------------

_WEIGHT_KEYS = ("huge", "big", "large", "medium", "fine", "sharp", "pixel_perfect")
_BAND_RADII = (32, 16, 8, 4, 2, 1, 0)  # box-blur radii per frequency band


def _box_mean_1d(x, r, axis):
    """Clamped-window running mean of a 2-D float64 array along one axis."""
    n = x.shape[axis]
    csum = np.zeros((n + 1, x.shape[1]) if axis == 0 else (x.shape[0], n + 1), dtype=np.float64)
    idx = np.arange(n)
    lo = np.clip(idx - r, 0, n)
    hi = np.clip(idx + r + 1, 0, n)
    count = (hi - lo).astype(np.float64)
    if axis == 0:
        csum[1:] = np.cumsum(x, axis=0)
        return (csum[hi] - csum[lo]) / count[:, None]
    csum[:, 1:] = np.cumsum(x, axis=1)
    return (csum[:, hi] - csum[:, lo]) / count[None, :]


def _box_blur(x, r):
    """Box blur with clamped (edge-shrinking) windows, radius ``r``.

    The clamped 2-D window is a rectangle, so its mean factors into a
    vertical then a horizontal 1-D running mean.  This avoids full-image
    index grids, which dominated peak memory on large images.
    """
    if r <= 0:
        return x
    rows = _box_mean_1d(np.asarray(x, dtype=np.float64), r, 0)
    return _box_mean_1d(rows, r, 1).astype(np.float32)


def _sobel(x):
    p = np.pad(x, 1, mode="edge")
    gx = (
        -p[:-2, :-2] - 2 * p[1:-1, :-2] - p[2:, :-2]
        + p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]
    )
    gy = (
        -p[:-2, :-2] - 2 * p[:-2, 1:-1] - p[:-2, 2:]
        + p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]
    )
    return np.hypot(gx, gy).astype(np.float32)


def edge_strength(luma, weights=None):
    """Multi-scale Sobel edge map in 0..1.

    `weights` maps the seven frequency names to 0..1 weights; each band is a
    Sobel magnitude of the luma blurred at that band's radius, robustly
    normalized to its 99th percentile.
    """
    if weights is None:
        weights = {k: 1.0 for k in _WEIGHT_KEYS}
    total_w = sum(max(0.0, float(weights.get(k, 1.0))) for k in _WEIGHT_KEYS)
    if total_w <= 0.0:
        return np.zeros_like(luma)
    acc = np.zeros_like(luma, dtype=np.float32)
    max_r = max(1, min(luma.shape) // 4)  # keep wide bands sane on small images
    for key, r in zip(_WEIGHT_KEYS, _BAND_RADII):
        wgt = max(0.0, float(weights.get(key, 1.0)))
        if wgt <= 0.0:
            continue
        band = _sobel(_box_blur(luma, min(r, max_r)))
        p99 = np.percentile(band, 99.0)
        if p99 > 1e-6:
            band = band / p99
        acc += wgt * np.clip(band, 0.0, 1.0)
    return np.clip(acc / total_w, 0.0, 1.0)


def _smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _band_mask(v, lo, hi, feather=0.05):
    """1.0 inside [lo, hi], smoothstep-falling to 0.0 over `feather` outside.

    Add-on extra (not from the Substance spec). The feather extends outward
    from the band; lo == 0 / hi == 1 are plain hard edges, no NaNs.
    """
    lo = float(np.clip(lo, 0.0, 1.0))
    hi = float(np.clip(hi, 0.0, 1.0))
    f = max(float(feather), 1e-6)
    rise = _smoothstep((v - (lo - f)) / f)
    fall = _smoothstep(((hi + f) - v) / f)
    return np.minimum(rise, fall).astype(np.float32)


def _gradient_ramp(h, w, angle_deg):
    """Positional 0..1 ramp along the unit vector at `angle_deg` degrees.

    Add-on extra (not from the Substance spec). 0 = left->right,
    90 = top->bottom; normalized over the frame corners along that axis.
    """
    ang = np.deg2rad(float(angle_deg))
    dx, dy = np.cos(ang), np.sin(ang)
    corners = np.array(
        [[0.0, 0.0], [w - 1.0, 0.0], [0.0, h - 1.0], [w - 1.0, h - 1.0]]
    )
    proj_c = corners[:, 0] * dx + corners[:, 1] * dy
    lo, hi = float(proj_c.min()), float(proj_c.max())
    if hi - lo < 1e-9:
        return np.zeros((h, w), dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    p = xx * dx + yy * dy
    return np.clip((p - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)


def _radial_falloff(h, w):
    """1.0 at the image center falling to 0.0 at the farthest corner.

    Add-on extra (not from the Substance spec). Normalized euclidean distance.
    """
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    dmax = float(np.hypot(cy, cx))
    if dmax < 1e-9:
        return np.ones((h, w), dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    d = np.hypot(yy - cy, xx - cx)
    return np.clip(1.0 - d / dmax, 0.0, 1.0).astype(np.float32)


def build_mask(mask_type, rgb, cutoff=0.0, gamma=1.0, weights=None, custom=None,
               lum_range=(0.0, 1.0), sat_range=(0.0, 1.0), gradient_angle=0.0,
               invert=False, blur=0):
    """Dither mask (h, w) float32 in 0..1.

    mask_type (case-insensitive):
      NONE       -> dither everywhere (v2.72 default); every other param ignored.
      EDGES      -> dither on edges: multi-scale Sobel luma strength, `weights`
                    mapping the seven frequency names to 0..1 band weights.
      FLATS      -> dither on flat areas (inverted EDGES).
      CUSTOM     -> luma of the user mask texture `custom` (ch, cw, 3|4) float
                    0..1, resampled to (h, w) when sizes differ.
      LUMINANCE  -> band mask on the image luma: 1 inside `lum_range` (lo, hi),
                    smoothstep-falling to 0 over a 0.05 feather outside both
                    ends (add-on extra, not from the Substance spec).
      SATURATION -> same band logic on HSV-style saturation
                    s = (max-min)/max(max, eps) per pixel, range `sat_range`
                    (add-on extra).
      GRADIENT   -> positional ramp, ignores image content: pixel coordinates
                    projected onto the unit vector at `gradient_angle` degrees
                    (0 = ramp left->right, 90 = top->bottom), normalized so the
                    ramp spans 0..1 across the frame along that axis
                    (add-on extra).
      RADIAL     -> 1.0 at the image center falling to 0.0 at the farthest
                    corner (add-on extra).

    `cutoff` (0..1) and `gamma` (>0) shape every image-derived and positional
    type exactly as they shape EDGES/CUSTOM. Post-ops applied to the final
    mask of every non-NONE type: `invert` flips the mask (m = 1 - m), `blur`
    box-blurs it with the given integer pixel radius (0 = off).
    """
    mask_type = mask_type.upper()
    h, w = rgb.shape[:2]
    if mask_type == "NONE":
        return np.ones((h, w), dtype=np.float32)

    if mask_type == "CUSTOM":
        if custom is None:
            raise ValueError("custom dither mask image required")
        m = custom[..., :3]
        if m.shape[0] != h or m.shape[1] != w:
            m = resample_bilinear(m, w, h)
        strength = _luma(m)
    elif mask_type == "LUMINANCE":
        strength = _band_mask(_luma(rgb), lum_range[0], lum_range[1])
    elif mask_type == "SATURATION":
        cmax = rgb[..., :3].max(axis=-1)
        cmin = rgb[..., :3].min(axis=-1)
        sat = ((cmax - cmin) / np.maximum(cmax, 1e-6)).astype(np.float32)
        strength = _band_mask(sat, sat_range[0], sat_range[1])
    elif mask_type == "GRADIENT":
        strength = _gradient_ramp(h, w, gradient_angle)
    elif mask_type == "RADIAL":
        strength = _radial_falloff(h, w)
    else:
        strength = edge_strength(_luma(rgb), weights)

    if gamma != 1.0:
        strength = np.power(np.clip(strength, 0.0, 1.0), 1.0 / gamma)
    m = np.clip((strength - cutoff) / max(1.0 - cutoff, 1e-6), 0.0, 1.0)
    if mask_type == "FLATS":
        m = 1.0 - m
    if invert:
        m = 1.0 - m
    if blur:
        m = _box_blur(m.astype(np.float32), int(blur))
    return m.astype(np.float32)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def apply_dither(rgb, dmap, blend_mode="OVERLAY", strength=0.25, saturation=0.5,
                 use_gray=False, mask=None):
    """Blend the threshold map into the pixelated RGB image.

    rgb: (h, w, 3) float 0..1. dmap: (h, w, 3) float 0..1. mask: (h, w) or None.
    """
    blend_mode = blend_mode.upper()
    if use_gray:
        dmap = np.repeat(dmap[..., :1], 3, axis=-1)
    if saturation < 1.0:
        lum = _luma(dmap)[..., None]
        dmap = np.clip(lum + (dmap - lum) * saturation, 0.0, 1.0)

    linear = blend_mode.endswith("LINEAR")
    base_mode = blend_mode.replace("_LINEAR", "")
    fn = blend_soft_light if base_mode == "SOFT_LIGHT" else blend_overlay

    base = rgb
    if linear:
        base = srgb_to_linear(rgb)
        blended = fn(base, dmap)
        m = strength if mask is None else strength * mask
        out = base + (blended - base) * np.asarray(m)[..., None]
        out = linear_to_srgb(np.clip(out, 0.0, 1.0))
    else:
        blended = fn(base, dmap)
        m = strength if mask is None else strength * mask
        out = base + (blended - base) * np.asarray(m)[..., None]
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _two_nearest(values, palette, space="RGB", chunk=16384):
    """Return nearest and second-nearest palette entries for image colors."""
    values = np.asarray(values, dtype=np.float32).reshape(-1, 3)
    palette = np.asarray(palette, dtype=np.float32)[:, :3]
    if palette.shape[0] < 2:
        raise ValueError("palette-aware dithering requires at least two colors")
    points = to_space(values, space)
    pal_points = to_space(palette, space)
    first = np.empty(points.shape[0], dtype=np.int64)
    second = np.empty(points.shape[0], dtype=np.int64)
    first_d = np.empty(points.shape[0], dtype=np.float32)
    second_d = np.empty(points.shape[0], dtype=np.float32)
    for start in range(0, points.shape[0], chunk):
        stop = min(start + chunk, points.shape[0])
        d = ((points[start:stop, None, :] - pal_points[None, :, :]) ** 2).sum(axis=-1)
        order = np.argpartition(d, 1, axis=1)[:, :2]
        d2 = np.take_along_axis(d, order, axis=1)
        swap = d2[:, 1] < d2[:, 0]
        i0 = np.where(swap, order[:, 1], order[:, 0])
        i1 = np.where(swap, order[:, 0], order[:, 1])
        first[start:stop] = i0
        second[start:stop] = i1
        first_d[start:stop] = np.where(swap, d2[:, 1], d2[:, 0])
        second_d[start:stop] = np.where(swap, d2[:, 0], d2[:, 1])
    return first, second, first_d, second_d


def palette_threshold_dither(rgb, palette, dmap, apply_space="CIELAB", strength=1.0,
                             contrast=1.0, invert=False, mask=None):
    """Dither between the two nearest palette colors using a threshold map.

    The nearest/second-nearest ratio is computed in ``apply_space``.  A
    centered threshold map chooses the second color only near a palette
    boundary, which preserves the palette exactly while producing ordered or
    noisy tone ramps.  This is a clean-room reconstruction of Pixel Composer's
    palette-aware threshold node, not a bit-identical port of its shader.
    """
    rgb = np.asarray(rgb, dtype=np.float32)
    palette = np.asarray(palette, dtype=np.float32)[:, :3]
    dmap = np.asarray(dmap, dtype=np.float32)
    if dmap.ndim == 3:
        dmap = _luma(dmap)
    if dmap.shape != rgb.shape[:2]:
        raise ValueError("palette dither map must match the image dimensions")
    first, second, d1, d2 = _two_nearest(rgb, palette, apply_space)
    ratio = d1 / np.maximum(d1 + d2, 1e-12)
    threshold = 0.5 + (dmap.reshape(-1) - 0.5) * float(max(contrast, 0.0))
    amount = float(np.clip(strength, 0.0, 1.0))
    # strength 0 means only the nearest palette color; strength 1 uses the map.
    threshold = 0.5 + (threshold - 0.5) * amount
    if invert:
        threshold = 1.0 - threshold
    choose_second = ratio > np.clip(threshold, 0.0, 1.0)
    first_colors = palette[first]
    second_colors = palette[second]
    out = np.where(choose_second[:, None], second_colors, first_colors).reshape(rgb.shape)
    if mask is not None:
        mask = np.clip(np.asarray(mask, dtype=np.float32), 0.0, 1.0).reshape(-1, 1)
        nearest = first_colors.reshape(rgb.shape)
        out = nearest.reshape(-1, 3) * (1.0 - mask) + out.reshape(-1, 3) * mask
        out = out.reshape(rgb.shape)
    return np.clip(out, 0.0, 1.0).astype(np.float32)
