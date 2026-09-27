"""PixelatorPlus UI shared by the Image Editor and Compositor sidebars.

The panel exposes one unified, non-versioned feature surface.  Contextual rows
only appear when their effect is active, never because of a compatibility mode.
"""

import bpy

from .operators import assets
from .properties import V3_STAGE_ITEMS


def _draw(layout, context):
    s = context.scene.pixelatorplus

    box = layout.box()
    box.label(text="Style Recipes", icon="PRESET")
    row = box.row(align=True)
    row.prop(s, "style_preset", text="")
    row.operator("pixelatorplus.load_style_preset", text="Load")
    box.operator("pixelatorplus.surprise_style", text="Surprise Me", icon="FILE_REFRESH")
    box.label(text="Starting points — every setting remains editable.", icon="INFO")

    row = layout.row(align=True)
    row.prop(s, "random_seed")
    row.operator("pixelatorplus.randomize_seed", text="", icon="FILE_REFRESH")

    row = layout.row(align=True)
    row.prop(s, "input_image")
    row.operator("pixelatorplus.grab_basecolor", text="", icon="MATERIAL")

    row = layout.row(align=True)
    row.prop(s, "live_preview")
    if s.live_preview:
        row.prop(s, "preview_max_size", text="Max")
        row.prop(s, "preview_cache_enabled", text="Cache")
        layout.prop(s, "preview_mode")

    layout.operator("pixelatorplus.apply", icon="IMAGE_DATA")
    if s.last_output_name:
        layout.label(text=f"Last output: {s.last_output_name}", icon="CHECKMARK")

    # -- Dimensions ----------------------------------------------------------
    box = layout.box()
    box.label(text="Dimensions", icon="MESH_GRID")
    box.prop(s, "use_separate_pixel_count")
    if s.use_separate_pixel_count:
        row = box.row(align=True)
        row.prop(s, "pixel_count_x")
        row.prop(s, "pixel_count_y")
    else:
        box.prop(s, "square_pixel_count")

    # -- Pixelate Style ------------------------------------------------------
    box = layout.box()
    box.label(text="Pixelate Style", icon="RENDER_STILL")
    box.prop(s, "downscale_mode")
    box.prop(s, "scale_algorithm")
    if s.scale_algorithm in ("SCALE2X", "SCALE3X", "CLEANEDGE"):
        box.prop(s, "scale_tolerance", slider=True)
    elif s.scale_algorithm == "CONTENT_AWARE":
        box.prop(s, "content_aware_factor")
        box.prop(s, "content_aware_max_dimension")
        box.prop(s, "content_aware_seam_mode")
    box.prop(s, "filter_preview")
    if s.filter_preview != "NONE":
        box.label(text="Preview only — never exported", icon="ERROR")

    # -- Dithering -----------------------------------------------------------
    box = layout.box()
    box.label(text="Dithering", icon="TEXTURE")
    box.prop(s, "dither_type")
    if s.dither_type != "NONE":
        box.prop(s, "dither_strategy")
        if s.dither_strategy == "PALETTE_THRESHOLD":
            box.prop(s, "palette_dither_contrast", slider=True)
            box.prop(s, "palette_dither_invert")
        if s.dither_type == "CUSTOM":
            box.prop(s, "custom_dither_image")
            box.prop(s, "custom_dither_resolution")
        elif s.dither_type in ("CUSTOM_8X8", "CUSTOM_16X16"):
            label = "8x8 Custom Dither" if s.dither_type == "CUSTOM_8X8" else "16x16 Custom Dither"
            box.prop(s, "custom_dither_image", text=label)
        box.prop(s, "lock_dither_to_grid")
        box.prop(s, "dither_blend_mode")
        box.prop(s, "use_gray_dither")
        box.prop(s, "dither_strength", slider=True)
        box.prop(s, "dither_saturation", slider=True)
        box.prop(s, "dither_mask_type")
        if s.dither_mask_type != "NONE":
            mt = s.dither_mask_type
            if mt == "CUSTOM":
                box.prop(s, "custom_mask_image")
            elif mt == "LUMINANCE":
                row = box.row(align=True)
                row.prop(s, "dither_mask_lum_low", slider=True)
                row.prop(s, "dither_mask_lum_high", slider=True)
            elif mt == "SATURATION":
                row = box.row(align=True)
                row.prop(s, "dither_mask_sat_low", slider=True)
                row.prop(s, "dither_mask_sat_high", slider=True)
            elif mt == "GRADIENT":
                box.prop(s, "dither_mask_gradient_angle")
            box.prop(s, "dither_cutoff", slider=True)
            box.prop(s, "dither_mask_gamma")
            if mt in ("EDGES", "FLATS"):  # frequency weights shape edges only
                box.prop(s, "show_mask_controls")
                if s.show_mask_controls:
                    col = box.column(align=True)
                    for key in ("huge", "big", "large", "medium", "fine", "sharp", "pixel_perfect"):
                        col.prop(s, key, slider=True)
            row = box.row(align=True)
            row.prop(s, "dither_mask_invert")
            row.prop(s, "dither_mask_blur")
        box.prop(s, "preview_dither_mask")

    # -- Quantization --------------------------------------------------------
    box = layout.box()
    box.label(text="Quantization", icon="COLOR")
    box.prop(s, "quantize_type")
    qt = s.quantize_type
    pbox = box.box()
    pbox.prop(s, "posterize_enabled")
    if s.posterize_enabled:
        pbox.prop(s, "posterize_levels")
        pbox.prop(s, "posterize_range_mode")
        if s.posterize_range_mode != "FULL":
            row = pbox.row(align=True)
            row.prop(s, "posterize_range_low", slider=True)
            row.prop(s, "posterize_range_high", slider=True)
        if s.posterize_range_mode == "PERCENTILE":
            row = pbox.row(align=True)
            row.prop(s, "posterize_percentile_low")
            row.prop(s, "posterize_percentile_high")
        row = pbox.row(align=True)
        row.prop(s, "posterize_gamma")
        row.prop(s, "posterize_mix", slider=True)
        pbox.prop(s, "posterize_channel_mask")
        pbox.prop(s, "posterize_alpha_policy")
        pbox.prop(s, "range_map_image")
    if qt == "CUSTOM_PALETTE":
        box.prop(s, "use_pixelated_for_quantize")
        box.prop(s, "initialize_mode")
        box.prop(s, "color_mode")
        box.prop(s, "apply_palette_mode")
        box.prop(s, "gamma")
        box.prop(s, "force_colors")
        box.prop(s, "palette_extract_method")
        box.prop(s, "palette_sort_mode")
        box.prop(s, "palette_shift")
        box.prop(s, "palette_trim")
        box.prop(s, "palette_replace_image")
        if s.palette_replace_image:
            box.prop(s, "palette_replace_threshold", slider=True)
        box.prop(s, "quantize_quality")
        box.prop(s, "k_num_colors")
        box.prop(s, "use_explicit_quantize_seed")
        if s.use_explicit_quantize_seed:
            box.prop(s, "quantize_seed")
        box.prop(s, "use_chroma_importance")
        if s.use_chroma_importance:
            box.prop(s, "chroma_importance", slider=True)
        box.prop(s, "output_palette")
        box.prop(s, "output_lut")
        if s.output_lut:
            box.label(text="4K LUT generation uses substantial memory.", icon="INFO")
    elif qt == "PER_CHANNEL":
        box.prop(s, "use_range_adaptive")
        box.prop(s, "quantize_colors_or_bits")
        if s.quantize_colors_or_bits == "BITS":
            box.prop(s, "quantize_bits")
        else:
            box.prop(s, "quantize_colors")
    elif qt == "LUT":
        box.prop(s, "lut")
        if s.lut == "CUSTOM_LUT":
            box.prop(s, "custom_lut_image")
        elif s.lut == "CUBE_LUT":
            box.prop(s, "cube_lut_path")
            box.prop(s, "cube_lut_interpolation")
            box.prop(s, "cube_lut_strength", slider=True)
        elif s.lut == "CUSTOM_PALETTE":
            box.prop(s, "custom_palette_image")
        if s.lut != "CUSTOM_LUT":
            box.prop(s, "apply_palette_mode")
        box.prop(s, "output_default_lut")
        if s.output_default_lut:
            box.label(text="4K LUT generation uses substantial memory.", icon="INFO")
    if qt != "NONE":
        box.prop(s, "diffusion")
        if s.diffusion != "NONE":
            box.prop(s, "diffusion_strength", slider=True)
            box.prop(s, "diffusion_serpentine")
            box.label(text="Diffusion snaps at pixel-grid resolution.", icon="INFO")

    # -- Display finishing --------------------------------------------------
    box = layout.box()
    box.label(text="Display Finish", icon="SHADING_RENDERED")
    box.prop(s, "finish_enabled")
    if s.finish_enabled:
        box.prop(s, "finish_brightness", slider=True)
        box.prop(s, "finish_contrast", slider=True)
        box.prop(s, "finish_exposure", slider=True)
        box.prop(s, "finish_saturation", slider=True)
        row = box.row(align=True)
        row.prop(s, "finish_grain", slider=True)
        row.prop(s, "finish_grain_saturation", slider=True)
        box.prop(s, "finish_grain_brightness", slider=True)
        row = box.row(align=True)
        row.prop(s, "finish_scanline_strength", slider=True)
        row.prop(s, "finish_scanline_size")
        row = box.row(align=True)
        row.prop(s, "finish_scanline_axis")
        row.prop(s, "finish_scanline_invert")
        row = box.row(align=True)
        row.prop(s, "finish_vignette_strength", slider=True)
        row.prop(s, "finish_vignette_roundness")
        box.prop(s, "finish_chromatic_aberration", slider=True)
        box.prop(s, "finish_mask_type")
        box.prop(s, "finish_mask_mix", slider=True)
        box.prop(s, "finish_mask_invert")
        box.prop(s, "finish_channel_mask")

    # -- Output & extras ------------------------------------------------------
    box = layout.box()
    box.label(text="Output", icon="FILE_IMAGE")
    box.operator("pixelatorplus.export_output", icon="EXPORT")
    row = box.row(align=True)
    row.operator("pixelatorplus.export_palette", icon="COLOR")
    row.operator("pixelatorplus.export_lut", icon="RENDERLAYERS")
    row = box.row(align=True)
    row.operator("pixelatorplus.export_palette_json", text="Palette JSON", icon="TEXT")
    row.operator("pixelatorplus.export_cube", text=".cube LUT", icon="IMAGE_RGB")
    box.operator("pixelatorplus.material_hookup", icon="MATERIAL")


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
            # Files saved before a stage existed have an incomplete stack.
            layout.label(text="The stage stack is incomplete.", icon="ERROR")
            layout.operator("pixelatorplus.init_stage_stack", text="Repair Stage Stack",
                            icon="FILE_REFRESH")
        return
    for item in stack:
        row = layout.row(align=True)
        # Pixelate builds the grid every later stage depends on.
        row.enabled = item.stage_id != "pixelate"
        row.prop(item, "enabled", text=labels[item.stage_id])


