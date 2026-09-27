"""Exact PixelatorPlus output baked into a Blender compositor image node.

The bundled asset catalog contains fast, fully editable native-node presets.
This module is the complementary final-quality path: it runs the add-on's
NumPy pipeline, then updates one clearly named Image node in the scene's
compositor tree.  A compositor node group cannot execute Python while Blender
evaluates the graph, so baking is explicit and never pretends otherwise.
"""

import bpy
from bpy.app.handlers import persistent
try:
    from bpy_extras.node_utils import connect_sockets
except ImportError:
    connect_sockets = None

from ..core.pipeline import PipelineError
from .apply import apply_settings
from .render_result import process_render_result

BAKED_NODE_FLAG = "pixelatorplus_baked_output"
BAKED_NODE_NAME = "PixelatorPlus Baked Output"


def _compositor_tree(scene):
    """Get the compositor tree across Blender 4.2 through 5.2+.

    Blender 5.2 removes the legacy ``Scene.node_tree`` compositor access.  The
    modern ``compositing_node_group`` is therefore preferred whenever it is
    available; the fallback remains only for supported 4.2-era files.
    """
    scene.use_nodes = True
    tree = getattr(scene, "compositing_node_group", None)
    if tree is None:
        tree = getattr(scene, "node_tree", None)
    if tree is not None:
        return tree

    tree = bpy.data.node_groups.new(f"{scene.name} Compositor", "CompositorNodeTree")
    try:
        scene.compositing_node_group = tree
    except AttributeError:
        # On Blender 4.2 the legacy scene-owned tree is created by use_nodes.
        tree = getattr(scene, "node_tree", None)
    if tree is None:
        raise RuntimeError("could not create a scene compositor node tree")
    return tree


def _existing_compositor_tree(scene):
    """The scene's compositor tree, or ``None``; never creates one."""
    return getattr(scene, "compositing_node_group", None) or getattr(scene, "node_tree", None)


def _baked_nodes(tree):
    return [node for node in tree.nodes if node.get(BAKED_NODE_FLAG)]


def baked_output_drives_compositor(scene):
    """True when the static baked Image node is linked into the compositor.

    Renders then return that fixed image for every frame, so frame-by-frame
    work (sprite sheets) must bypass compositing.  Never creates a tree.
    """
    tree = _existing_compositor_tree(scene)
    if tree is None:
        return False
    return any(any(output.links for output in node.outputs) for node in _baked_nodes(tree))


# Links from the baked Image node lifted for the render in progress, per
# scene: (baked node name, output index, target node name, input index).
_lifted_links = {}


def _lift_baked_links(scene):
    """Disconnect the baked node for one render, remembering its links.

    A connected baked node is a static image: left in place, it would feed
    the previous bake into the new render instead of the fresh pixels.
    """
    tree = _existing_compositor_tree(scene)
    if tree is None:
        return
    lifted = []
    for node in _baked_nodes(tree):
        for out_index, output in enumerate(node.outputs):
            for link in tuple(output.links):
                target = link.to_node
                in_index = next(i for i, socket in enumerate(target.inputs)
                                if socket == link.to_socket)
                lifted.append((node.name, out_index, target.name, in_index))
                tree.links.remove(link)
    if lifted:
        _lifted_links[scene.name] = lifted


def _restore_baked_links(scene):
    """Reconnect links lifted by :func:`_lift_baked_links` (no-op otherwise)."""
    lifted = _lifted_links.pop(scene.name, None)
    tree = _existing_compositor_tree(scene)
    if not lifted or tree is None:
        return
    for node_name, out_index, target_name, in_index in lifted:
        node, target = tree.nodes.get(node_name), tree.nodes.get(target_name)
        if node is not None and target is not None:
            tree.links.new(node.outputs[out_index], target.inputs[in_index])


def _baked_output_node(scene, image):
    """Create or update the one Image node that represents exact output."""
    tree = _compositor_tree(scene)
    nodes = tree.nodes
    node = next((item for item in nodes if item.get(BAKED_NODE_FLAG)), None)
    if node is None:
        node = nodes.new("CompositorNodeImage")
        node.name = BAKED_NODE_NAME
        node.label = "PixelatorPlus Exact Baked Output"
        node[BAKED_NODE_FLAG] = True
        composite = next(
            (item for item in nodes if item.bl_idname == "CompositorNodeComposite"),
            None,
        )
        node.location = ((composite.location.x - 280) if composite else 300,
                         composite.location.y if composite else 0)
    node.image = image
    for item in nodes:
        item.select = False
    node.select = True
    nodes.active = node
    return node


def _compositor_output_node(tree):
    """Find/create the final compositor output in Blender 4.2 through 5.2+."""
    output = next(
        (item for item in tree.nodes if item.bl_idname == "CompositorNodeComposite"),
        None,
    )
    if output is not None:
        return output
    if hasattr(bpy.types, "CompositorNodeComposite"):
        return tree.nodes.new("CompositorNodeComposite")

    # Blender 5.0+ stores the scene compositor as a node group. Its Group
    # Output replaces the older Composite node and needs an Image interface
    # socket. Blender 5.2 removes the legacy Composite node entirely.
    has_image_output = any(
        getattr(item, "in_out", None) == "OUTPUT" and item.name == "Image"
        for item in tree.interface.items_tree
    )
    if not has_image_output:
        tree.interface.new_socket(
            name="Image", in_out="OUTPUT", socket_type="NodeSocketColor"
        )
    output = next(
        (item for item in tree.nodes if item.bl_idname == "NodeGroupOutput"),
        None,
    )
    return output or tree.nodes.new("NodeGroupOutput")


