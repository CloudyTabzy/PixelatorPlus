"""Freeze the current palette so every later frame or image reuses it.

Generating a palette per image makes animation frames flicker: k-means finds
slightly different colors every frame.  Freezing runs the exact pipeline
once, stores the resulting palette as an image, and switches quantization to
**Lookup Table → Custom Palette** with that image, so all subsequent Apply,
preview, and render bakes map onto identical colors.  The generated-palette
settings stay stored and can be re-selected at any time.
"""

import bpy
import numpy as np

from ..core.pipeline import PipelineError
from .apply import apply_settings, array_to_image


def freeze_palette(scene):
    """Apply once, then lock quantization to the resulting palette image.

    Returns the palette image.  Raises ``ValueError`` when the run produced
    no palette (for example, the Quantize stage is disabled in the stack).
    """
    settings = scene.pixelatorplus
    if any(
        stage.stage_id == "quantize" and not stage.enabled
        for stage in settings.v3.stage_stack
    ):
        raise ValueError(
            "The Quantize stage is disabled; enable it before freezing a palette"
        )
    _output, result = apply_settings(scene)
    # The palette before Palette Tint: tinting is re-applied on every run,
    # so freezing the tinted colors would tint twice.
    colors = result.get("source_palette_colors")
    if colors is None:
        raise ValueError(
            "No palette was generated to freeze; check that the Quantize stage "
            "is enabled"
        )
    colors = np.asarray(colors, dtype=np.float32)[:, :3]
    swatch = np.concatenate([colors, np.ones((colors.shape[0], 1), np.float32)], axis=-1)
    name = f"{settings.input_image.name} [PixelatorPlus Frozen Palette]"
    image = array_to_image(swatch[None, :, :], name)
    # Keep the palette with the .blend even while nothing references it.
    image.use_fake_user = True
    settings.custom_palette_image = image
    settings.quantize_type = "LUT"
    settings.lut = "CUSTOM_PALETTE"
    return image


class PIXELATORPLUS_OT_freeze_palette(bpy.types.Operator):
    """Apply once and reuse its palette for every later frame (prevents palette flicker)"""

    bl_idname = "pixelatorplus.freeze_palette"
    bl_label = "Freeze Palette"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.pixelatorplus if context.scene else None
        return bool(
            settings and settings.input_image
            # Only generated palettes vary between frames.
            and settings.quantize_type == "CUSTOM_PALETTE"
            and not any(
                stage.stage_id == "quantize" and not stage.enabled
                for stage in settings.v3.stage_stack
            )
        )

    def execute(self, context):
        try:
            image = freeze_palette(context.scene)
        except (PipelineError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Froze {image.size[0]} colors into '{image.name}'; quantization now uses it",
        )
        return {"FINISHED"}


classes = (PIXELATORPLUS_OT_freeze_palette,)

register, unregister = bpy.utils.register_classes_factory(classes)
