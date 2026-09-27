"""PixelatorPlus extension entry point for Blender 4.2+.

A native Blender re-implementation of the PixelatorPlus v2.72 Substance filter
(Action Dawg / Victoria Holland): pixelation with square or per-axis pixel
counts, ordered/noise/blue-noise/custom dithering with edge-aware masking,
and color quantization via k-means palettes (RGB/CIELAB/Oklab), per-channel
reduction, or built-in vintage LUTs (Amiga, Apple II, Atari 2600, C64, NES,
Gameboy, Master System, Web...).

Panels live in the Image Editor and Compositor sidebars ("PixelatorPlus" tab).
"""

__author__ = "CloudyTabzy"

try:
    import bpy  # noqa: F401
except ImportError:
    bpy = None  # standalone use: pixelatorplus.core stays importable for pytest

if bpy is not None:
    from . import operators, panels, preview, properties

    _modules = (properties, panels, operators, preview)

    def register():
        for m in _modules:
            m.register()

    def unregister():
        for m in reversed(_modules):
            m.unregister()

    if __name__ == "__main__":
        register()
