"""PixelatorPlus UI shared by the Image Editor and Compositor sidebars.

One draw function serves both editors.  A compact workflow header (input,
recipe, Apply, live preview) is always visible; everything else lives in
foldable layout panels (Blender 4.1+ ``UILayout.panel``) whose headers show a
summary or an on/off toggle, so the common path stays short.  Controls only
appear when their effect is active.

Drawing is strictly read-only: Blender forbids ID writes during ``draw``, so
data initialization and repair live in operators.
"""

import bpy

from .core.pixelate import compute_grid
from .operators import assets
from .properties import V3_STAGE_ITEMS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SUMMARY_CHARS = 18

def _section(layout, idname, title, icon="NONE", summary="", toggle=None, closed=True):
    """Foldable section; returns its body layout, or ``None`` when folded.

    ``toggle`` is ``(data, property)`` for a header checkbox; the body is
    drawn inactive (greyed, still editable) while that toggle is off.
    """
    if layout.use_property_split:
        # A nested header would otherwise inherit the label/value split.
        layout = layout.column()
        layout.use_property_split = False
    header, body = layout.panel(f"PIXELATORPLUS_{idname}", default_closed=closed)
    if toggle is not None:
        header.prop(toggle[0], toggle[1], text="")
    header.label(text=title, icon=icon)
    if summary:
        # Short enough that the section title always stays readable.
        if len(summary) > _SUMMARY_CHARS:
            summary = summary[:_SUMMARY_CHARS - 1] + "…"
        right = header.row()
        right.alignment = "RIGHT"
        right.label(text=summary)
    if body is None:
        return None
    body.use_property_split = True
    body.use_property_decorate = False
    if toggle is not None:
        body.active = bool(getattr(toggle[0], toggle[1]))
    return body


def _enum_label(data, prop):
    """Display name of an enum property's current value."""
    value = getattr(data, prop)
    return data.bl_rna.properties[prop].enum_items[value].name


def _grid_summary(s):
    """``'64 × 48 cells'`` for the current input image, or ``''``."""
    image = s.input_image
    if image is None or image.size[0] == 0 or image.size[1] == 0:
        return ""
    gw, gh = compute_grid(
        image.size[0], image.size[1], s.square_pixel_count,
        s.use_separate_pixel_count, s.pixel_count_x, s.pixel_count_y,
    )
    return f"{gw} × {gh} cells"


# ---------------------------------------------------------------------------
# Always-visible workflow header
# ---------------------------------------------------------------------------

def _draw_workflow(layout, s):
    col = layout.column(align=True)
    row = col.row(align=True)
    row.prop(s, "input_image", text="")
    row.operator("pixelatorplus.grab_basecolor", text="", icon="MATERIAL")
    row = col.row(align=True)
    row.prop(s, "style_preset", text="")
    row.operator("pixelatorplus.load_style_preset", text="Load")
    col.operator("pixelatorplus.surprise_style", text="Surprise Me", icon="FILE_REFRESH")

    row = layout.row()
    row.scale_y = 1.5
    row.operator("pixelatorplus.apply", icon="IMAGE_DATA")
    if s.last_output_name:
        layout.label(text=s.last_output_name, icon="CHECKMARK")

    row = layout.row(align=True)
    row.prop(s, "live_preview", icon="HIDE_OFF" if s.live_preview else "HIDE_ON")
    if s.live_preview:
        row.prop(s, "preview_mode", text="")
        row = layout.row(align=True)
        row.prop(s, "preview_max_size", text="Max Size")
        row.prop(s, "preview_cache_enabled", text="Cache", toggle=True)
        if s.preview_status:
            layout.label(text=s.preview_status, icon="ERROR" if s.preview_failed else "INFO")


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _draw_pixels(layout, s):
    body = _section(layout, "pixels", "Pixels", "MESH_GRID", _grid_summary(s), closed=False)
    if body is None:
        return
    body.prop(s, "use_separate_pixel_count", text="Separate X / Y")
    if s.use_separate_pixel_count:
        col = body.column(align=True)
        col.prop(s, "pixel_count_x", text="Cells X")
        col.prop(s, "pixel_count_y", text="Y")
    else:
        body.prop(s, "square_pixel_count", text="Cells")
    body.prop(s, "downscale_mode", text="Downscale")
    body.prop(s, "scale_algorithm", text="Upscaler")
    if s.scale_algorithm in ("SCALE2X", "SCALE3X", "CLEANEDGE"):
        body.prop(s, "scale_tolerance", slider=True)
    elif s.scale_algorithm == "CONTENT_AWARE":
        col = body.column(align=True)
        col.prop(s, "content_aware_factor", text="Factor")
        col.prop(s, "content_aware_max_dimension", text="Work Limit")
        col.prop(s, "content_aware_seam_mode", text="Seams")
    body.prop(s, "filter_preview", text="Preview Filter")
    if s.filter_preview != "NONE":
        body.label(text="Preview only; never applied or exported.", icon="INFO")


