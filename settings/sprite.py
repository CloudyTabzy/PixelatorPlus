"""The Sprite section: stray-pixel cleanup, part lines, and outlines.

Mixin for ``properties.PixelatorPlusSettings``; Blender registers the
annotations of mixin bases, so these are ordinary scene settings.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
)

from .common import mark_dirty


class SpriteSettings:
    # Sprite (add-on extra, PixelatorPlus-native)
    sprite_cleanup: BoolProperty(
        name="Remove Stray Pixels", default=False, update=mark_dirty,
        description="Replace isolated cells with the color their neighbors agree on",
    )
    sprite_cleanup_agreement: IntProperty(
        name="Neighbor Agreement", default=3, min=2, max=4, update=mark_dirty,
        description="How many of a stray cell's four neighbors must share a color "
        "before it is replaced (4 = only fully surrounded cells)",
    )
    sprite_outline: EnumProperty(
        name="Outline", default="NONE", update=mark_dirty,
        description="Draw a one-cell outline around transparent-background silhouettes",
        items=[
            ("NONE", "None", "No outline"),
            ("OUTSIDE", "Outside", "Fill empty cells around the silhouette"),
            ("INSIDE", "Inside", "Recolor the silhouette's own edge cells"),
        ],
    )
    sprite_part_lines: BoolProperty(
        name="Part Lines", default=False, update=mark_dirty,
        description="Draw one-pixel lines where the model's parts meet (needs an ID map)",
    )
    sprite_part_source: EnumProperty(
        name="Parts", default="OBJECT", update=mark_dirty,
        items=[
            ("OBJECT", "Objects", "Each object is one part"),
            ("MATERIAL", "Materials", "Each material is one part"),
        ],
        description="What counts as one part when an ID map is rendered",
    )
    id_map_image: PointerProperty(
        name="ID Map", type=bpy.types.Image, update=mark_dirty,
        description="Flat per-part color render with the same framing as the input "
        "(Render ID Map creates one; sprite sheets render their own)",
    )
    sprite_outline_color_mode: EnumProperty(
        name="Line Color", default="SELECTIVE", update=mark_dirty,
        description="Color of outlines and part lines",
        items=[
            ("SELECTIVE", "Selective", "Darken the neighboring sprite color (pixel-art sel-out)"),
            ("DARKEST", "Darkest Palette Color", "Use the darkest color of the active palette"),
            ("CUSTOM", "Custom", "Use a fixed outline color"),
        ],
    )
    sprite_outline_color: FloatVectorProperty(
        name="Custom Line Color", size=3, default=(0.05, 0.05, 0.08), min=0.0, max=1.0,
        subtype="COLOR_GAMMA", update=mark_dirty,
        description="Fixed outline color (snapped to the palette when one is active)",
    )
    sprite_outline_darken: FloatProperty(
        name="Darken", default=0.5, min=0.0, max=1.0, subtype="FACTOR",
        update=mark_dirty,
        description="How much darker than the sprite selective lines are",
    )
    sprite_outline_corners: BoolProperty(
        name="Outline Corners", default=False, update=mark_dirty,
        description="Also outline diagonal neighbors for a heavier, rounder outline",
    )
    sprite_alpha_threshold: FloatProperty(
        name="Opacity Threshold", default=0.5, min=0.01, max=1.0, subtype="FACTOR",
        update=mark_dirty,
        description="Cells at least this opaque count as part of the sprite",
    )
