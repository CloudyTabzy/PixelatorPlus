"""Tone Bands: cel-style banded lighting.

PixelatorPlus-native stage (no Substance spec counterpart).  Lightness is
quantized into a few flat tones, the way pixel artists shade with a handful
of bands instead of smooth gradients.  Work happens in Oklab, so the bands
are perceptually even and hue is untouched by the lightness change.

Two things go beyond a 2D posterize, both fed by Blender renders:

- **Per part** (an ID map): every object or material gets its own full set of
  bands across its own lightness range, instead of dark parts collapsing into
  one band and light parts into another.
- **Light map** ranking: bands follow a rendered, texture-free lighting pass
  rather than the image's own lightness, so dark texture detail is not
  mistaken for shadow.

Arrays follow the core convention: ``(h, w, 3)`` RGB and ``(h, w, 1)`` alpha
float32 in 0..1.
"""

import numpy as np

from .colorspace import from_space, to_space
from .stages import resize_mask


BAND_SOURCES = ("LIGHTNESS", "LIGHT_MAP")
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
# Percentiles that bound a region's range, ignoring a few outlier pixels.
_RANGE_PERCENTILES = (2.0, 98.0)
# Flatten averages color only within one hue family: hues separated by a gap
# wider than this (on the color wheel), or near-grays, never blend.
_HUE_GAP_DEGREES = 30.0
# Near-gray is judged by saturation relative to lightness (chroma / L):
# dark shades of a color have little absolute chroma but keep their ratio
# (about 0.07 and up), while slightly noisy grays stay near 0.01.
_NEUTRAL_SATURATION = 0.03


def _hue_families(lab):
    """Group ``(N, 3)`` Oklab colors into hue families (-1 = near-gray).

    Hues are sorted around the color wheel and split wherever neighbors are
    more than ``_HUE_GAP_DEGREES`` apart, so a continuous drift (the shades of
    one color) stays together while distinct colors separate.
    """
    families = np.full(lab.shape[0], -1, dtype=np.int64)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    chromatic = np.flatnonzero(chroma >= _NEUTRAL_SATURATION * np.maximum(lab[:, 0], 0.05))
    if chromatic.size == 0:
        return families
    hue = np.degrees(np.arctan2(lab[chromatic, 2], lab[chromatic, 1])) % 360.0
    order = np.argsort(hue, kind="stable")
    sorted_hue = hue[order]
    gaps = np.diff(np.concatenate([sorted_hue, sorted_hue[:1] + 360.0]))
    cuts = np.flatnonzero(gaps > _HUE_GAP_DEGREES)
    if cuts.size == 0:
        families[chromatic] = 0
        return families
    # Start right after a cut so the wrap-around gap separates families.
    start = (cuts[-1] + 1) % order.size
    rolled_gaps = np.roll(gaps, -start)
    family = np.concatenate([[0], np.cumsum(rolled_gaps[:-1] > _HUE_GAP_DEGREES)])
    families[chromatic[np.roll(order, -start)]] = family
    return families


def _region_labels(shape, id_map):
    """One integer label per pixel, or ``None`` when no ID map is used."""
    h, w = shape[:2]
    if id_map is None:
        return None
    ids = np.asarray(id_map, dtype=np.float32)
    if ids.ndim != 3 or ids.shape[-1] < 3:
        raise ValueError("ID map must be an RGB or RGBA image")
    if ids.shape[0] == 0 or ids.shape[1] == 0:
        raise ValueError("ID map has no pixel data")
    if not np.isfinite(ids[..., :4]).all():
        raise ValueError("ID map must contain finite pixel values")
    ys = np.minimum((np.arange(h) * ids.shape[0] / max(h, 1)).astype(np.int64), ids.shape[0] - 1)
    xs = np.minimum((np.arange(w) * ids.shape[1] / max(w, 1)).astype(np.int64), ids.shape[1] - 1)
    ids = ids[np.ix_(ys, xs)]
    codes = np.rint(np.clip(ids[..., :3], 0.0, 1.0) * 255.0).astype(np.int32)
    labels = (codes[..., 0] << 16) | (codes[..., 1] << 8) | codes[..., 2]
    if ids.shape[-1] > 3:
        labels = np.where(ids[..., 3] >= 0.5, labels, -1)  # -1: no part
    return labels.reshape(-1)


def _region_members(labels, visible):
    """Yield visible pixel indices grouped by region without repeated full scans."""
    indices = np.flatnonzero(visible)
    if indices.size == 0:
        return
    if labels is None:
        yield indices
        return

    visible_labels = labels[indices]
    regions, group_ids = np.unique(visible_labels, return_inverse=True)
    # For a small number of parts, direct masks avoid sorting a full image.
    # With many parts, sort the compact inverse labels once instead of
    # rescanning every pixel for every object/material.
    scan_limit = max(8, int(np.log2(indices.size)))
    if regions.size <= scan_limit:
        for group_id in range(regions.size):
            yield indices[group_ids == group_id]
        return

    order = np.argsort(group_ids, kind="stable")
    sorted_groups = group_ids[order]
    boundaries = np.flatnonzero(np.diff(sorted_groups)) + 1
    del sorted_groups, group_ids, visible_labels
    start = 0
    for end in boundaries:
        yield indices[order[start:end]]
        start = end
    yield indices[order[start:]]


