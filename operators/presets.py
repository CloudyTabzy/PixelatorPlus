"""Operators for loading and playfully varying editable style recipes."""

import random

import bpy

from ..presets import preset_info, preset_values, surprise_values
from ..properties import ensure_v3_stages


def _apply_values(settings, values):
    """Assign a validated recipe dict to a PixelatorPlus PropertyGroup."""
    for name, value in values.items():
        if name.startswith("v3_"):
            setattr(settings.v3, name[3:], value)
            continue
        if not hasattr(settings, name):
            raise AttributeError(f"Style recipe refers to unknown setting '{name}'")
        setattr(settings, name, value)
    for stage in ensure_v3_stages(settings):
        stage.enabled = True


class PIXELATORPLUS_OT_load_style_preset(bpy.types.Operator):
    """Load the selected style recipe as fully editable settings"""

    bl_idname = "pixelatorplus.load_style_preset"
    bl_label = "Load Style Recipe"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and hasattr(context.scene, "pixelatorplus")

    def execute(self, context):
        settings = context.scene.pixelatorplus
        try:
            info = preset_info(settings.style_preset)
            _apply_values(settings, preset_values(settings.style_preset))
        except (AttributeError, KeyError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Loaded '{info['name']}' — every setting remains editable")
        return {"FINISHED"}


class PIXELATORPLUS_OT_surprise_style(bpy.types.Operator):
    """Choose a style recipe and add safe, recipe-aware variation"""

    bl_idname = "pixelatorplus.surprise_style"
    bl_label = "Surprise Me"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and hasattr(context.scene, "pixelatorplus")

    def execute(self, context):
        settings = context.scene.pixelatorplus
        try:
            identifier, values = surprise_values(random.SystemRandom())
            settings.style_preset = identifier
            _apply_values(settings, values)
            info = preset_info(identifier)
        except (AttributeError, KeyError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Surprise: {info['name']} with a fresh variation")
        return {"FINISHED"}


classes = (PIXELATORPLUS_OT_load_style_preset, PIXELATORPLUS_OT_surprise_style)


register, unregister = bpy.utils.register_classes_factory(classes)
