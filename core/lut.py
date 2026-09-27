"""4K LUT support.

Layout (documented approximation of the Substance 4K LUT used by PixelatorPlus's
Lookup Table quantization and Promo_LUT.png): a 4096x4096 image = 256^3 RGB
grid, arranged as a 16x16 grid of 256x256 tiles. Blue selects the tile in
row-major order (tile_x = b % 16, tile_y = b // 16); within a tile, x = red,
y = green, all channels quantized to 8-bit steps.
"""

import numpy as np

LUT_SIZE = 4096
_LUT_SIZE = LUT_SIZE
_LUT_TILES = 16
_LUT_TILE = 256


def identity_lut():
    """The default 4K LUT: out == in (PixelatorPlus's 'Output the Default LUT')."""
    ramp = np.linspace(0.0, 1.0, _LUT_TILE, dtype=np.float32)
    lut = np.empty((_LUT_SIZE, _LUT_SIZE, 3), dtype=np.float32)
    for b in range(_LUT_TILES * _LUT_TILES):
        ty, tx = divmod(b, _LUT_TILES)
        tile = np.empty((_LUT_TILE, _LUT_TILE, 3), dtype=np.float32)
        tile[..., 0] = ramp[None, :]
        tile[..., 1] = ramp[:, None]
        tile[..., 2] = b / 255.0
        lut[ty * _LUT_TILE : (ty + 1) * _LUT_TILE, tx * _LUT_TILE : (tx + 1) * _LUT_TILE] = tile
    return lut


def apply_lut(rgb, lut):
    """Sample a 4K LUT image for every pixel of an (h, w, 3) 0..1 image.

    Nearest sampling on 8-bit indices. Raises ValueError if `lut` is not
    4096x4096.
    """
    if lut.shape[0] != _LUT_SIZE or lut.shape[1] != _LUT_SIZE:
        raise ValueError(f"custom LUT must be {_LUT_SIZE}x{_LUT_SIZE}")
    idx = np.round(np.clip(rgb[..., :3], 0.0, 1.0) * 255.0).astype(np.int32)
    r, g, b = idx[..., 0], idx[..., 1], idx[..., 2]
    py = (b // _LUT_TILES) * _LUT_TILE + g
    px = (b % _LUT_TILES) * _LUT_TILE + r
    return lut[py, px, :3].astype(np.float32)


def encode_lut_from_palette(palette, chunk_tiles=True):
    """Build a 4K LUT mapping every RGB triple to its nearest palette color.

    Nearest-neighbor in RGB space, computed per blue tile to bound memory.
    `palette`: (K, 3) float 0..1.
    """
    palette = np.asarray(palette, dtype=np.float32)[:, :3]
    ramp = np.linspace(0.0, 1.0, _LUT_TILE, dtype=np.float32)
    lut = np.empty((_LUT_SIZE, _LUT_SIZE, 3), dtype=np.float32)
    for b in range(_LUT_TILES * _LUT_TILES):
        ty, tx = divmod(b, _LUT_TILES)
        grid = np.empty((_LUT_TILE, _LUT_TILE, 3), dtype=np.float32)
        grid[..., 0] = ramp[None, :]
        grid[..., 1] = ramp[:, None]
        grid[..., 2] = b / 255.0
        flat = grid.reshape(-1, 3).astype(np.float64)
        # nearest palette color per grid point, chunked over grid points
        out = np.empty((flat.shape[0], 3), dtype=np.float32)
        step = 8192 if chunk_tiles else flat.shape[0]
        for s in range(0, flat.shape[0], step):
            pts = flat[s : s + step]
            d = (
                (pts[:, 0:1] - palette[:, 0].T) ** 2
                + (pts[:, 1:2] - palette[:, 1].T) ** 2
                + (pts[:, 2:3] - palette[:, 2].T) ** 2
            )
            out[s : s + step] = palette[np.argmin(d, axis=1)]
        lut[ty * _LUT_TILE : (ty + 1) * _LUT_TILE, tx * _LUT_TILE : (tx + 1) * _LUT_TILE] = out.reshape(
            _LUT_TILE, _LUT_TILE, 3
        )
    return lut
