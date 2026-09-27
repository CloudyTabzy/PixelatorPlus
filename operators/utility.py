"""Small utility operators.

PIXELATORPLUS_OT_randomize_seed — the 'Random' button next to Seed (screenshot /
spec: $randomseed).
PIXELATORPLUS_OT_grab_basecolor — pull the Base Color image texture from the active
object's material into the Input pin (Painter-style channel workflow).
"""

import random

import bpy


class PIXELATORPLUS_OT_randomize_seed(bpy.types.Operator):
    """Randomize the seed ($randomseed)"""

    bl_idname = "pixelatorplus.randomize_seed"
    bl_label = "Randomize Seed"

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        context.scene.pixelatorplus.random_seed = random.randint(0, 9999)
        return {"FINISHED"}


class PIXELATORPLUS_OT_grab_basecolor(bpy.types.Operator):
    """Use the active material's Base Color texture as the input image"""

    bl_idname = "pixelatorplus.grab_basecolor"
    bl_label = "Grab Base Color Texture"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.scene is not None
            and obj is not None
            and obj.active_material is not None
            and obj.active_material.use_nodes
        )

    def execute(self, context):
        s = context.scene.pixelatorplus
        mat = context.active_object.active_material
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeBsdfPrincipled":
                link = node.inputs["Base Color"].links
                if link and link[0].from_node.bl_idname == "ShaderNodeTexImage":
                    image = link[0].from_node.image
                    if image is not None:
                        s.input_image = image
                        self.report({"INFO"}, f"Input set to '{image.name}'")
                        return {"FINISHED"}
        # fall back to any image texture in the material
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeTexImage" and node.image is not None:
                s.input_image = node.image
                self.report({"INFO"}, f"Input set to '{node.image.name}' (first image texture)")
                return {"FINISHED"}
        self.report({"WARNING"}, "No image texture found in the active material")
        return {"CANCELLED"}


classes = (PIXELATORPLUS_OT_randomize_seed, PIXELATORPLUS_OT_grab_basecolor)


register, unregister = bpy.utils.register_classes_factory(classes)
