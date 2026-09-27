"""Sprite sheets: native-resolution frames packed into one atlas image.

PixelatorPlus-native stage for game export (no Substance spec counterpart).
The packing options adapt ideas from the Pixel Composer research audit (its
render-sprite-sheet node: horizontal/vertical/grid packing, columns, spacing,
padding, and atlas data) in a clean-room NumPy implementation.

Frames here are **top-down** ``(h, w, 4)`` float32 RGBA arrays (row 0 is the
top, as in image files and atlas JSON).  Blender image buffers are bottom-up;
callers flip them on the way in and out.  The atlas description follows the
widely read TexturePacker / Aseprite "JSON array" layout, so Godot, Phaser,
PixiJS, and similar importers can slice the sheet.
"""

import math

import numpy as np

from .pixelate import downscale_nearest


LAYOUTS = ("GRID", "ROW", "COLUMN")


def native_frame(image, grid_size, scale=1):
    """Collapse a pipeline result to one pixel per cell, then upscale by ``scale``.

    ``image`` is the full-resolution pipeline output, ``grid_size`` its
    ``(gw, gh)``.  Cells are sampled at their centers, which is exact for
    pixelated output.  ``scale`` is an integer nearest-neighbor factor.
    """
    gw, gh = grid_size
    cells = downscale_nearest(np.asarray(image, dtype=np.float32), gw, gh)
    scale = max(1, int(scale))
    if scale > 1:
        cells = np.repeat(np.repeat(cells, scale, axis=0), scale, axis=1)
    return cells


def is_empty(frame):
    """True when a frame has no visible pixel."""
    return not np.any(np.asarray(frame)[..., 3] > 1e-6)


def union_bounds(frames):
    """``(x, y, w, h)`` enclosing every visible pixel of every frame, or ``None``.

    One shared rectangle keeps an animation aligned after trimming.
    """
    visible = None
    for frame in frames:
        mask = np.asarray(frame)[..., 3] > 1e-6
        visible = mask if visible is None else visible | mask
    if visible is None or not visible.any():
        return None
    rows = np.flatnonzero(visible.any(axis=1))
    cols = np.flatnonzero(visible.any(axis=0))
    return int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)


def grid_shape(count, layout="GRID", columns=0):
    """``(columns, rows)`` for ``count`` frames; ``columns=0`` picks a near-square grid."""
    layout = str(layout or "GRID").upper()
    if layout not in LAYOUTS:
        raise ValueError(f"unknown sprite sheet layout {layout!r}")
    count = max(1, int(count))
    if layout == "ROW":
        return count, 1
    if layout == "COLUMN":
        return 1, count
    columns = int(columns) if int(columns) > 0 else math.ceil(math.sqrt(count))
    columns = min(columns, count)
    return columns, math.ceil(count / columns)


def pack_frames(frames, layout="GRID", columns=0, spacing=0, padding=0):
    """Pack equally sized frames into one RGBA sheet.

    ``spacing`` separates neighboring frames and ``padding`` surrounds the
    whole sheet, both in pixels and fully transparent.  Returns
    ``(sheet, rects)`` with top-down ``(x, y, w, h)`` rectangles in frame
    order.
    """
    frames = [np.asarray(frame, dtype=np.float32) for frame in frames]
    if not frames:
        raise ValueError("a sprite sheet needs at least one frame")
    fh, fw = frames[0].shape[:2]
    if any(frame.shape != frames[0].shape for frame in frames):
        raise ValueError("sprite sheet frames must share one size")
    spacing, padding = max(0, int(spacing)), max(0, int(padding))
    cols, rows = grid_shape(len(frames), layout, columns)
    width = 2 * padding + cols * fw + (cols - 1) * spacing
    height = 2 * padding + rows * fh + (rows - 1) * spacing
    sheet = np.zeros((height, width, 4), dtype=np.float32)
    rects = []
    for index, frame in enumerate(frames):
        col, row = index % cols, index // cols
        x = padding + col * (fw + spacing)
        y = padding + row * (fh + spacing)
        sheet[y:y + fh, x:x + fw] = frame
        rects.append((x, y, fw, fh))
    return sheet, rects


def atlas_json(rects, frame_numbers, sheet_size, source_size, image_name,
               duration_ms, trim=None, name="frame", palette=None):
    """Describe a packed sheet as a TexturePacker / Aseprite JSON-array atlas.

    ``trim`` is the ``(x, y, w, h)`` crop taken from every ``source_size``
    frame, or ``None``.  ``palette`` (``(K, 3)`` 0..1) is recorded as hex
    strings under ``meta`` when the sheet shares one palette.
    """
    source_w, source_h = source_size
    frames = []
    for (x, y, w, h), number in zip(rects, frame_numbers):
        offset_x, offset_y = (trim[0], trim[1]) if trim else (0, 0)
        frames.append({
            "filename": f"{name}_{int(number):04d}",
            "frame": {"x": x, "y": y, "w": w, "h": h},
            "rotated": False,
            "trimmed": bool(trim),
            "spriteSourceSize": {"x": offset_x, "y": offset_y, "w": w, "h": h},
            "sourceSize": {"w": source_w, "h": source_h},
            "duration": int(round(duration_ms)),
        })
    meta = {
        "app": "PixelatorPlus for Blender",
        "image": image_name,
        "format": "RGBA8888",
        "size": {"w": int(sheet_size[0]), "h": int(sheet_size[1])},
        "scale": "1",
    }
    if palette is not None:
        colors = np.clip(np.rint(np.asarray(palette, dtype=np.float32)[:, :3] * 255.0), 0, 255)
        meta["palette"] = ["#%02x%02x%02x" % tuple(int(c) for c in color) for color in colors]
    return {"frames": frames, "meta": meta}


def build_sheet(frames, frame_numbers, layout="GRID", columns=0, spacing=0, padding=0,
                trim=False, skip_empty=False):
    """Pack native frames with optional empty-frame skipping and shared trimming.

    Returns ``(sheet, rects, kept_numbers, trim_rect)``; ``trim_rect`` is the
    crop applied to every frame, or ``None``.
    """
    pairs = list(zip(frames, frame_numbers))
    if skip_empty:
        pairs = [(frame, number) for frame, number in pairs if not is_empty(frame)]
    if not pairs:
        raise ValueError("every frame is empty; nothing to pack")
    frames = [frame for frame, _number in pairs]
    numbers = [number for _frame, number in pairs]
    trim_rect = union_bounds(frames) if trim else None
    if trim_rect is not None:
        x, y, w, h = trim_rect
        frames = [frame[y:y + h, x:x + w] for frame in frames]
    sheet, rects = pack_frames(frames, layout, columns, spacing, padding)
    return sheet, rects, numbers, trim_rect
