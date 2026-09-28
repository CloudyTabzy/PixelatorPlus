"""Render helpers: temporary scene settings, PNG stills, and ID maps.

Everything here changes the user's scene only through ``TemporarySettings``,
which records each property the first time it changes and restores it later.
Restoring runs in the order properties were first changed; callers rely on
that for Blender 5.x image formats, where ``media_type`` must be set (and
restored) before ``file_format``.

An **ID map** is a flat, unantialiased Workbench render in which every part
of the model (each object, or each material) has its own solid color.  The
sprite stage's Part Lines read it to find where parts meet, which a 2D image
cannot reveal.
"""

import colorsys
import os
import shutil
import tempfile

import bpy

from .apply import array_to_image, image_to_array


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
        if not hasattr(owner, name):
            return False
        try:
            self.set(owner, name, value)
        except (TypeError, ValueError):
            return False
        return True

    def restore(self):
        """Restore every changed property, in first-change order (safe to repeat)."""
        saved, self._saved = self._saved, {}
        for owner, name, value in saved.values():
            setattr(owner, name, value)


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


def prepare_id_render(temp, scene, source="OBJECT"):
    """Turn the next renders into flat, unantialiased part-ID renders."""
    render, display = scene.render, scene.display
    shading, view = display.shading, scene.view_settings
    temp.set(render, "engine", "BLENDER_WORKBENCH")
    temp.set(render, "film_transparent", True)
    temp.set(render, "use_compositing", False)
    temp.try_set(render, "use_motion_blur", False)
    # Antialiasing would blend neighboring IDs into colors of no part.
    temp.set(display, "render_aa", "OFF")
    # 8-bit output dithering adds per-pixel noise; IDs must be exact.
    temp.try_set(render, "dither_intensity", 0.0)
    temp.set(shading, "light", "FLAT")
    temp.set(shading, "color_type", "OBJECT" if source == "OBJECT" else "MATERIAL")
    for flag in ("show_cavity", "show_object_outline", "show_shadows", "show_xray",
                 "show_specular_highlight", "use_dof"):
        temp.try_set(shading, flag, False)
    # Keep ID colors exact; the available transforms depend on the OCIO config.
    temp.try_set(view, "view_transform", "Standard")
    temp.try_set(view, "look", "None")
    temp.try_set(view, "exposure", 0.0)
    temp.try_set(view, "gamma", 1.0)
    temp.try_set(view, "use_curve_mapping", False)
    # Assign well-separated colors instead of Workbench's name-hashed random
    # colors, which can make two different parts nearly identical.
    if source == "MATERIAL":
        parts, prop = sorted(bpy.data.materials, key=lambda m: m.name), "diffuse_color"
    else:
        parts, prop = sorted(scene.objects, key=lambda o: o.name), "color"
    for index, part in enumerate(parts):
        temp.set(part, prop, (*_distinct_color(index), 1.0))


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


def render_id_map(scene, source="OBJECT"):
    """Render the current frame's ID map and return it (bottom-up RGBA)."""
    temp = TemporarySettings()
    folder = tempfile.mkdtemp(prefix="pixelatorplus_id_")
    try:
        prepare_png_render(temp, scene)
        prepare_id_render(temp, scene, source)
        path = os.path.join(folder, "id_map.png")
        render_still(temp, scene, path)
        return load_pixels(path)
    finally:
        temp.restore()
        shutil.rmtree(folder, ignore_errors=True)


class PIXELATORPLUS_OT_render_id_map(bpy.types.Operator):
    """Render the current frame's ID map (one flat color per part) for Part Lines"""

    bl_idname = "pixelatorplus.render_id_map"
    bl_label = "Render ID Map"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.scene.camera)

    def execute(self, context):
        scene = context.scene
        settings = scene.pixelatorplus
        try:
            pixels = render_id_map(scene, settings.sprite_part_source)
        except RuntimeError as exc:
            self.report({"ERROR"}, f"Could not render the ID map: {exc}")
            return {"CANCELLED"}
        image = array_to_image(pixels, f"{scene.name} [PixelatorPlus ID Map]")
        settings.id_map_image = image
        self.report({"INFO"}, f"ID map '{image.name}' rendered; Part Lines will use it")
        return {"FINISHED"}


classes = (PIXELATORPLUS_OT_render_id_map,)

register, unregister = bpy.utils.register_classes_factory(classes)
