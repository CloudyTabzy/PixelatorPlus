"""Material hookup: wire the last PixelatorPlus output into the active object's
material as an Image Texture node feeding Base Color (spec section 9, output
stage). Creates a material if the active object has none.
"""

import bpy


class PIXELATORPLUS_OT_material_hookup(bpy.types.Operator):
    """Plug the last PixelatorPlus output into the active material as Base Color"""

    bl_idname = "pixelatorplus.material_hookup"
    bl_label = "Wire Output to Active Material"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        s = context.scene.pixelatorplus if context.scene else None
        obj = context.active_object
        return (
            obj is not None
            # Empties, lights, cameras, etc. have no material slots to wire.
            and hasattr(obj.data, "materials")
            and s is not None
            and bool(s.last_output_name)
            and bpy.data.images.get(s.last_output_name) is not None
        )

    def execute(self, context):
        s = context.scene.pixelatorplus
        image = bpy.data.images[s.last_output_name]
        obj = context.active_object

        mat = obj.active_material
        if mat is None:
            mat = bpy.data.materials.new(name=f"{obj.name} PixelatorPlus")
            if obj.material_slots:
                obj.material_slots[0].material = mat
            else:
                obj.data.materials.append(mat)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        tex = next(
            (n for n in nodes if n.bl_idname == "ShaderNodeTexImage" and n.image == image),
            None,
        )
        if tex is None:
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = image
            tex.location = (-400, 300)
        # Pixel art wants hard texel edges
        tex.interpolation = "Closest"

        bsdf = next((n for n in nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
        if bsdf is None:
            bsdf = nodes.new("ShaderNodeBsdfPrincipled")
            bsdf.location = (0, 300)
            out_node = next(
                (n for n in nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None
            )
            if out_node is None:
                out_node = nodes.new("ShaderNodeOutputMaterial")
                out_node.location = (300, 300)
            links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
        base_color = bsdf.inputs["Base Color"]
        # Re-running this operator must make the generated output authoritative
        # instead of leaving an older material link in place.
        for link in tuple(base_color.links):
            links.remove(link)
        links.new(tex.outputs["Color"], base_color)

        self.report({"INFO"}, f"'{image.name}' wired into material '{mat.name}'")
        return {"FINISHED"}


classes = (PIXELATORPLUS_OT_material_hookup,)


register, unregister = bpy.utils.register_classes_factory(classes)
