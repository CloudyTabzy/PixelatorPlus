"""Pixelation stage: downscale to a pixel grid and upscale back.

Modes (spec: DownscaleMode):
  - NEAREST        hard blocky pixels (center-sample downscale, nearest upscale)
  - NEAREST_SOFTER area-averaged downscale, nearest upscale (blocky but with
                   averaged colors; reconstruction of PixelatorPlus's softer mode)

Preview filters (spec: FilterPreview) resample the pixel *grid* back to the
output size for viewport preview only (spec warns: do not export with these):
  - NONE / BILINEAR / N64_3POINT (the Nintendo 64's triangular 3-texel filter)
"""

import numpy as np


def compute_grid(w, h, square_count, separate, count_x, count_y):
    """Pixel-grid dimensions (gw, gh) from the Dimensions group parameters.

    Square mode puts `square_count` cells on the shortest axis and scales the
    other proportionally to the image aspect. Separate mode uses exact X/Y
    counts. Counts are clamped to >= 1 and to the source resolution.
    """
    if separate:
        gw, gh = count_x, count_y
    else:
        n = max(1, square_count)
        scale = n / max(1, min(w, h))
        gw = max(1, int(round(w * scale)))
        gh = max(1, int(round(h * scale)))
    return max(1, min(gw, w)), max(1, min(gh, h))


def _nearest_index(n_out, n_in):
    """Output index -> source index for nearest resampling (0.5-centered)."""
    return np.minimum((np.arange(n_out) + 0.5) * n_in / n_out, n_in - 1).astype(np.int64)


def upscale_nearest(grid, w, h):
    """Nearest upscale of a (gh, gw, C) grid to (h, w, C)."""
    gh, gw = grid.shape[:2]
    ys = _nearest_index(h, gh)
    xs = _nearest_index(w, gw)
    return grid[ys][:, xs]


def downscale_nearest(img, gw, gh):
    """Center-sample downscale to (gh, gw, C)."""
    h, w = img.shape[:2]
    ys = _nearest_index(gh, h)
    xs = _nearest_index(gw, w)
    return img[ys][:, xs]


def downscale_area(img, gw, gh):
    """Area-averaged downscale via an integral image (exact box filter)."""
    h, w = img.shape[:2]
    c = img.shape[2] if img.ndim == 3 else 1
    work = img.reshape(h, w, c).astype(np.float64)
    integ = np.zeros((h + 1, w + 1, c), dtype=np.float64)
    integ[1:, 1:] = work.cumsum(axis=0).cumsum(axis=1)

    yb = np.round(np.linspace(0, h, gh + 1)).astype(np.int64)
    xb = np.round(np.linspace(0, w, gw + 1)).astype(np.int64)
    y0, y1 = yb[:-1], yb[1:]
    x0, x1 = xb[:-1], xb[1:]

    # (gh, gw, C) box sums from the integral image
    a = integ[np.ix_(y1, x1)]
    b = integ[np.ix_(y0, x1)]
    cc = integ[np.ix_(y1, x0)]
    d = integ[np.ix_(y0, x0)]
    sums = a - b - cc + d
    areas = ((y1 - y0)[:, None] * (x1 - x0)[None, :]).astype(np.float64)
    areas = np.maximum(areas, 1.0)[..., None]
    return (sums / areas).astype(np.float32)


def _color_equal(a, b, tolerance=0.0):
    return np.max(np.abs(a - b), axis=-1) <= float(max(tolerance, 0.0))


def scale2x(grid, tolerance=0.0):
    """Scale2x pixel-art edge interpolation for an RGB/RGBA grid."""
    grid = np.asarray(grid, dtype=np.float32)
    p = np.pad(grid, ((1, 1), (1, 1), (0, 0)), mode="edge")
    b, d, e, f, h = p[:-2, 1:-1], p[1:-1, :-2], p[1:-1, 1:-1], p[1:-1, 2:], p[2:, 1:-1]
    p0 = np.where((_color_equal(d, b, tolerance) & ~_color_equal(b, f, tolerance) & ~_color_equal(d, h, tolerance))[..., None], d, e)
    p1 = np.where((_color_equal(b, f, tolerance) & ~_color_equal(b, d, tolerance) & ~_color_equal(f, h, tolerance))[..., None], f, e)
    p2 = np.where((_color_equal(d, h, tolerance) & ~_color_equal(d, b, tolerance) & ~_color_equal(h, f, tolerance))[..., None], d, e)
    p3 = np.where((_color_equal(h, f, tolerance) & ~_color_equal(d, h, tolerance) & ~_color_equal(b, f, tolerance))[..., None], f, e)
    out = np.empty((grid.shape[0] * 2, grid.shape[1] * 2, grid.shape[2]), dtype=np.float32)
    out[0::2, 0::2], out[0::2, 1::2] = p0, p1
    out[1::2, 0::2], out[1::2, 1::2] = p2, p3
    return out


