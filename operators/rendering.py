"""Render helpers: temporary scene settings, PNG stills, and ID maps.

Everything here changes the user's scene only through ``TemporarySettings``,
which records each property the first time it changes and restores it later.
Restoring runs in the order properties were first changed; callers rely on
that for Blender 5.x image formats, where ``media_type`` must be set (and
restored) before ``file_format``.

Map renders describe the scene rather than the look.  An **ID map** is a
flat, unantialiased Workbench render in which every part of the model (each
object, or each material) has its own solid color; Part Lines and per-part
Tone Bands read it to find the parts, which a 2D image cannot reveal.  A
**light map** renders the model as white clay under studio light, so Tone
Bands can tell real shadow from dark texture.
"""

import colorsys
import os
import shutil
import tempfile

import bpy

from .apply import array_to_image, image_to_array, _scene_owner_token

_MAP_KIND_KEY = "pixelatorplus_map_kind"
_MAP_OWNER_KEY = "pixelatorplus_map_owner"
_RENDERABLE_OBJECT_TYPES = frozenset({
    "MESH", "CURVE", "SURFACE", "META", "FONT", "VOLUME", "POINTCLOUD",
    "CURVES", "GPENCIL", "GREASEPENCIL",
})


def scene_has_renderable_content(scene):
    """Return whether a render-enabled scene collection can draw geometry."""
    pending = [(scene.collection, frozenset())]
    while pending:
        collection, ancestors = pending.pop()
        pointer = collection.as_pointer()
        if collection.hide_render or pointer in ancestors:
            continue
        path = ancestors | {pointer}
        for obj in collection.objects:
            if obj.hide_render:
                continue
            if _object_has_renderable_content(obj):
                return True
            if (obj.type == "EMPTY" and obj.instance_type == "COLLECTION"
                    and obj.instance_collection is not None):
                pending.append((obj.instance_collection, path))
        pending.extend((child, path) for child in collection.children)
    return False


def _object_has_renderable_content(obj):
    """Check for actual object data while allowing modifiers to generate it."""
    if obj.type not in _RENDERABLE_OBJECT_TYPES:
        return False
    if len(obj.modifiers):
        return True
    data = obj.data
    if data is None:
        return False
    if obj.type == "MESH":
        return bool(len(data.vertices))
    if obj.type in ("CURVE", "SURFACE"):
        return bool(len(data.splines))
    if obj.type == "FONT":
        return bool(str(data.body).strip())
    if obj.type == "META":
        return bool(len(data.elements))
    if obj.type == "VOLUME":
        return bool(len(data.grids))
    if obj.type == "POINTCLOUD":
        return bool(len(data.points))
    if obj.type == "CURVES":
        return bool(len(data.curves))
    # Grease Pencil's layer/frame structure differs across Blender versions;
    # a layer is a conservative indication that it may contain strokes.
    return bool(len(data.layers))


class TemporarySettings:
    """Change Blender properties now; restore them all with :meth:`restore`."""

    def __init__(self):
        self._saved = {}

    def set(self, owner, name, value):
        key = (owner.as_pointer(), name)
        if key not in self._saved:
            current = getattr(owner, name)
            if hasattr(current, "__len__") and not isinstance(current, str):
                # Vector properties return a live view; keep a copy.
                current = tuple(current)
            self._saved[key] = (owner, name, current)
        setattr(owner, name, value)

    def try_set(self, owner, name, value):
        """Like :meth:`set`, but skip missing properties and rejected values."""
        try:
            if not hasattr(owner, name):
                return False
            self.set(owner, name, value)
        except (ReferenceError, RuntimeError, TypeError, ValueError):
            return False
        return True

    def restore(self):
        """Restore every changed property, in first-change order (safe to repeat)."""
        saved, self._saved = self._saved, {}
        failed = {}
        first_error = None
        for key, (owner, name, value) in saved.items():
            try:
                setattr(owner, name, value)
            except Exception as exc:
                failed[key] = (owner, name, value)
                if first_error is None:
                    first_error = exc
        self._saved = failed
        if first_error is not None:
            raise first_error


def prepare_png_render(temp, scene, transparent=True):
    """Route renders of ``scene`` to 8-bit RGBA PNG stills (raw 3D render)."""
    render = scene.render
    formats = render.image_settings
    temp.set(render, "use_file_extension", True)
    if transparent:
        temp.set(render, "film_transparent", True)
    # The 3D render, not a video-sequencer edit that would replace it.
    temp.set(render, "use_sequencer", False)
    if hasattr(formats, "media_type"):
        temp.set(formats, "media_type", "IMAGE")  # before file_format (Blender 5.x)
    temp.set(formats, "file_format", "PNG")
    temp.set(formats, "color_mode", "RGBA")
    temp.set(formats, "color_depth", "8")


def _distinct_color(index):
    """Well-separated solid colors: golden-ratio hue steps, alternating value."""
    hue = (index * 0.618033988749895) % 1.0
    return colorsys.hsv_to_rgb(hue, 1.0, 1.0 if index % 2 == 0 else 0.55)


def _prepare_exact_workbench(temp, scene):
    """Workbench settings shared by map renders: exact, unantialiased, raw colors."""
    render, display = scene.render, scene.display
    shading, view = display.shading, scene.view_settings
    temp.set(render, "engine", "BLENDER_WORKBENCH")
    temp.set(render, "film_transparent", True)
    temp.set(render, "use_compositing", False)
    temp.try_set(render, "use_motion_blur", False)
    # Antialiasing would blend neighboring parts into colors of no part.
    temp.set(display, "render_aa", "OFF")
    # 8-bit output dithering adds per-pixel noise; maps must be exact.
    temp.try_set(render, "dither_intensity", 0.0)
    for flag in ("show_cavity", "show_object_outline", "show_xray",
                 "show_specular_highlight", "use_dof"):
        temp.try_set(shading, flag, False)
    # The available view transforms depend on the OCIO config.
    temp.try_set(view, "view_transform", "Standard")
    temp.try_set(view, "look", "None")
    temp.try_set(view, "exposure", 0.0)
    temp.try_set(view, "gamma", 1.0)
    temp.try_set(view, "use_curve_mapping", False)


