"""Sprite stage: stray-pixel cleanup and silhouette outlines on the pixel grid.

PixelatorPlus-native stage (no Substance spec counterpart).  The outline idea
comes from the Pixel Composer research audit (its outline node); this is a
clean-room NumPy implementation aimed at the Blender workflow of rendering a
3D model and turning it into a game sprite.

Both operations work on the pixel-cell grid, not on full-resolution pixels:
each cell is represented by its center sample (the same sampling as
``pixelate.downscale_nearest``).  Only cells an operation changes are written
back, as whole cells, so untouched cells keep any full-resolution dither
detail.  Opacity is binary per cell (``alpha >= alpha_threshold``); outlines
follow transparency, so an image without transparent areas has no silhouette.

Arrays follow the core convention: RGB ``(h, w, 3)`` and alpha ``(h, w, 1)``
float32 in 0..1.
"""

import numpy as np

from .pixelate import downscale_nearest, upscale_nearest
from .quantize import palette_snap_fn


OUTLINE_MODES = ("NONE", "OUTSIDE", "INSIDE")
OUTLINE_COLOR_MODES = ("SELECTIVE", "DARKEST", "CUSTOM")

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
# Orthogonal neighbors first; the diagonal offsets are used for corners.
_ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))
_DIAGONAL = ((-1, -1), (-1, 1), (1, -1), (1, 1))
_COLOR_TOLERANCE = 1e-4


def _shift(arr, dy, dx, fill):
    """Return ``arr`` shifted so ``out[y, x] == arr[y + dy, x + dx]``."""
    out = np.full_like(arr, fill)
    h, w = arr.shape[:2]
    ys, yd = (slice(dy, h), slice(0, h - dy)) if dy >= 0 else (slice(0, h + dy), slice(-dy, h))
    xs, xd = (slice(dx, w), slice(0, w - dx)) if dx >= 0 else (slice(0, w + dx), slice(-dx, w))
    out[yd, xd] = arr[ys, xs]
    return out


def _cell_key(rgb, opaque):
    """RGBA comparison key where every transparent cell compares equal."""
    key = np.concatenate([rgb, opaque[..., None].astype(np.float32)], axis=-1)
    key[~opaque] = 0.0
    return key


def remove_stray_cells(rgb, opaque, min_agreement=3):
    """Replace isolated cells with the color their neighbors agree on.

    A cell is stray when it matches none of its orthogonal neighbors while at
    least ``min_agreement`` (2..4) of those neighbors share one color.  It then
    takes that color, including transparency: a lone opaque speck in empty
    space disappears and a one-cell hole inside a sprite is filled.  Cells on
    one-cell-wide lines match their line neighbors, so lines survive.

    ``rgb`` is ``(gh, gw, 3)`` and ``opaque`` ``(gh, gw)`` bool; returns new
    ``(rgb, opaque, changed)`` arrays.
    """
    min_agreement = int(np.clip(min_agreement, 2, 4))
    key = _cell_key(rgb, opaque)
    # Out-of-grid neighbors are NaN, so they never match or vote.
    neighbors = [_shift(key, dy, dx, np.nan) for dy, dx in _ORTHOGONAL]

    def same(a, b):
        return np.all(np.abs(a - b) <= _COLOR_TOLERANCE, axis=-1)

    matches_any = np.zeros(opaque.shape, dtype=bool)
    best_votes = np.zeros(opaque.shape, dtype=np.int32)
    best_index = np.zeros(opaque.shape, dtype=np.int32)
    for i, candidate in enumerate(neighbors):
        matches_any |= same(key, candidate)
        votes = sum(same(candidate, other).astype(np.int32) for other in neighbors)
        better = votes > best_votes
        best_votes = np.where(better, votes, best_votes)
        best_index = np.where(better, i, best_index)

    changed = ~matches_any & (best_votes >= min_agreement)
    stacked = np.stack(neighbors, axis=0)
    chosen = np.take_along_axis(stacked, best_index[None, ..., None], axis=0)[0]
    new_rgb = np.where(changed[..., None], chosen[..., :3], rgb)
    new_opaque = np.where(changed, chosen[..., 3] > 0.5, opaque)
    return new_rgb.astype(np.float32), new_opaque, changed


def _dilate(mask, corners):
    """True where any orthogonal (and optionally diagonal) neighbor is set."""
    offsets = _ORTHOGONAL + (_DIAGONAL if corners else ())
    grown = np.zeros_like(mask)
    for dy, dx in offsets:
        grown |= _shift(mask, dy, dx, False)
    return grown


def _snap(colors, palette, apply_space):
    """Nearest palette color for ``(N, 3)`` colors (identity without a palette)."""
    if palette is None or len(colors) == 0:
        return colors
    return palette_snap_fn(palette, apply_space)(colors)