def scale3x(grid, tolerance=0.0):
    """Scale3x pixel-art edge interpolation for an RGB/RGBA grid."""
    grid = np.asarray(grid, dtype=np.float32)
    p = np.pad(grid, ((1, 1), (1, 1), (0, 0)), mode="edge")
    b, d, e, f, h = p[:-2, 1:-1], p[1:-1, :-2], p[1:-1, 1:-1], p[1:-1, 2:], p[2:, 1:-1]
    eq = lambda x, y: _color_equal(x, y, tolerance)
    p0 = np.where(eq(d, b)[..., None], d, e)
    p1 = np.where(((eq(d, b) & ~eq(e, b)) | (eq(b, f) & ~eq(e, f)))[..., None], b, e)
    p2 = np.where(eq(b, f)[..., None], f, e)
    p3 = np.where(((eq(d, b) & ~eq(e, d)) | (eq(d, h) & ~eq(e, h)))[..., None], d, e)
    p4 = e
    p5 = np.where(((eq(b, f) & ~eq(e, b)) | (eq(h, f) & ~eq(e, h)))[..., None], f, e)
    p6 = np.where(eq(d, h)[..., None], d, e)
    p7 = np.where(((eq(d, h) & ~eq(e, d)) | (eq(h, f) & ~eq(e, f)))[..., None], h, e)
    p8 = np.where(eq(h, f)[..., None], f, e)
    out = np.empty((grid.shape[0] * 3, grid.shape[1] * 3, grid.shape[2]), dtype=np.float32)
    out[0::3, 0::3], out[0::3, 1::3], out[0::3, 2::3] = p0, p1, p2
    out[1::3, 0::3], out[1::3, 1::3], out[1::3, 2::3] = p3, p4, p5
    out[2::3, 0::3], out[2::3, 1::3], out[2::3, 2::3] = p6, p7, p8
    return out


def cleanedge_scale(grid, tolerance=0.05):
    """Tolerance-aware CleanEdge-style 2x scaling reconstruction."""
    # The original CleanEdge shader is MIT-licensed but implementation-specific
    # and GPU-oriented.  This NumPy path uses the same neighborhood intent with
    # tolerance-aware comparisons and keeps the attribution boundary clean.
    return scale2x(grid, tolerance)