def _draw_color(layout, s):
    qt = s.quantize_type
    body = _section(layout, "color", "Color", "COLOR", _enum_label(s, "quantize_type"),
                    closed=False)
    if body is None:
        return
    body.prop(s, "quantize_type", text="Mode")

    if qt == "CUSTOM_PALETTE":
        body.prop(s, "k_num_colors", text="Colors")
        body.prop(s, "palette_extract_method", text="Extraction")
        body.prop(s, "color_mode", text="Build Space")
        body.prop(s, "apply_palette_mode", text="Match Space")
        body.prop(s, "force_colors")
        body.operator("pixelatorplus.freeze_palette", text="Freeze Palette for Animation",
                      icon="FREEZE")
        _draw_palette_tuning(body, s)
    elif qt == "PER_CHANNEL":
        body.prop(s, "quantize_colors_or_bits", text="Levels By")
        if s.quantize_colors_or_bits == "BITS":
            body.prop(s, "quantize_bits", text="Bits")
        else:
            body.prop(s, "quantize_colors", text="Colors")
        body.prop(s, "use_range_adaptive", text="Adapt to Image Range")
    elif qt == "LUT":
        body.prop(s, "lut", text="Palette")
        if s.lut == "CUSTOM_LUT":
            body.prop(s, "custom_lut_image", text="Image")
            body.label(text="Live preview skips 4K LUT images.", icon="INFO")
        elif s.lut == "CUBE_LUT":
            body.prop(s, "cube_lut_path", text="File")
            body.prop(s, "cube_lut_interpolation", text="Interpolation")
            body.prop(s, "cube_lut_strength", text="Strength", slider=True)
        elif s.lut == "CUSTOM_PALETTE":
            body.prop(s, "custom_palette_image", text="Image")
        if s.lut not in ("CUSTOM_LUT", "CUBE_LUT"):
            body.prop(s, "apply_palette_mode", text="Match Space")

    if qt != "NONE":
        body.prop(s, "diffusion")
        if s.diffusion != "NONE":
            col = body.column(align=True)
            col.prop(s, "diffusion_strength", text="Strength", slider=True)
            col.prop(s, "diffusion_serpentine", text="Serpentine")

    _draw_posterize(body, s)


def _draw_palette_tuning(layout, s):
    body = _section(layout, "palette_tuning", "Palette Tuning", "PREFERENCES")
    if body is None:
        return
    body.prop(s, "initialize_mode", text="Initialize")
    body.prop(s, "quantize_quality")
    body.prop(s, "gamma")
    body.prop(s, "use_pixelated_for_quantize")
    body.prop(s, "use_explicit_quantize_seed", text="Explicit Seed")
    if s.use_explicit_quantize_seed:
        body.prop(s, "quantize_seed", text="Seed")
    body.prop(s, "use_chroma_importance", text="Color Importance")
    if s.use_chroma_importance:
        body.prop(s, "chroma_importance", text="Amount", slider=True)
    body.separator()
    body.prop(s, "palette_sort_mode", text="Sort")
    body.prop(s, "palette_shift", text="Shift")
    body.prop(s, "palette_trim", text="Trim Duplicates")
    body.prop(s, "palette_replace_image", text="Replace From")
    if s.palette_replace_image:
        body.prop(s, "palette_replace_threshold", text="Threshold", slider=True)