def tone_bands(rgb, alpha, bands=3, light=None, id_map=None, flatten=True):
    """Quantize lightness into ``bands`` flat tones per region.

    ``light`` is an optional ``(h, w)``/``(h, w, C)`` light map (any size) that
    ranks pixels into bands instead of their own lightness.  ``id_map`` splits
    the image into regions that each get the full set of bands.  Band tones
    spread evenly across each region's own lightness range.  With
    ``flatten`` each band takes one mean color per hue family (hues split at
    gaps wider than 30 degrees, plus near-grays), a pure cel look that never
    blends different colors together; without it pixels keep their own color
    and change only in lightness.  Fully transparent pixels are left unchanged.
    """
    rgb = np.asarray(rgb, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[-1] != 3:
        raise ValueError("Tone Bands expects an RGB image with shape (h, w, 3)")
    h, w = rgb.shape[:2]
    alpha = np.asarray(alpha, dtype=np.float32)
    if alpha.ndim == 3 and alpha.shape[-1] == 1:
        alpha = alpha[..., 0]
    if alpha.shape != (h, w):
        raise ValueError("Tone Bands alpha must match the RGB image dimensions")
    if not np.isfinite(rgb).all():
        raise ValueError("Tone Bands RGB values must be finite")
    if not np.isfinite(alpha).all():
        raise ValueError("Tone Bands alpha values must be finite")
    if h == 0 or w == 0:
        return rgb.copy()

    bands = int(np.clip(bands, 2, 16))
    lab = to_space(rgb.reshape(-1, 3), "OKLAB").astype(np.float32)
    lightness = lab[:, 0]
    if light is None:
        rank = lightness
    else:
        light = np.asarray(light, dtype=np.float32)
        light_alpha = None
        if light.ndim == 3 and light.shape[-1] == 1:
            light = light[..., 0]
        elif light.ndim == 3 and light.shape[-1] >= 3:
            light_alpha = light[..., 3] if light.shape[-1] >= 4 else None
            light = light[..., :3] @ _LUMA
        else:
            light_alpha = None
        if light.ndim != 2 or light.shape[0] == 0 or light.shape[1] == 0:
            raise ValueError("Light map must be a non-empty grayscale, RGB, or RGBA image")
        if not np.isfinite(light).all():
            raise ValueError("Light map must contain finite pixel values")
        rank = resize_mask(light, (h, w)).reshape(-1)
        if light_alpha is not None:
            if not np.isfinite(light_alpha).all():
                raise ValueError("Light map alpha values must be finite")
            map_visible = resize_mask(light_alpha, (h, w)).reshape(-1) > 1e-6
            # A visible input pixel with no corresponding map sample should
            # rank by its own lightness, not by the map's transparent black.
            rank = np.where(map_visible, rank, lightness)
    visible = alpha.reshape(-1) > 1e-6
    if not visible.any():
        return rgb.copy()
    labels = _region_labels((h, w), id_map)
    for members in _region_members(labels, visible):
        order = rank[members]
        low, high = np.percentile(order, _RANGE_PERCENTILES)
        if high - low < 1e-6:
            band = np.full(members.shape, bands // 2)
        else:
            band = np.clip(((order - low) / (high - low) * bands).astype(np.int64), 0, bands - 1)
        dark, bright = np.percentile(lightness[members], _RANGE_PERCENTILES)
        if flatten:
            for index in np.unique(band):
                in_band = members[band == index]
                families = _hue_families(lab[in_band])
                for family in np.unique(families):
                    chosen = in_band[families == family]
                    lab[chosen, 1:] = lab[chosen, 1:].mean(axis=0)
        # Defer changing lightness until after family grouping, which uses the
        # source Oklab lightness when separating near-neutrals from colors.
        lab[members, 0] = dark + (band + 0.5) / bands * (bright - dark)

    result = rgb.copy()
    rgb_result = result.reshape(h, w, 3)
    lab_image = lab.reshape(h, w, 3)
    visible_image = visible.reshape(h, w)
    # Convert bounded row batches to avoid materializing a second full-size
    # float image when processing large renders.
    for y in range(0, h, 128):
        end = min(y + 128, h)
        block_visible = visible_image[y:end]
        if block_visible.any():
            rgb_block = rgb_result[y:end]
            rgb_block[block_visible] = from_space(lab_image[y:end][block_visible], "OKLAB")
    return result.astype(np.float32, copy=False)
