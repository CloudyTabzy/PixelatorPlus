"""Deterministic posterize/levels processing for the staged pipeline.

This is a Blender-independent reconstruction of the useful part of Pixel
Composer's level/posterize nodes.  It deliberately operates on display RGB
values in the same 0..1 convention as the rest of PixelatorPlus.  The stage
supports full-range, per-image min/max, and robust percentile bounds, with an
optional named ``range_map`` image for local level intensity.
"""

import numpy as np

from .stages import apply_stage_mask, resize_mask


def _channel_bounds(rgb, mode, low, high, percentile_low, percentile_high):
    """Return per-channel lower/upper bounds for an RGB image."""
    mode = str(mode or "FULL").upper()
    if mode == "FULL":
        return (
            np.zeros(3, dtype=np.float32),
            np.ones(3, dtype=np.float32),
        )
    flat = np.asarray(rgb, dtype=np.float32).reshape(-1, 3)
    if flat.shape[0] == 0:
        raise ValueError("posterize cannot process an empty image")
    if mode in ("MIN_MAX", "IMAGE"):
        lo = flat.min(axis=0)
        hi = flat.max(axis=0)
    elif mode in ("PERCENTILE", "ROBUST"):
        p0 = float(np.clip(percentile_low, 0.0, 49.0))
        p1 = float(np.clip(percentile_high, 51.0, 100.0))
        if p1 <= p0:
            raise ValueError("posterize high percentile must exceed low percentile")
        lo, hi = np.percentile(flat, (p0, p1), axis=0).astype(np.float32)
    else:
        raise ValueError(f"unknown posterize range mode {mode!r}")
    # Explicit offsets are useful for matching a Levels workflow while keeping
    # the bounds ordered and within the display range.
    lo = np.clip(lo + float(low), 0.0, 1.0)
    hi = np.clip(hi - (1.0 - float(high)), 0.0, 1.0)
    hi = np.maximum(hi, lo + 1e-6)
    return lo.astype(np.float32), hi.astype(np.float32)


def apply_posterize(
    image,
    levels=8,
    range_mode="FULL",
    range_low=0.0,
    range_high=1.0,
    percentile_low=2.0,
    percentile_high=98.0,
    gamma=1.0,
    mask=None,
    mix=1.0,
    channels="RGB",
    alpha_policy="PRESERVE",
    range_map=None,
):
    """Posterize an RGB/RGBA image and apply it through the stage contract.

    ``levels`` is the number of output steps per channel.  ``gamma`` moves
    the quantization thresholds but does not change the endpoints.  A
    ``range_map`` (or ``mask``) may locally mix the effect with the original;
    its values are normalized to 0..1 and resized with nearest sampling.
    """
    image = np.asarray(image, dtype=np.float32)
    if image.ndim != 3 or image.shape[2] not in (3, 4):
        raise ValueError("posterize image must have shape (h,w,3|4)")
    levels = int(np.clip(levels, 2, 256))
    gamma = max(float(gamma), 1e-4)
    rgb = np.clip(image[..., :3], 0.0, 1.0)
    lo, hi = _channel_bounds(
        rgb, range_mode, range_low, range_high, percentile_low, percentile_high
    )
    normalized = np.clip((rgb - lo) / np.maximum(hi - lo, 1e-6), 0.0, 1.0)
    encoded = normalized ** gamma
    quantized = np.rint(encoded * (levels - 1.0)) / (levels - 1.0)
    decoded = np.clip(quantized ** (1.0 / gamma), 0.0, 1.0)
    effect = decoded * (hi - lo) + lo
    # A range map controls local effect amount, not the bounds themselves. It
    # is intentionally small and predictable instead of becoming a second
    # arbitrary shader input.
    blend_mask = mask
    if range_map is not None:
        blend_mask = resize_mask(range_map, image.shape)
        if mask is not None:
            blend_mask *= resize_mask(mask, image.shape)
    effect = effect.astype(np.float32)
    if image.shape[2] == 4:
        effect_alpha = image[..., 3:4].copy()
        if str(alpha_policy or "PRESERVE").upper() == "QUANTIZE":
            effect_alpha = np.rint(np.clip(effect_alpha, 0.0, 1.0) * (levels - 1.0)) / (levels - 1.0)
        effect = np.concatenate([effect, effect_alpha.astype(np.float32)], axis=-1)
    return apply_stage_mask(
        image,
        effect,
        mask=blend_mask,
        mix=mix,
        channels=channels,
        alpha_policy=alpha_policy,
    )