def _draw_posterize(layout, s):
    summary = f"{s.posterize_levels} levels" if s.posterize_enabled else ""
    body = _section(layout, "posterize", "Posterize / Levels", "IMAGE_RGB", summary,
                    toggle=(s, "posterize_enabled"))
    if body is None:
        return
    body.prop(s, "posterize_levels", text="Levels")
    body.prop(s, "posterize_range_mode", text="Range")
    if s.posterize_range_mode != "FULL":
        col = body.column(align=True)
        col.prop(s, "posterize_range_low", text="Black", slider=True)
        col.prop(s, "posterize_range_high", text="White", slider=True)
    if s.posterize_range_mode == "PERCENTILE":
        col = body.column(align=True)
        col.prop(s, "posterize_percentile_low", text="Shadow %")
        col.prop(s, "posterize_percentile_high", text="Highlight %")
    body.prop(s, "posterize_gamma", text="Gamma")
    body.prop(s, "posterize_mix", text="Mix", slider=True)
    body.prop(s, "posterize_channel_mask", text="Channels")
    body.prop(s, "posterize_alpha_policy", text="Alpha")
    body.prop(s, "range_map_image", text="Range Map")


def _draw_dither(layout, s):
    on = s.dither_type != "NONE"
    body = _section(layout, "dither", "Dither", "TEXTURE",
                    _enum_label(s, "dither_type") if on else "Off")
    if body is None:
        return
    body.prop(s, "dither_type", text="Pattern")
    if not on:
        return
    threshold = s.dither_strategy == "PALETTE_THRESHOLD"
    body.prop(s, "dither_strategy", text="Strategy")
    if s.dither_type == "CUSTOM":
        body.prop(s, "custom_dither_image", text="Image")
        body.prop(s, "custom_dither_resolution", text="Tile Size")
    elif s.dither_type in ("CUSTOM_8X8", "CUSTOM_16X16"):
        body.prop(s, "custom_dither_image", text="Image")
    body.prop(s, "dither_strength", text="Strength", slider=True)
    if threshold:
        body.prop(s, "palette_dither_contrast", text="Contrast", slider=True)
        body.prop(s, "palette_dither_invert", text="Invert Threshold")
        body.prop(s, "threshold_map_image", text="Threshold Map")
    else:
        body.prop(s, "dither_blend_mode", text="Blend")
        body.prop(s, "dither_saturation", text="Saturation", slider=True)
        body.prop(s, "use_gray_dither")
    body.prop(s, "lock_dither_to_grid", text="Lock to Pixel Grid")
    _draw_dither_mask(body, s)


def _draw_dither_mask(layout, s):
    mt = s.dither_mask_type
    body = _section(layout, "dither_mask", "Mask", "MOD_MASK",
                    _enum_label(s, "dither_mask_type") if mt != "NONE" else "")
    if body is None:
        return
    body.prop(s, "dither_mask_type", text="Source")
    if mt != "NONE":
        if mt == "CUSTOM":
            body.prop(s, "custom_mask_image", text="Image")
        elif mt == "LUMINANCE":
            col = body.column(align=True)
            col.prop(s, "dither_mask_lum_low", text="Low", slider=True)
            col.prop(s, "dither_mask_lum_high", text="High", slider=True)
        elif mt == "SATURATION":
            col = body.column(align=True)
            col.prop(s, "dither_mask_sat_low", text="Low", slider=True)
            col.prop(s, "dither_mask_sat_high", text="High", slider=True)
        elif mt == "GRADIENT":
            body.prop(s, "dither_mask_gradient_angle", text="Angle")
        body.prop(s, "dither_cutoff", text="Strength", slider=True)
        body.prop(s, "dither_mask_gamma", text="Gamma")
        body.prop(s, "dither_mask_blur", text="Blur")
        body.prop(s, "dither_mask_invert", text="Invert")
        if mt in ("EDGES", "FLATS"):  # frequency weights shape edges only
            body.prop(s, "show_mask_controls")
            if s.show_mask_controls:
                col = body.column(align=True)
                for key in ("huge", "big", "large", "medium", "fine", "sharp", "pixel_perfect"):
                    col.prop(s, key, slider=True)
    body.prop(s, "preview_dither_mask", text="Show Mask Instead")


