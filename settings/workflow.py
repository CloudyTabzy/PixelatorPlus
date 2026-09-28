"""Input, recipes, live preview, snapshots, compositor automation, and output state.

Mixin for ``properties.PixelatorPlusSettings``; Blender registers the
annotations of mixin bases, so these are ordinary scene settings.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from ..presets import PRESET_ITEMS
from .common import mark_dirty


class WorkflowSettings:
    # image pins
    input_image: PointerProperty(
        name="Input", type=bpy.types.Image, update=mark_dirty,
        description="Source image to pixelate",
    )
    last_sheet_name: StringProperty(name="Last Sprite Sheet", default="")
    # add-on state
    style_preset: EnumProperty(
        name="Style Recipe",
        default="MODERN_INDIE_24",
        items=PRESET_ITEMS,
        description="Choose an editable starting recipe; use Load Style Recipe to apply it",
    )
    random_seed: IntProperty(
        name="Random Seed", default=0, update=mark_dirty,
        description="Seed for white noise and palette initialization ($randomseed)",
    )
    live_preview: BoolProperty(
        name="Live Preview", default=False, update=mark_dirty,
        description="Recompute a capped-resolution preview while tweaking",
    )
    preview_mode: EnumProperty(
        name="Live Preview Mode", default="FINAL", update=mark_dirty,
        description="Draft bypasses intensive dither and quantization stages; Apply always uses final settings",
        items=[
            ("DRAFT", "Draft (Pixelation Only)", "Fast pixelation-only preview while adjusting composition"),
            ("FINAL", "Final Effects", "Preview all enabled effects at the preview resolution"),
        ],
    )
    preview_max_size: IntProperty(
        name="Preview Max Size", default=512, min=64, max=1024, update=mark_dirty,
        description="Longest-side cap for the live preview",
    )
    # Written by the preview timer, shown in the panel; not user settings.
    preview_status: StringProperty(
        name="Preview Status", default="", options={"HIDDEN"},
        description="Why the live preview is approximate or out of date",
    )
    preview_failed: BoolProperty(name="Preview Failed", default=False, options={"HIDDEN"})
    preview_cache_enabled: BoolProperty(
        name="Cache Live Preview", default=True, update=mark_dirty,
        description="Reuse identical preview results without starting a worker thread",
    )
    # Explicit v3 scene snapshot.  Image pins remain PointerProperties and are
    # intentionally not serialized into this string.
    v3_plan_json: StringProperty(
        name="V3 Plan Snapshot", default="", options={"HIDDEN"},
        description="Validated JSON snapshot of scalar settings and stage order",
    )
    v3_plan_fingerprint: StringProperty(
        name="V3 Plan Fingerprint", default="", options={"HIDDEN"},
    )
    auto_bake_render: BoolProperty(
        name="Auto Bake Finished Renders", default=False,
        description="Run the exact PixelatorPlus pipeline after each render and update the compositor output node",
    )
    auto_connect_baked_output: BoolProperty(
        name="Auto Connect Baked Output", default=False,
        description="When auto baking, replace the Composite image link with the exact baked output",
    )
    last_output_name: StringProperty(name="Last Output", default="")
    last_palette_name: StringProperty(name="Last Palette Output", default="")
    last_palette_index_name: StringProperty(name="Last Palette Index Output", default="")
    last_lut_name: StringProperty(name="Last LUT Output", default="")