def _draw_advanced(layout, context):
    """Draw the additive V3 controls without changing the normal workflow."""
    s = context.scene.pixelatorplus

    box = layout.box()
    box.label(text="V3 staged pipeline adapter is active", icon="INFO")
    box.label(text="Existing settings and presets remain compatible.")

    box = layout.box()
    box.label(text="Plan Snapshot", icon="FILE_BLEND")
    row = box.row(align=True)
    row.operator("pixelatorplus.snapshot_plan", text="Capture / Migrate", icon="DUPLICATE")
    row.operator("pixelatorplus.restore_plan", text="Restore", icon="LOOP_BACK")
    if s.v3_plan_fingerprint:
        box.label(text=f"Stored plan: {s.v3_plan_fingerprint}", icon="CHECKMARK")
    else:
        box.label(text="No snapshot yet — image pins stay linked separately.", icon="INFO")

    box = layout.box()
    box.label(text="PixelatorPlus Creative Core", icon="COLORSET_04_VEC")
    box.prop(s.v3, "palette_lock")
    if s.v3.palette_lock == "PALETTE_TINT":
        box.prop(s.v3, "palette_lock_strength", slider=True)
    box.prop(s.v3, "grid_coherence")
    box.label(text="Palette Lock and Grid Coherence are PixelatorPlus-native features.", icon="INFO")

    stage_box = layout.box()
    stage_box.label(text="V3 Stage Stack (dependency order)", icon="NODETREE")
    _draw_stage_stack(stage_box, s.v3.stage_stack)
    stage_box.label(text="The stack is intentionally dependency-ordered in v3.0.", icon="INFO")

    box = layout.box()
    box.label(text="Stage Controls", icon="NODETREE")
    box.prop(s, "posterize_enabled")
    if s.posterize_enabled:
        box.prop(s, "posterize_levels")
        box.prop(s, "posterize_range_mode")
        box.prop(s, "posterize_gamma")
        box.prop(s, "posterize_mix", slider=True)
        box.prop(s, "posterize_channel_mask")
        box.prop(s, "range_map_image")
    box.prop(s, "scale_algorithm")
    if s.scale_algorithm in ("SCALE2X", "SCALE3X", "CLEANEDGE"):
        box.prop(s, "scale_tolerance", slider=True)
    elif s.scale_algorithm == "CONTENT_AWARE":
        box.prop(s, "content_aware_factor")
        box.prop(s, "content_aware_max_dimension")
        box.prop(s, "content_aware_seam_mode")
    box.prop(s, "dither_strategy")
    if s.dither_strategy == "PALETTE_THRESHOLD":
        box.prop(s, "palette_dither_contrast", slider=True)
        box.prop(s, "palette_dither_invert")
    box.prop(s, "diffusion")
    if s.diffusion != "NONE":
        box.prop(s, "diffusion_strength", slider=True)
        box.prop(s, "diffusion_serpentine")

    box = layout.box()
    box.label(text="Palette Workflow", icon="COLORSET_04_VEC")
    box.prop(s, "strength_map_image")
    box.prop(s, "threshold_map_image")
    box.prop(s, "palette_extract_method")
    box.prop(s, "palette_sort_mode")
    box.prop(s, "palette_shift")
    box.prop(s, "palette_trim")
    box.prop(s, "palette_replace_image")
    if s.palette_replace_image:
        box.prop(s, "palette_replace_threshold", slider=True)
    box.label(text="Used by generated/custom-palette modes.", icon="INFO")

    box = layout.box()
    box.label(text="Portable LUT", icon="IMAGE_RGB")
    box.prop(s, "lut")
    if s.lut == "CUBE_LUT":
        box.prop(s, "cube_lut_path")
        box.prop(s, "cube_lut_interpolation")
        box.prop(s, "cube_lut_strength", slider=True)
    else:
        box.label(text="Choose Portable .cube to enable its controls.", icon="INFO")

    box = layout.box()
    box.label(text="Display Finish", icon="SHADING_RENDERED")
    box.prop(s, "finish_enabled")
    if s.finish_enabled:
        for name in ("finish_brightness", "finish_contrast", "finish_exposure", "finish_saturation"):
            box.prop(s, name, slider=True)
        box.prop(s, "finish_grain", slider=True)
        box.prop(s, "finish_grain_brightness", slider=True)
        box.prop(s, "finish_grain_saturation", slider=True)
        box.prop(s, "finish_scanline_strength", slider=True)
        row = box.row(align=True)
        row.prop(s, "finish_scanline_size")
        row.prop(s, "finish_scanline_axis")
        row.prop(s, "finish_scanline_invert")
        box.prop(s, "finish_vignette_strength", slider=True)
        box.prop(s, "finish_vignette_roundness")
        box.prop(s, "finish_chromatic_aberration", slider=True)
        box.prop(s, "finish_mask_type")
        box.prop(s, "finish_mask_mix", slider=True)
        box.prop(s, "finish_mask_invert")
        box.prop(s, "finish_channel_mask")


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
        s = context.scene.pixelatorplus
        _draw(self.layout, context)
        box = self.layout.box()
        box.label(text="Exact Compositor Output", icon="NODE_COMPOSITING")
        box.label(text="Bakes the full PixelatorPlus pipeline into an Image node.")
        row = box.row(align=True)
        row.operator("pixelatorplus.bake_compositor_input", icon="IMAGE_DATA")
        row.operator("pixelatorplus.bake_compositor_render", icon="RENDER_RESULT")
        box.operator("pixelatorplus.connect_baked_output", text="Connect Baked Output to Compositor",
                     icon="NODE_COMPOSITING")
        box.prop(s, "auto_bake_render")
        if s.auto_bake_render:
            box.prop(s, "auto_connect_baked_output")
            if s.auto_connect_baked_output:
                box.label(text="Replaces the current compositor image link after each render.", icon="ERROR")

        box = self.layout.box()
        box.label(text="Compositor Asset Library", icon="ASSET_MANAGER")
        if assets.compositor_assets_registered():
            box.label(text="PixelatorPlus / Compositor is ready", icon="CHECKMARK")
        else:
            box.operator("pixelatorplus.install_compositor_assets", text="Add to Asset Libraries",
                         icon="ASSET_MANAGER")
            box.label(text="Adds one PixelatorPlus entry to Blender preferences.", icon="INFO")
        box.label(text="Drag native Pixelate and Posterize presets from the Asset Shelf.")


class PIXELATORPLUS_PT_advanced_image_editor(bpy.types.Panel):
    """Collapsed additive V3 panel for advanced image-editor workflows."""

    bl_idname = "PIXELATORPLUS_PT_advanced_image_editor"
    bl_parent_id = "PIXELATORPLUS_PT_image_editor"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "PixelatorPlus"
    bl_label = "Advanced (V3)"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        _draw_advanced(self.layout, context)


class PIXELATORPLUS_PT_advanced_compositor(bpy.types.Panel):
    """Collapsed additive V3 panel for advanced compositor workflows."""

    bl_idname = "PIXELATORPLUS_PT_advanced_compositor"
    bl_parent_id = "PIXELATORPLUS_PT_compositor"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "PixelatorPlus"
    bl_label = "Advanced (V3)"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return getattr(context.space_data, "tree_type", None) == "CompositorNodeTree"

    def draw(self, context):
        _draw_advanced(self.layout, context)


classes = (
    PIXELATORPLUS_PT_image_editor,
    PIXELATORPLUS_PT_compositor,
    PIXELATORPLUS_PT_advanced_image_editor,
    PIXELATORPLUS_PT_advanced_compositor,
)


register, unregister = bpy.utils.register_classes_factory(classes)