def _wire_to_composite(scene, node):
    """Make the exact baked image the explicit final compositor output."""
    tree = _compositor_tree(scene)
    links = tree.links
    output = _compositor_output_node(tree)
    if output.bl_idname == "CompositorNodeComposite":
        output.location = (node.location.x + 280, node.location.y)
    image_input = output.inputs["Image"]
    for link in tuple(image_input.links):
        links.remove(link)
    if connect_sockets is not None:
        link = connect_sockets(image_input, node.outputs[0])
    else:
        link = None
    if link is None:
        link = links.new(node.outputs[0], image_input)
    if link is None:
        raise RuntimeError("could not connect the baked image to compositor output")
    return output


def bake_input_to_compositor(scene, source_image=None, connect=False):
    """Run exact settings against Input and place the result in the compositor."""
    output, result = apply_settings(scene, source_image)
    node = _baked_output_node(scene, output)
    if connect:
        _wire_to_composite(scene, node)
    return output, result, node


def bake_render_result_to_compositor(scene, connect=False):
    """Run exact settings against Render Result and place it in the compositor."""
    output, result = process_render_result(scene)
    node = _baked_output_node(scene, output)
    if connect:
        _wire_to_composite(scene, node)
    return output, result, node


def _auto_connecting(scene):
    settings = getattr(scene, "pixelatorplus", None)
    return bool(settings and settings.auto_bake_render and settings.auto_connect_baked_output)


@persistent
def _render_init(scene):
    """Keep an auto-connected previous bake out of the render that starts now."""
    if not _auto_connecting(scene):
        return
    try:
        _lift_baked_links(scene)
    except Exception as exc:
        # A render handler must never raise into Blender's render pipeline.
        print(f"PixelatorPlus could not detach the baked output: {exc}")


@persistent
def _render_cancel(scene):
    try:
        _restore_baked_links(scene)
    except Exception as exc:
        print(f"PixelatorPlus could not reconnect the baked output: {exc}")


@persistent
def _render_complete(scene):
    """Optional final-quality bake after Blender finishes a render."""
    try:
        _restore_baked_links(scene)
    except Exception as exc:
        print(f"PixelatorPlus could not reconnect the baked output: {exc}")
    settings = getattr(scene, "pixelatorplus", None)
    if settings is None or not settings.auto_bake_render:
        return
    try:
        bake_render_result_to_compositor(
            scene, connect=settings.auto_connect_baked_output
        )
    except Exception as exc:
        # A render handler must never raise into Blender's render pipeline.
        print(f"PixelatorPlus automatic compositor bake failed: {exc}")


class PIXELATORPLUS_OT_bake_compositor_input(bpy.types.Operator):
    """Bake the exact PixelatorPlus Input result to a compositor Image node"""

    bl_idname = "pixelatorplus.bake_compositor_input"
    bl_label = "Bake Input to Compositor"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.scene.pixelatorplus.input_image)

    def execute(self, context):
        try:
            output, result, node = bake_input_to_compositor(context.scene)
        except (PipelineError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        gw, gh = result["grid"]
        self.report({"INFO"}, f"{gw}x{gh} exact output baked to '{node.name}' ({output.name})")
        return {"FINISHED"}


class PIXELATORPLUS_OT_bake_compositor_render(bpy.types.Operator):
    """Bake the exact Render Result to a compositor Image node"""

    bl_idname = "pixelatorplus.bake_compositor_render"
    bl_label = "Bake Render Result to Compositor"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        rr = bpy.data.images.get("Render Result")
        return bool(context.scene and rr and rr.size[0] > 0 and rr.size[1] > 0)

    def execute(self, context):
        try:
            output, result, node = bake_render_result_to_compositor(context.scene)
        except (PipelineError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        gw, gh = result["grid"]
        self.report({"INFO"}, f"{gw}x{gh} exact render baked to '{node.name}' ({output.name})")
        return {"FINISHED"}


class PIXELATORPLUS_OT_connect_baked_output(bpy.types.Operator):
    """Connect the exact baked output to the scene compositor output"""

    bl_idname = "pixelatorplus.connect_baked_output"
    bl_label = "Connect Baked Output to Compositor"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.pixelatorplus if context.scene else None
        return bool(settings and settings.last_output_name
                    and bpy.data.images.get(settings.last_output_name))

    def execute(self, context):
        image = bpy.data.images[context.scene.pixelatorplus.last_output_name]
        node = _baked_output_node(context.scene, image)
        _wire_to_composite(context.scene, node)
        self.report({"INFO"}, f"'{node.name}' connected to compositor output")
        return {"FINISHED"}


classes = (
    PIXELATORPLUS_OT_bake_compositor_input,
    PIXELATORPLUS_OT_bake_compositor_render,
    PIXELATORPLUS_OT_connect_baked_output,
)


_register_classes, _unregister_classes = bpy.utils.register_classes_factory(classes)


_HANDLERS = (
    ("render_init", _render_init),
    ("render_cancel", _render_cancel),
    ("render_complete", _render_complete),
)


def register():
    _register_classes()
    for name, handler in _HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if handler not in handlers:
            handlers.append(handler)


def unregister():
    for name, handler in _HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if handler in handlers:
            handlers.remove(handler)
    _lifted_links.clear()
    _unregister_classes()