def prepare_id_render(temp, scene, source="OBJECT"):
    """Turn the next renders into flat, unantialiased part-ID renders."""
    _prepare_exact_workbench(temp, scene)
    shading = scene.display.shading
    temp.set(shading, "light", "FLAT")
    temp.set(shading, "color_type", "OBJECT" if source == "OBJECT" else "MATERIAL")
    temp.try_set(shading, "show_shadows", False)
    # Assign well-separated colors instead of Workbench's name-hashed random
    # colors, which can make two different parts nearly identical.
    if source == "MATERIAL":
        parts, prop = sorted(bpy.data.materials, key=lambda m: m.name), "diffuse_color"
    else:
        parts, prop = sorted(scene.objects, key=lambda o: o.name), "color"
    for index, part in enumerate(parts):
        temp.set(part, prop, (*_distinct_color(index), 1.0))


def prepare_light_render(temp, scene):
    """Turn the next renders into light maps: white clay under studio light.

    Only lighting remains (shape shading and cast shadows); textures, colors,
    cavity, and specular highlights are removed, so Tone Bands can tell
    shadow from dark texture.
    """
    _prepare_exact_workbench(temp, scene)
    shading = scene.display.shading
    temp.set(shading, "light", "STUDIO")
    temp.set(shading, "color_type", "SINGLE")
    temp.set(shading, "single_color", (1.0, 1.0, 1.0))
    temp.try_set(shading, "show_shadows", True)


# Map kinds rendered from the scene: settings preparation and output name.
MAP_KINDS = {
    "id_map": ("ID Map", lambda temp, scene: prepare_id_render(
        temp, scene, scene.pixelatorplus.sprite_part_source)),
    "light_map": ("Light Map", prepare_light_render),
}


def render_still(temp, scene, path):
    """Render the current frame of ``scene`` to ``path``."""
    temp.set(scene.render, "filepath", path)
    bpy.ops.render.render(write_still=True, scene=scene.name)
    if not os.path.isfile(path):
        raise RuntimeError(f"Blender did not write the rendered frame {path}")


def load_pixels(path):
    """Load an image file as a bottom-up ``(h, w, 4)`` float32 array."""
    image = bpy.data.images.load(path, check_existing=False)
    try:
        return image_to_array(image)
    finally:
        bpy.data.images.remove(image)


def render_map(scene, key):
    """Render the current frame's ``key`` map (see ``MAP_KINDS``), bottom-up RGBA."""
    _label, prepare = MAP_KINDS[key]
    temp = TemporarySettings()
    folder = tempfile.mkdtemp(prefix="pixelatorplus_map_")
    try:
        prepare_png_render(temp, scene)
        prepare(temp, scene)
        path = os.path.join(folder, f"{key}.png")
        render_still(temp, scene, path)
        return load_pixels(path)
    finally:
        try:
            temp.restore()
        finally:
            shutil.rmtree(folder, ignore_errors=True)


def _write_map_image(scene, key, pixels):
    """Update this scene's generated map without reusing an unrelated image."""
    label = MAP_KINDS[key][0]
    settings = scene.pixelatorplus
    owner = _scene_owner_token(scene)
    current = getattr(settings, f"{key}_image", None)
    if (current is not None and current.get(_MAP_KIND_KEY) == key
            and current.get(_MAP_OWNER_KEY) == owner):
        image = array_to_image(pixels, current.name, image=current)
    else:
        name = f"{scene.name} [PixelatorPlus {label}]"
        image = array_to_image(pixels, name, reuse=False)
        image[_MAP_KIND_KEY] = key
        image[_MAP_OWNER_KEY] = owner
    setattr(settings, f"{key}_image", image)
    return image


class _RenderMapOperator:
    """Render one map kind for the current frame and pin it in the settings."""

    map_key = ""
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return bool(
            scene and scene.camera and scene_has_renderable_content(scene)
        )

    def execute(self, context):
        scene = context.scene
        label = MAP_KINDS[self.map_key][0]
        if not scene_has_renderable_content(scene):
            self.report({"ERROR"}, "The scene has no renderable objects for a map render")
            return {"CANCELLED"}
        try:
            pixels = render_map(scene, self.map_key)
            image = _write_map_image(scene, self.map_key, pixels)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not create the {label}: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{label} '{image.name}' rendered and pinned")
        return {"FINISHED"}


class PIXELATORPLUS_OT_render_id_map(_RenderMapOperator, bpy.types.Operator):
    """Render the current frame's ID map (one flat color per part) for Part Lines and Tone Bands"""

    bl_idname = "pixelatorplus.render_id_map"
    bl_label = "Render ID Map"
    map_key = "id_map"


class PIXELATORPLUS_OT_render_light_map(_RenderMapOperator, bpy.types.Operator):
    """Render the current frame's light map (texture-free studio lighting) for Tone Bands"""

    bl_idname = "pixelatorplus.render_light_map"
    bl_label = "Render Light Map"
    map_key = "light_map"


classes = (PIXELATORPLUS_OT_render_id_map, PIXELATORPLUS_OT_render_light_map)

register, unregister = bpy.utils.register_classes_factory(classes)