def _draw_sprite(layout, s):
    parts = []
    if s.sprite_outline != "NONE":
        parts.append("Outline")
    if s.sprite_cleanup:
        parts.append("Cleanup")
    body = _section(layout, "sprite", "Sprite", "OUTLINER_OB_GREASEPENCIL",
                    " + ".join(parts) or "Off")
    if body is None:
        return
    body.prop(s, "sprite_cleanup")
    if s.sprite_cleanup:
        body.prop(s, "sprite_cleanup_agreement", text="Agreement")
    body.prop(s, "sprite_outline")
    if s.sprite_outline != "NONE":
        body.prop(s, "sprite_outline_color_mode", text="Color")
        if s.sprite_outline_color_mode == "CUSTOM":
            body.prop(s, "sprite_outline_color", text="Custom")
        elif s.sprite_outline_color_mode == "SELECTIVE":
            body.prop(s, "sprite_outline_darken", slider=True)
        body.prop(s, "sprite_outline_corners", text="Corners")
    if s.sprite_cleanup or s.sprite_outline != "NONE":
        body.prop(s, "sprite_alpha_threshold", slider=True)
        body.label(text="Uses transparency: render with Film > Transparent.", icon="INFO")


def _draw_finish(layout, s):
    body = _section(layout, "finish", "Finish", "SHADING_RENDERED",
                    toggle=(s, "finish_enabled"))
    if body is None:
        return
    col = body.column(align=True)
    col.prop(s, "finish_brightness", slider=True)
    col.prop(s, "finish_contrast", slider=True)
    col.prop(s, "finish_exposure", slider=True)
    col.prop(s, "finish_saturation", slider=True)
    col = body.column(align=True)
    col.prop(s, "finish_grain", slider=True)
    col.prop(s, "finish_grain_brightness", text="Brightness", slider=True)
    col.prop(s, "finish_grain_saturation", text="Saturation", slider=True)
    col = body.column(align=True)
    col.prop(s, "finish_scanline_strength", text="Scanlines", slider=True)
    col.prop(s, "finish_scanline_size", text="Size")
    col.prop(s, "finish_scanline_axis", text="Direction")
    col.prop(s, "finish_scanline_invert", text="Invert")
    col = body.column(align=True)
    col.prop(s, "finish_vignette_strength", slider=True)
    col.prop(s, "finish_vignette_roundness", text="Roundness")
    body.prop(s, "finish_chromatic_aberration", slider=True)
    col = body.column(align=True)
    col.prop(s, "finish_mask_type", text="Mask")
    col.prop(s, "finish_mask_mix", text="Mix", slider=True)
    col.prop(s, "finish_mask_invert", text="Invert Mask")
    body.prop(s, "finish_channel_mask", text="Channels")


def _draw_output(layout, s):
    body = _section(layout, "output", "Output", "FILE_IMAGE")
    if body is None:
        return
    body.prop(s, "output_palette")
    if s.quantize_type == "CUSTOM_PALETTE":
        body.prop(s, "output_lut")
    elif s.quantize_type == "LUT":
        body.prop(s, "output_default_lut")
    if s.output_lut or s.output_default_lut:
        body.label(text="4K LUTs use substantial memory.", icon="INFO")
    col = body.column(align=True)
    col.operator("pixelatorplus.export_output", icon="EXPORT")
    row = col.row(align=True)
    row.operator("pixelatorplus.export_palette", text="Palette", icon="COLOR")
    row.operator("pixelatorplus.export_lut", text="4K LUT", icon="RENDERLAYERS")
    row = col.row(align=True)
    row.operator("pixelatorplus.export_palette_json", text="Palette JSON", icon="TEXT")
    row.operator("pixelatorplus.export_cube", text=".cube LUT", icon="IMAGE_RGB")
    body.operator("pixelatorplus.material_hookup", icon="MATERIAL")