def outline_cells(rgb, opaque, mode="OUTSIDE", color_mode="SELECTIVE",
                  color=(0.05, 0.05, 0.08), darken=0.5, corners=False,
                  palette=None, apply_space="RGB"):
    """Draw a one-cell outline around the opaque silhouette.

    ``OUTSIDE`` fills transparent cells touching the silhouette; ``INSIDE``
    recolors the silhouette's own boundary cells.  The grid edge is not
    treated as transparency.  Color modes:

    - ``SELECTIVE``: the classic pixel-art "sel-out": the adjacent sprite
      color (the cell's own color for INSIDE) darkened by ``darken``.
    - ``DARKEST``: the darkest palette entry.
    - ``CUSTOM``: ``color`` (display RGB).

    With a finite ``palette``, SELECTIVE and CUSTOM colors snap to it so the
    result stays palette-exact.  Returns new ``(rgb, opaque, changed)``.
    """
    mode = str(mode or "NONE").upper()
    color_mode = str(color_mode or "SELECTIVE").upper()
    if mode not in OUTLINE_MODES:
        raise ValueError(f"unknown outline mode {mode!r}")
    if color_mode not in OUTLINE_COLOR_MODES:
        raise ValueError(f"unknown outline color mode {color_mode!r}")
    if mode == "NONE":
        return rgb, opaque, np.zeros(opaque.shape, dtype=bool)

    if mode == "OUTSIDE":
        target = ~opaque & _dilate(opaque, corners)
    else:
        # _shift fills with False, so the grid edge never counts as empty.
        target = opaque & _dilate(~opaque, corners)
    if palette is not None:
        palette = np.asarray(palette, dtype=np.float32)[:, :3]

    if color_mode == "DARKEST" and palette is not None:
        ink = np.broadcast_to(palette[np.argmin(palette @ _LUMA)], (int(target.sum()), 3))
    elif color_mode == "SELECTIVE":
        if mode == "OUTSIDE":
            # Average the opaque orthogonal neighbors (diagonals too when a
            # cell only touches the sprite at a corner).
            base = _neighbor_mean(rgb, opaque, _ORTHOGONAL)
            corner_only = np.isnan(base[..., 0])
            if corners:
                base = np.where(corner_only[..., None],
                                _neighbor_mean(rgb, opaque, _DIAGONAL), base)
            base = base[target]
        else:
            base = rgb[target]
        ink = _snap(base * np.float32(1.0 - np.clip(darken, 0.0, 1.0)), palette, apply_space)
    else:  # CUSTOM, or DARKEST without a palette
        custom = np.clip(np.asarray(color, dtype=np.float32)[:3], 0.0, 1.0)[None, :]
        ink = np.broadcast_to(_snap(custom, palette, apply_space), (int(target.sum()), 3))

    new_rgb = rgb.copy()
    new_rgb[target] = ink
    return new_rgb, opaque | target, target


def _neighbor_mean(rgb, opaque, offsets):
    """Mean color of opaque neighbors at ``offsets`` (NaN where there are none)."""
    total = np.zeros(rgb.shape, dtype=np.float32)
    count = np.zeros(opaque.shape, dtype=np.float32)
    for dy, dx in offsets:
        neighbor_opaque = _shift(opaque, dy, dx, False)
        total += np.where(neighbor_opaque[..., None], _shift(rgb, dy, dx, 0.0), 0.0)
        count += neighbor_opaque
    with np.errstate(invalid="ignore", divide="ignore"):
        return total / count[..., None]


def apply_sprite_stage(rgb, alpha, gw, gh, params, palette=None):
    """Run cleanup then outline on the cell grid of a full-resolution image.

    ``rgb`` is ``(h, w, 3)``, ``alpha`` ``(h, w, 1)``.  Returns updated
    ``(rgb, alpha)``; cells no operation touched keep their full-resolution
    pixels.  Changed cells become uniform, fully opaque or fully transparent.
    """
    rgb = np.asarray(rgb, dtype=np.float32)
    alpha = np.asarray(alpha, dtype=np.float32)
    h, w = rgb.shape[:2]
    threshold = float(params.get("sprite_alpha_threshold", 0.5))
    cells_rgb = downscale_nearest(rgb, gw, gh)
    cells_opaque = downscale_nearest(alpha, gw, gh)[..., 0] >= threshold
    changed = np.zeros(cells_opaque.shape, dtype=bool)

    if params.get("sprite_cleanup", False):
        cells_rgb, cells_opaque, cleaned = remove_stray_cells(
            cells_rgb, cells_opaque, params.get("sprite_cleanup_agreement", 3)
        )
        changed |= cleaned
    outline_mode = params.get("sprite_outline", "NONE")
    if outline_mode != "NONE":
        cells_rgb, cells_opaque, outlined = outline_cells(
            cells_rgb, cells_opaque, outline_mode,
            params.get("sprite_outline_color_mode", "SELECTIVE"),
            params.get("sprite_outline_color", (0.05, 0.05, 0.08)),
            params.get("sprite_outline_darken", 0.5),
            params.get("sprite_outline_corners", False),
            palette,
            params.get("apply_palette_mode", "RGB"),
        )
        changed |= outlined
    if not changed.any():
        return rgb, alpha

    full_changed = upscale_nearest(changed, w, h)
    full_rgb = upscale_nearest(cells_rgb, w, h)
    full_alpha = upscale_nearest(cells_opaque.astype(np.float32), w, h)[..., None]
    rgb = np.where(full_changed[..., None], full_rgb, rgb).astype(np.float32)
    alpha = np.where(full_changed[..., None], full_alpha, alpha).astype(np.float32)
    return rgb, alpha
