"""Small display-finishing stages for the incremental PixelatorPlus workflow.

These effects are post-process reconstructions inspired by Pixel Composer's
level, grain, interlace, vignette, and chromatic-aberration nodes.  They are
deterministic, NumPy-only, and intentionally applied after palette work so
artists can choose whether to preserve an indexed palette look.
"""

import numpy as np

from .stages import apply_rgb_effect


def adjust_color(rgb, brightness=0.0, contrast=1.0, exposure=0.0, saturation=1.0):
    """Apply display-space brightness, contrast, exposure, and saturation."""
    rgb = np.asarray(rgb, dtype=np.float32)
    out = np.clip(rgb, 0.0, 1.0) * (2.0 ** float(exposure))
    out = (out - 0.5) * float(contrast) + 0.5 + float(brightness)
    luma = out @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    out = luma[..., None] + (out - luma[..., None]) * float(saturation)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def add_grain(rgb, amount=0.0, brightness=0.0, saturation=1.0, seed=0):
    """Add deterministic film grain; amount is normalized to a display range."""
    rgb = np.asarray(rgb, dtype=np.float32)
    amount = float(np.clip(amount, 0.0, 1.0))
    if amount <= 0.0:
        return rgb.copy()
    rng = np.random.default_rng(int(seed))
    noise = rng.normal(0.0, amount * 0.18, rgb.shape[:2] + (3,)).astype(np.float32)
    luma = noise.mean(axis=-1, keepdims=True)
    noise = luma * (1.0 - float(np.clip(saturation, 0.0, 1.0))) + noise * float(np.clip(saturation, 0.0, 1.0))
    noise += float(brightness) * amount * 0.1
    return np.clip(rgb + noise, 0.0, 1.0).astype(np.float32)


def add_scanlines(rgb, strength=0.0, size=2, axis="Y", invert=False):
    """Modulate alternating rows or columns with a scanline pattern."""
    rgb = np.asarray(rgb, dtype=np.float32)
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0.0:
        return rgb.copy()
    h, w = rgb.shape[:2]
    period = max(2, int(size))
    coord = np.arange(h if str(axis).upper() == "Y" else w)
    line = ((coord % period) == 0).astype(np.float32)
    if invert:
        line = 1.0 - line
    factor = 1.0 - line * strength
    if str(axis).upper() == "Y":
        factor = factor[:, None, None]
    else:
        factor = factor[None, :, None]
    return np.clip(rgb * factor, 0.0, 1.0).astype(np.float32)


def add_vignette(rgb, strength=0.0, roundness=1.0):
    """Darken the image toward its corners using a normalized radial mask."""
    rgb = np.asarray(rgb, dtype=np.float32)
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0.0:
        return rgb.copy()
    h, w = rgb.shape[:2]
    y = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    x = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    radius = np.sqrt(x * x + y * y) / np.sqrt(2.0)
    falloff = np.clip(radius, 0.0, 1.0) ** max(float(roundness), 0.1)
    return np.clip(rgb * (1.0 - falloff[..., None] * strength), 0.0, 1.0).astype(np.float32)


def add_chromatic_aberration(rgb, amount=0.0):
    """Shift red and blue channels by a small edge-clamped pixel offset."""
    rgb = np.asarray(rgb, dtype=np.float32)
    amount = float(np.clip(amount, 0.0, 1.0))
    if amount <= 0.0:
        return rgb.copy()
    h, w = rgb.shape[:2]
    offset = max(1, int(round(amount * max(h, w) * 0.02)))
    padded = np.pad(rgb, ((0, 0), (offset, offset), (0, 0)), mode="edge")
    out = rgb.copy()
    out[..., 0] = padded[:, :w, 0]
    out[..., 2] = padded[:, offset * 2:offset * 2 + w, 2]
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def apply_finish(image, settings, seed=0, mask=None):
    """Apply the configured finish stack to an RGB/RGBA image."""
    image = np.asarray(image, dtype=np.float32)
    rgb = image[..., :3]
    effect = adjust_color(
        rgb,
        settings.get("finish_brightness", 0.0),
        settings.get("finish_contrast", 1.0),
        settings.get("finish_exposure", 0.0),
        settings.get("finish_saturation", 1.0),
    )
    effect = add_grain(
        effect,
        settings.get("finish_grain", 0.0),
        settings.get("finish_grain_brightness", 0.0),
        settings.get("finish_grain_saturation", 1.0),
        seed,
    )
    effect = add_scanlines(
        effect,
        settings.get("finish_scanline_strength", 0.0),
        settings.get("finish_scanline_size", 2),
        settings.get("finish_scanline_axis", "Y"),
        settings.get("finish_scanline_invert", False),
    )
    effect = add_vignette(
        effect,
        settings.get("finish_vignette_strength", 0.0),
        settings.get("finish_vignette_roundness", 1.0),
    )
    effect = add_chromatic_aberration(effect, settings.get("finish_chromatic_aberration", 0.0))
    if image.shape[2] > 3:
        effect = np.concatenate([effect, image[..., 3:4]], axis=-1)
    return apply_rgb_effect(
        image,
        effect[..., :3],
        mask=mask,
        mix=settings.get("finish_mask_mix", 1.0),
        channels=settings.get("finish_channel_mask", "RGB"),
    )
