"""The Pixels section: grid dimensions, downscaling, upscalers, and preview filtering.

Mixin for ``properties.PixelatorPlusSettings``; Blender registers the
annotations of mixin bases, so these are ordinary scene settings.
"""

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
)

from .common import mark_dirty
from .items import (
    SCALE_ALGORITHMS,
)


class PixelSettings:
    # Dimensions
    use_separate_pixel_count: BoolProperty(
        name="Separate XY Pixel Count", default=False, update=mark_dirty,
        description="Enable non-square pixel counts",
    )
    square_pixel_count: IntProperty(
        name="Square Pixel Count", default=256, min=0, max=2048, update=mark_dirty,
        description="Pixel count on the shortest image axis",
    )
    pixel_count_x: IntProperty(
        name="Pixel Count X", default=256, min=0, max=2048, update=mark_dirty,
    )
    pixel_count_y: IntProperty(
        name="Pixel Count Y", default=256, min=0, max=2048, update=mark_dirty,
    )
    # Pixelate Style
    downscale_mode: EnumProperty(
        name="Downscale Mode", default="NEAREST", update=mark_dirty,
        items=[
            ("NEAREST", "Nearest Neighbor", "Hard blocky pixels"),
            ("NEAREST_SOFTER", "Nearest Softer", "Area-averaged block colors"),
        ],
    )
    scale_algorithm: EnumProperty(
        name="Pixel-Art Scale Algorithm", default="NEAREST", items=SCALE_ALGORITHMS,
        update=mark_dirty,
        description="Optional edge-aware algorithm applied to the small pixel grid before final nearest upscaling",
    )
    scale_tolerance: FloatProperty(
        name="Scale Tolerance", default=0.05, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty,
        description="Color difference tolerated by Scale2x, Scale3x, and CleanEdge",
    )
    content_aware_factor: FloatProperty(
        name="Content-Aware Factor", default=1.0, min=0.25, max=4.0,
        update=mark_dirty,
        description="Target scale factor for the capped content-aware grid resize",
    )
    content_aware_max_dimension: IntProperty(
        name="Content-Aware Work Limit", default=128, min=16, max=512,
        update=mark_dirty,
        description="Maximum working dimension before content-aware scaling falls back to nearest",
    )
    content_aware_seam_mode: EnumProperty(
        name="Content-Aware Seam", default="MINIMUM", update=mark_dirty,
        items=[
            ("MINIMUM", "Protect Edges", "Remove low-energy seams first"),
            ("MAXIMUM", "Favor Edges", "Remove high-energy seams first for an abstract effect"),
        ],
    )
    filter_preview: EnumProperty(
        name="Preview Texture Filtering", default="NONE", update=mark_dirty,
        description="Viewport preview filtering only — never applied on Apply/Export",
        items=[
            ("NONE", "None", "Nearest (pixel-perfect)"),
            ("BILINEAR", "Bilinear", "Bilinear smoothing of the pixel grid"),
            ("N64_3POINT", "N64 3-Point", "Nintendo 64 three-point filtering"),
        ],
    )
