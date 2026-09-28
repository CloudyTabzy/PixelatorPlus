"""Shared pure-NumPy stage contracts and mask application helpers.

Pixel Composer gives most of its image nodes the same mask/mix/channel shape.
PixelatorPlus uses this small contract for new stages while retaining the
existing v2-specific dither-mask implementation.  It is intentionally free of
Blender imports and keeps alpha policy explicit.
"""

import numpy as np


STAGE_CHANNELS = ("RGB", "R", "G", "B", "RG", "RB", "GB")
ALPHA_POLICIES = ("PRESERVE", "REPLACE", "QUANTIZE")

# Metadata is intentionally plain data: it is useful to the preview layer and
# tests without importing Blender or making the executor depend on a class
# hierarchy.  Cost labels are scheduling hints, not quality changes.
STAGE_SPECS = {
    "pre_adjust": {"cost": "LOW", "draft": True},
    "pixelate": {"cost": "MEDIUM", "draft": True},
    "posterize": {"cost": "LOW", "draft": True},
    "shading": {"cost": "LOW", "draft": True},
    "palette": {"cost": "HIGH", "draft": False},
    "dither": {"cost": "MEDIUM", "draft": True},
    "diffusion": {"cost": "HIGH", "draft": False},
    "quantize": {"cost": "HIGH", "draft": False},
    "sprite": {"cost": "LOW", "draft": True},
    "display_finish": {"cost": "MEDIUM", "draft": True},
}


def stage_spec(stage_type):
    """Return immutable-ish scheduling metadata for a known stage."""
    key = str(stage_type or "").lower()
    if key not in STAGE_SPECS:
        raise ValueError(f"unknown PixelatorPlus stage {stage_type!r}")
    return dict(STAGE_SPECS[key])


def make_context(image, params=None, images=None, seed=0, preview=False):
    """Create the common execution context passed to future stages."""
    return {
        "image": np.asarray(image, dtype=np.float32),
        "params": dict(params or {}),
        "images": dict(images or {}),
        "seed": int(seed),
        "preview": bool(preview),
        "metadata": {},
    }


def resize_mask(mask, shape):
    """Nearest-resize a scalar mask to ``(height, width)``."""
    h, w = shape[:2]
    if mask is None:
        return np.ones((h, w), dtype=np.float32)
    arr = np.asarray(mask, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[..., 0]
    if arr.ndim != 2:
        raise ValueError("stage masks must be 2-D or an image with channels")
    ys = np.minimum((np.arange(h) * arr.shape[0] / max(h, 1)).astype(np.int64), arr.shape[0] - 1)
    xs = np.minimum((np.arange(w) * arr.shape[1] / max(w, 1)).astype(np.int64), arr.shape[1] - 1)
    return np.clip(arr[np.ix_(ys, xs)], 0.0, 1.0).astype(np.float32)


def channel_indices(channels):
    """Return RGB indices selected by a channel-mask identifier."""
    channels = str(channels or "RGB").upper()
    if channels not in STAGE_CHANNELS:
        raise ValueError(f"unknown stage channel mask {channels!r}")
    return tuple(index for index, name in enumerate("RGB") if name in channels)


def apply_stage_mask(base, effect, mask=None, mix=1.0, channels="RGB", alpha_policy="PRESERVE"):
    """Blend an effect into an image using the common stage contract.

    ``base`` and ``effect`` are ``(h,w,3|4)`` arrays.  The selected RGB
    channels are mixed by ``mask * mix``; alpha is preserved by default.
    """
    base = np.asarray(base, dtype=np.float32)
    effect = np.asarray(effect, dtype=np.float32)
    if base.shape[:2] != effect.shape[:2] or base.shape[2] != effect.shape[2]:
        raise ValueError("stage base and effect must have matching shapes")
    out = base.copy()
    blend = resize_mask(mask, base.shape) * float(np.clip(mix, 0.0, 1.0))
    blend = blend[..., None]
    for index in channel_indices(channels):
        out[..., index] = base[..., index] * (1.0 - blend[..., 0]) + effect[..., index] * blend[..., 0]
    policy = str(alpha_policy or "PRESERVE").upper()
    if base.shape[2] > 3 and policy == "REPLACE":
        out[..., 3] = effect[..., 3]
    elif base.shape[2] > 3 and policy == "QUANTIZE":
        out[..., 3] = np.clip(effect[..., 3], 0.0, 1.0)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def apply_rgb_effect(image, effect_rgb, mask=None, mix=1.0, channels="RGB"):
    """Convenience wrapper for a 3-channel effect on an RGBA/RGB image."""
    image = np.asarray(image, dtype=np.float32)
    effect = np.asarray(effect_rgb, dtype=np.float32)
    if image.shape[2] == 4 and effect.shape[2] == 3:
        effect = np.concatenate([effect, image[..., 3:4]], axis=-1)
    return apply_stage_mask(image, effect, mask, mix, channels, "PRESERVE")
