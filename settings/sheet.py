"""The Sprite Sheet section: animation export workflow (not part of the look).

Mixin for ``properties.PixelatorPlusSettings``; Blender registers the
annotations of mixin bases, so these are ordinary scene settings.
"""

from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
)




class SpriteSheetSettings:
    # Sprite sheet (animation export workflow, not part of the look)
    sheet_use_scene_range: BoolProperty(
        name="Use Scene Frame Range", default=True,
        description="Render the scene's start-to-end frames",
    )
    sheet_frame_start: IntProperty(name="Start", default=1, min=0)
    sheet_frame_end: IntProperty(name="End", default=24, min=0)
    sheet_frame_step: IntProperty(
        name="Step", default=1, min=1, max=100,
        description="Render every Nth frame",
    )
    sheet_layout: EnumProperty(
        name="Layout", default="GRID",
        items=[
            ("GRID", "Grid", "Rows and columns"),
            ("ROW", "Row", "One horizontal strip"),
            ("COLUMN", "Column", "One vertical strip"),
        ],
    )
    sheet_columns: IntProperty(
        name="Columns", default=0, min=0, max=256,
        description="Frames per row (0 = automatic, near square)",
    )
    sheet_spacing: IntProperty(
        name="Spacing", default=0, min=0, max=64,
        description="Transparent pixels between frames",
    )
    sheet_padding: IntProperty(
        name="Padding", default=0, min=0, max=64,
        description="Transparent pixels around the whole sheet",
    )
    sheet_pixel_scale: IntProperty(
        name="Pixel Scale", default=1, min=1, max=16,
        description="Output pixels per sprite pixel (1 = native resolution)",
    )
    sheet_trim: BoolProperty(
        name="Trim Empty Space", default=False,
        description="Crop every frame to the area any frame uses, keeping the animation aligned",
    )
    sheet_skip_empty: BoolProperty(
        name="Skip Empty Frames", default=False,
        description="Leave fully transparent frames out of the sheet",
    )
    sheet_shared_palette: BoolProperty(
        name="Shared Palette", default=True,
        description="Generate one palette from all frames so colors never flicker "
        "(Generated Palette mode)",
    )
    sheet_transparent: BoolProperty(
        name="Transparent Background", default=True,
        description="Render with Film > Transparent for the duration of the sheet",
    )