def content_aware_scale(grid, factor=1.0, max_dimension=256, seam_mode="MINIMUM"):
    """Capped seam-carving resize for small pixel grids.

    This is an opt-in reconstruction of Pixel Composer's content-aware scale.
    It uses luminance-gradient energy, caps work by ``max_dimension``, and
    falls back to nearest scaling for oversized grids or a neutral factor.
    """
    grid = np.asarray(grid, dtype=np.float32)
    factor = float(factor)
    if abs(factor - 1.0) < 1e-6:
        return grid.copy()
    h, w = grid.shape[:2]
    target_w = max(1, int(round(w * factor)))
    target_h = max(1, int(round(h * factor)))
    if max(h, w, target_h, target_w) > int(max_dimension):
        return upscale_nearest(grid, target_w, target_h)

    seam_mode = str(seam_mode or "MINIMUM").upper()
    if seam_mode not in ("MINIMUM", "MAXIMUM"):
        raise ValueError(f"unknown content-aware seam mode {seam_mode!r}")

    def energy(arr):
        luma = arr[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        p = np.pad(luma, 1, mode="edge")
        return np.abs(p[1:-1, 2:] - p[1:-1, :-2]) + np.abs(p[2:, 1:-1] - p[:-2, 1:-1])

    def remove_vertical(arr):
        e = energy(arr)
        if seam_mode == "MAXIMUM":
            e = np.max(e) - e
        cost = e.copy().astype(np.float64)
        back = np.zeros_like(cost, dtype=np.int64)
        for y in range(1, cost.shape[0]):
            prev = np.pad(cost[y - 1], (1, 1), constant_values=np.inf)
            choices = np.stack([prev[:-2], prev[1:-1], prev[2:]], axis=0)
            pick = np.argmin(choices, axis=0)
            back[y] = np.arange(cost.shape[1]) + pick - 1
            cost[y] += choices[pick, np.arange(cost.shape[1])]
        x = int(np.argmin(cost[-1]))
        seam = np.empty(cost.shape[0], dtype=np.int64)
        for y in range(cost.shape[0] - 1, -1, -1):
            seam[y] = x
            x = int(np.clip(back[y, x], 0, cost.shape[1] - 1)) if y else x
        keep = np.arange(arr.shape[1])[None, :] != seam[:, None]
        return arr[keep].reshape(arr.shape[0], arr.shape[1] - 1, arr.shape[2])

    def insert_vertical(arr):
        e = energy(arr)
        seam = np.argmin(e.mean(axis=0))
        seam = int(seam)
        left = arr[:, max(seam - 1, 0):seam + 1]
        right = arr[:, seam:min(seam + 1, arr.shape[1] - 1) + 1]
        inserted = ((left[:, -1:] + right[:, :1]) * 0.5).astype(np.float32)
        return np.concatenate([arr[:, :seam + 1], inserted, arr[:, seam + 1:]], axis=1)

    out = grid.copy()
    while out.shape[1] > target_w:
        out = remove_vertical(out)
    while out.shape[1] < target_w:
        out = insert_vertical(out)
    while out.shape[0] > target_h:
        out = np.swapaxes(remove_vertical(np.swapaxes(out, 0, 1)), 0, 1)
    while out.shape[0] < target_h:
        out = np.swapaxes(insert_vertical(np.swapaxes(out, 0, 1)), 0, 1)
    return out.astype(np.float32)


def apply_scale_algorithm(grid, algorithm="NEAREST", tolerance=0.05,
                          content_factor=1.0, content_max_dimension=256,
                          content_seam_mode="MINIMUM"):
    """Apply a named pixel-art scaling algorithm to a small grid."""
    algorithm = str(algorithm or "NEAREST").upper()
    if algorithm in ("NEAREST", "NONE"):
        return np.asarray(grid, dtype=np.float32)
    if algorithm == "SCALE2X":
        return scale2x(grid, tolerance)
    if algorithm == "SCALE3X":
        return scale3x(grid, tolerance)
    if algorithm == "CLEANEDGE":
        return cleanedge_scale(grid, tolerance)
    if algorithm == "CONTENT_AWARE":
        return content_aware_scale(
            grid, content_factor, content_max_dimension, content_seam_mode
        )
    raise ValueError(f"unknown pixel scale algorithm {algorithm!r}")


def pixelate(img, gw, gh, mode="NEAREST", scale_algorithm="NEAREST", scale_tolerance=0.05,
             content_factor=1.0, content_max_dimension=256, content_seam_mode="MINIMUM"):
    """Pixelate an (h, w, C) float image onto a gw x gh grid, same output size.

    Returns (pixelated_full_res, grid) — the grid is the small image at grid
    resolution, used by preview filters and by palette generation.
    """
    if mode == "NEAREST_SOFTER":
        grid = downscale_area(img, gw, gh)
    else:
        grid = downscale_nearest(img, gw, gh)
    grid = apply_scale_algorithm(
        grid, scale_algorithm, scale_tolerance, content_factor, content_max_dimension,
        content_seam_mode,
    )
    h, w = img.shape[:2]
    return upscale_nearest(grid, w, h), grid


# ---------------------------------------------------------------------------
# Preview filters (operate on the grid, produce full-res output)
# ---------------------------------------------------------------------------

def _sample_coords(n_out, n_in):
    """0.5-centered fractional source coordinates, clamped to texel range."""
    s = (np.arange(n_out) + 0.5) * n_in / n_out - 0.5
    return np.clip(s, 0.0, n_in - 1.0)


def resample_bilinear(grid, w, h):
    gh, gw = grid.shape[:2]
    sy = _sample_coords(h, gh)
    sx = _sample_coords(w, gw)
    y0 = np.floor(sy).astype(np.int64)
    x0 = np.floor(sx).astype(np.int64)
    y1 = np.clip(y0 + 1, 0, gh - 1)
    x1 = np.clip(x0 + 1, 0, gw - 1)
    fy = (sy - y0).astype(np.float32)[:, None, None]
    fx = (sx - x0).astype(np.float32)[None, :, None]

    c00 = grid[y0][:, x0]
    c01 = grid[y0][:, x1]
    c10 = grid[y1][:, x0]
    c11 = grid[y1][:, x1]
    return (c00 * (1 - fx) * (1 - fy) + c01 * fx * (1 - fy)
            + c10 * (1 - fx) * fy + c11 * fx * fy).astype(np.float32)


def resample_n64_3point(grid, w, h):
    """N64-style 3-point filter: bilinear over the triangle half of each texel
    quad that contains the sample point (the RDP's tri-texel approximation)."""
    gh, gw = grid.shape[:2]
    sy = _sample_coords(h, gh)
    sx = _sample_coords(w, gw)
    y0 = np.floor(sy).astype(np.int64)
    x0 = np.floor(sx).astype(np.int64)
    y1 = np.clip(y0 + 1, 0, gh - 1)
    x1 = np.clip(x0 + 1, 0, gw - 1)
    fy = (sy - y0).astype(np.float32)[:, None, None]
    fx = (sx - x0).astype(np.float32)[None, :, None]

    c00 = grid[y0][:, x0]
    c01 = grid[y0][:, x1]
    c10 = grid[y1][:, x0]
    c11 = grid[y1][:, x1]

    lower = (fx + fy) <= 1.0  # which triangle of the quad
    w00 = np.where(lower, 1.0 - fx - fy, 0.0)
    w11 = np.where(lower, 0.0, fx + fy - 1.0)
    w01 = np.where(lower, fx, 1.0 - fy)
    w10 = np.where(lower, fy, 1.0 - fx)
    return (c00 * w00 + c01 * w01 + c10 * w10 + c11 * w11).astype(np.float32)


def resample_preview(grid, w, h, filter_mode):
    if filter_mode == "BILINEAR":
        return resample_bilinear(grid, w, h)
    if filter_mode == "N64_3POINT":
        return resample_n64_3point(grid, w, h)
    return upscale_nearest(grid, w, h)
