"""PIXELATORPLUS_OT_process_render_result: copy the compositor's Render Result into
a regular image, feed it through the PixelatorPlus pipeline, and produce the usual
'<name> [PixelatorPlus]' output. Shown in the compositor sidebar panel.
"""

import bpy

from .apply import apply_settings, array_to_image, image_to_array

RENDER_COPY_NAME = "Render Result (PixelatorPlus Input)"


def render_result_to_input(scene):
    """Copy Blender's ephemeral Render Result into a regular image datablock."""
    rr = bpy.data.images.get("Render Result")
    if rr is None:
        raise ValueError("Render Result image not found")
    copy = array_to_image(image_to_array(rr), RENDER_COPY_NAME)
    scene.pixelatorplus.input_image = copy
    return copy


def process_render_result(scene):
    """Run the exact pipeline against the current Render Result."""
    return apply_settings(scene, render_result_to_input(scene))


class PIXELATORPLUS_OT_process_render_result(bpy.types.Operator):
    """Copy the Render Result, set it as PixelatorPlus input, and apply"""

    bl_idname = "pixelatorplus.process_render_result"
    bl_label = "PixelatorPlus Render Result"

    @classmethod
    def poll(cls, context):
        rr = bpy.data.images.get("Render Result")
        return (
            context.scene is not None
            and rr is not None
            and rr.size[0] > 0
            and rr.size[1] > 0
        )

    def execute(self, context):
        try:
            out, result = process_render_result(context.scene)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        gw, gh = result["grid"]
        self.report({"INFO"}, f"PixelatorPlus: {gw}x{gh} grid -> '{out.name}'")
        return {"FINISHED"}


classes = (PIXELATORPLUS_OT_process_render_result,)


register, unregister = bpy.utils.register_classes_factory(classes)