def _draw_advanced(layout, s):
    body = _section(layout, "advanced", "Advanced", "OPTIONS")
    if body is None:
        return
    body.prop(s.v3, "palette_lock")
    if s.v3.palette_lock == "PALETTE_TINT":
        body.prop(s.v3, "palette_lock_strength", text="Tint Strength", slider=True)
    body.prop(s.v3, "grid_coherence")
    body.prop(s, "strength_map_image", text="Strength Map")
    row = body.row(align=True)
    row.prop(s, "random_seed")
    row.operator("pixelatorplus.randomize_seed", text="", icon="FILE_REFRESH")

    stack = _section(body, "stage_stack", "Stage Stack", "NODETREE")
    if stack is not None:
        _draw_stage_stack(stack, s.v3.stage_stack)

    snapshot = _section(body, "plan_snapshot", "Plan Snapshot", "FILE_BLEND",
                        s.v3_plan_fingerprint)
    if snapshot is not None:
        row = snapshot.row(align=True)
        row.operator("pixelatorplus.snapshot_plan", text="Capture", icon="DUPLICATE")
        row.operator("pixelatorplus.restore_plan", text="Restore", icon="LOOP_BACK")
        snapshot.label(text="Image inputs stay linked; only settings are stored.",
                       icon="INFO")


def _draw_stage_stack(layout, stack):
    """Draw stage toggles without mutating data (Blender forbids ID writes in draw)."""
    labels = {stage_id: label for stage_id, label, _description in V3_STAGE_ITEMS}
    if [item.stage_id for item in stack] != list(labels):
        if len(stack) == 0:
            # New scenes have no stack yet; every stage runs until the user
            # creates one to edit.
            layout.label(text="All stages are active.", icon="CHECKMARK")
            layout.operator("pixelatorplus.init_stage_stack", icon="ADD")
        else:
            # Files saved before a stage existed have an incomplete stack;
            # the missing stages still run until the stack is repaired.
            layout.label(text="This file predates newer stages.", icon="INFO")
            layout.operator("pixelatorplus.init_stage_stack", text="Repair Stage Stack",
                            icon="FILE_REFRESH")
        return
    col = layout.column(align=True)
    for item in stack:
        row = col.row(align=True)
        # Pixelate builds the grid every later stage depends on.
        row.enabled = item.stage_id != "pixelate"
        row.prop(item, "enabled", text=labels[item.stage_id])


def _draw_compositor(layout, s):
    body = _section(layout, "compositor", "Compositor", "NODE_COMPOSITING", closed=False)
    if body is None:
        return
    body.label(text="Bake the exact result into an Image node:")
    col = body.column(align=True)
    row = col.row(align=True)
    row.operator("pixelatorplus.bake_compositor_input", text="Bake Input", icon="IMAGE_DATA")
    row.operator("pixelatorplus.bake_compositor_render", text="Bake Render",
                 icon="RENDER_RESULT")
    col.operator("pixelatorplus.connect_baked_output", text="Connect to Output",
                 icon="LINKED")
    body.prop(s, "auto_bake_render")
    if s.auto_bake_render:
        body.prop(s, "auto_connect_baked_output")
        if s.auto_connect_baked_output:
            body.label(text="Replaces the compositor output link after each render.",
                       icon="ERROR")
    body.separator()
    if assets.compositor_assets_registered():
        body.label(text="Node presets are in the Asset Shelf.", icon="CHECKMARK")
    else:
        body.operator("pixelatorplus.install_compositor_assets",
                      text="Add Node Presets to Asset Library", icon="ASSET_MANAGER")


def _draw(layout, context, compositor=False):
    s = context.scene.pixelatorplus
    _draw_workflow(layout, s)
    _draw_pixels(layout, s)
    _draw_color(layout, s)
    _draw_dither(layout, s)
    _draw_sprite(layout, s)
    _draw_finish(layout, s)
    _draw_output(layout, s)
    if compositor:
        _draw_compositor(layout, s)
    _draw_advanced(layout, s)


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------

class PIXELATORPLUS_PT_image_editor(bpy.types.Panel):
    bl_idname = "PIXELATORPLUS_PT_image_editor"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "PixelatorPlus"
    bl_label = "PixelatorPlus"

    def draw(self, context):
        _draw(self.layout, context)


class PIXELATORPLUS_PT_compositor(bpy.types.Panel):
    bl_idname = "PIXELATORPLUS_PT_compositor"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "PixelatorPlus"
    bl_label = "PixelatorPlus"

    @classmethod
    def poll(cls, context):
        return getattr(context.space_data, "tree_type", None) == "CompositorNodeTree"

    def draw(self, context):
        _draw(self.layout, context, compositor=True)


classes = (
    PIXELATORPLUS_PT_image_editor,
    PIXELATORPLUS_PT_compositor,
)

register, unregister = bpy.utils.register_classes_factory(classes)
