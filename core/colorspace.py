"""Color-space conversions used across the PixelatorPlus pipeline.

All functions are vectorized NumPy ops on float arrays of shape (..., 3) with
values nominally in 0..1 (CIELAB/Oklab outputs use their native ranges:
Lab L in 0..100, a/b roughly -128..127; Oklab L in 0..1, a/b roughly -0.5..0.5).

Formulas are the standard public ones:
  - sRGB EOTF (IEC 61966-2-1)
  - CIELAB via sRGB D65 XYZ (IEC 61966-2-1 / CIE 1976)
  - Oklab (Bjoern Ottosson, 2020)
"""

import numpy as np

# ---------------------------------------------------------------------------
# sRGB <-> linear
# ---------------------------------------------------------------------------

def srgb_to_linear(rgb):
    rgb = np.asarray(rgb, dtype=np.float32)
    return np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        np.power(np.maximum((rgb + 0.055) / 1.055, 0.0), 2.4),
    ).astype(np.float32)


def linear_to_srgb(lin):
    lin = np.asarray(lin, dtype=np.float32)
    return np.where(
        lin <= 0.0031308,
        lin * 12.92,
        1.055 * np.power(np.maximum(lin, 0.0), 1.0 / 2.4) - 0.055,
    ).astype(np.float32)


# ---------------------------------------------------------------------------
# RGB <-> CIELAB (through XYZ, D65)
# ---------------------------------------------------------------------------

_M_RGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ],
    dtype=np.float64,
)
_M_XYZ_TO_RGB = np.linalg.inv(_M_RGB_TO_XYZ)
_D65 = np.array([0.95047, 1.0, 1.08883], dtype=np.float64)
_EPSILON = 216.0 / 24389.0  # 0.008856
_KAPPA = 24389.0 / 27.0     # 903.3


def _f_lab(t):
    return np.where(t > _EPSILON, np.cbrt(t), (_KAPPA * t + 16.0) / 116.0)


def _f_lab_inv(t):
    t3 = t ** 3
    return np.where(t3 > _EPSILON, t3, (116.0 * t - 16.0) / _KAPPA)


def rgb_to_lab(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    xyz = srgb_to_linear(rgb) @ _M_RGB_TO_XYZ.T
    f = _f_lab(xyz / _D65)
    l = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([l, a, b], axis=-1).astype(np.float32)


def lab_to_rgb(lab):
    lab = np.asarray(lab, dtype=np.float64)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    xyz = np.stack([_f_lab_inv(fx), _f_lab_inv(fy), _f_lab_inv(fz)], axis=-1) * _D65
    rgb = linear_to_srgb(xyz @ _M_XYZ_TO_RGB.T)
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# RGB <-> Oklab
# ---------------------------------------------------------------------------

_M1 = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ],
    dtype=np.float64,
)
_M2 = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ],
    dtype=np.float64,
)
_M1_INV = np.linalg.inv(_M1)
_M2_INV = np.linalg.inv(_M2)


def rgb_to_oklab(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    lms = srgb_to_linear(rgb) @ _M1.T
    lms_cbrt = np.cbrt(np.maximum(lms, 0.0))
    lab = lms_cbrt @ _M2.T
    return lab.astype(np.float32)


def oklab_to_rgb(lab):
    lab = np.asarray(lab, dtype=np.float64)
    lms = (lab @ _M2_INV.T) ** 3
    rgb = linear_to_srgb(lms @ _M1_INV.T)
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# Generic dispatch + gamma helpers
# ---------------------------------------------------------------------------

_TO_SPACE = {"RGB": lambda x: np.asarray(x, dtype=np.float32), "CIELAB": rgb_to_lab, "OKLAB": rgb_to_oklab}
_FROM_SPACE = {"RGB": lambda x: np.asarray(x, dtype=np.float32), "CIELAB": lab_to_rgb, "OKLAB": oklab_to_rgb}


def to_space(rgb, space):
    """RGB 0..1 -> target space. `space` in {RGB, CIELAB, OKLAB}."""
    return _TO_SPACE[space](rgb)


def from_space(values, space):
    """Target space -> RGB 0..1 (clipped). `space` in {RGB, CIELAB, OKLAB}."""
    return np.clip(_FROM_SPACE[space](values), 0.0, 1.0).astype(np.float32)


def gamma_apply(rgb, gamma):
    """Pre-warp used by palette generation (x ** (1/gamma)); helps dark range."""
    if gamma == 1.0:
        return np.asarray(rgb, dtype=np.float32)
    return np.power(np.clip(rgb, 0.0, 1.0), 1.0 / gamma).astype(np.float32)


def gamma_remove(rgb, gamma):
    if gamma == 1.0:
        return np.asarray(rgb, dtype=np.float32)
    return np.power(np.clip(rgb, 0.0, 1.0), gamma).astype(np.float32)
