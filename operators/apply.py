"""PIXELATORPLUS_OT_apply: run the full-resolution pipeline on the input image and
write the result to a '<name> [PixelatorPlus]' image datablock (reused in place on
repeat runs). Optional extra outputs (palette swatch / 4K LUT) follow the
output_palette / output_lut / output_default_lut toggles.
"""

import uuid

import numpy as np

import bpy

from ..core.pipeline import PipelineError, run_pipeline
from ..core.plan import normalize_plan, plan_to_params, stage_types
from ..properties import collect_params
from .gpu_backend import get_palette_accelerator

PREVIEW_IMAGE_NAME = "PixelatorPlus Preview"

_SCENE_OWNER_KEY = "_pixelatorplus_output_owner"
_SCENE_OWNER_NAME_KEY = "_pixelatorplus_output_owner_scene_name"
_OUTPUT_OWNER_KEY = "pixelatorplus_owner_scene"
_OUTPUT_SOURCE_KEY = "pixelatorplus_source_image"
_OUTPUT_ROLE_KEY = "pixelatorplus_output_role"

_PIN_ATTRIBUTES = {
    "custom_dither": "custom_dither_image",
    "custom_mask": "custom_mask_image",
    "custom_lut": "custom_lut_image",
    "custom_palette": "custom_palette_image",
    "custom_palette_replace": "palette_replace_image",
    "strength_map": "strength_map_image",
    "threshold_map": "threshold_map_image",
    "range_map": "range_map_image",
    "id_map": "id_map_image",
    "light_map": "light_map_image",
}


def image_to_array(image):
    """Blender Image -> float32 NumPy (h, w, 4). Raises ValueError if empty."""
    w, h = image.size
    if w <= 0 or h <= 0:
        raise ValueError(f"image '{image.name}' has no pixel data")
    arr = np.empty(h * w * 4, dtype=np.float32)
    image.pixels.foreach_get(arr)
    return arr.reshape(h, w, 4)


def array_to_image(arr, name, reuse=True, image=None):
    """Write a float32 array without replacing an existing image datablock.

    ``image`` is an explicitly selected output image.  Its buffer is resized in
    place so materials, compositor nodes, and other Blender users retain their
    reference when the output dimensions change.
    """
    if arr.shape[2] == 3:
        alpha = np.ones(arr.shape[:2] + (1,), dtype=np.float32)
        arr = np.concatenate([arr, alpha], axis=-1)
    h, w = arr.shape[:2]
    img = image if image is not None else (bpy.data.images.get(name) if reuse else None)
    if img is not None and (img.size[0] != w or img.size[1] != h):
        try:
            img.scale(w, h)
        except RuntimeError as exc:
            raise ValueError(f"could not resize output image '{img.name}'") from exc
        if img.size[0] != w or img.size[1] != h:
            raise ValueError(f"output image '{img.name}' did not resize to {w}x{h}")
    if img is None:
        img = bpy.data.images.new(name, width=w, height=h, alpha=True, float_buffer=False)
    img.pixels.foreach_set(np.ascontiguousarray(arr, dtype=np.float32).ravel())
    img.update()
    return img


def _scene_owner_token(scene):
    """Return a persistent per-scene token used to own generated outputs."""
    token = scene.get(_SCENE_OWNER_KEY)
    scene_name = str(getattr(scene, "name_full", scene.name))
    # Scene custom properties are copied with duplicated scenes.  Pair the
    # token with Blender's unique scene name so a duplicate starts a new output
    # namespace while ordinary save/reload keeps its existing one.
    if (not isinstance(token, str) or not token
            or scene.get(_SCENE_OWNER_NAME_KEY) != scene_name):
        token = uuid.uuid4().hex
        scene[_SCENE_OWNER_KEY] = token
        scene[_SCENE_OWNER_NAME_KEY] = scene_name
    return token


def _source_name(source):
    """Use Blender's unique datablock name as the persistent source marker."""
    return str(getattr(source, "name_full", source.name))


def _owned_output(scene, source, role, legacy_name, expected_name):
    """Find an output owned by this scene/source/role, adopting safe legacy data."""
    owner = _scene_owner_token(scene)
    source_name = _source_name(source)

    def matches(image):
        return (
            image.get(_OUTPUT_OWNER_KEY) == owner
            and image.get(_OUTPUT_SOURCE_KEY) == source_name
            and image.get(_OUTPUT_ROLE_KEY) == role
        )

    candidate = bpy.data.images.get(legacy_name) if legacy_name else None
    if candidate is not None and matches(candidate):
        return candidate
    for image in bpy.data.images:
        if matches(image):
            return image

    # Files made before ownership metadata existed can be adopted only through
    # the scene's explicit last-output pointer, never by a global name lookup.
    if candidate is not None and not any(
        key in candidate for key in (_OUTPUT_OWNER_KEY, _OUTPUT_SOURCE_KEY, _OUTPUT_ROLE_KEY)
    ) and candidate.name.startswith(expected_name):
        return candidate
    return None


def _stamp_output(image, scene, source, role):
    """Attach scene/source/role ownership metadata to an add-on generated image."""
    image[_OUTPUT_OWNER_KEY] = _scene_owner_token(scene)
    image[_OUTPUT_SOURCE_KEY] = _source_name(source)
    image[_OUTPUT_ROLE_KEY] = role


def _write_output(scene, source, arr, role, setting_name, name):
    """Update the scene-owned output image and keep the scene's direct reference."""
    settings = scene.pixelatorplus
    current = _owned_output(scene, source, role, getattr(settings, setting_name), name)
    # A missing owned image must create a new datablock.  Falling back to
    # ``array_to_image``'s legacy global-name reuse here would let another
    # scene's output be overwritten before it can be stamped with this role.
    image = array_to_image(arr, name, reuse=False, image=current)
    _stamp_output(image, scene, source, role)
    setattr(settings, setting_name, image.name)
    return image


def required_custom_image_keys(params):
    """Return custom image pins reachable by the active stage plan.

    Apply and live preview use this single resolver.  Preview intentionally
    changes its unsupported custom-image-LUT mode before calling this helper.
    """
    plan = normalize_plan(params)
    resolved = plan_to_params(plan)
    active = set(stage_types(plan))
    keys = set()
    qtype = resolved.get("quantize_type", "NONE")
    lut = resolved.get("lut", "AMIGA")
    dither_active = "dither" in active and resolved.get("dither_type", "NONE") != "NONE"
    palette_threshold = dither_active and resolved.get("dither_strategy", "OVERLAY") == "PALETTE_THRESHOLD"

    if dither_active and resolved.get("dither_type") in ("CUSTOM", "CUSTOM_8X8", "CUSTOM_16X16"):
        keys.add("custom_dither")
    if dither_active and resolved.get("dither_mask_type", "NONE") == "CUSTOM":
        keys.add("custom_mask")
    if ("display_finish" in active and resolved.get("finish_enabled", False)
            and resolved.get("finish_mask_type", "NONE") == "CUSTOM"):
        keys.add("custom_mask")
    if "posterize" in active:
        keys.add("range_map")
    if palette_threshold:
        keys.add("threshold_map")
    if dither_active or ("display_finish" in active and resolved.get("finish_enabled", False)):
        keys.add("strength_map")

    custom_palette_needed = qtype == "LUT" and lut == "CUSTOM_PALETTE" and (
        "quantize" in active or palette_threshold
    )
    if custom_palette_needed:
        keys.add("custom_palette")
    if qtype == "LUT" and lut == "CUSTOM_LUT" and "quantize" in active:
        keys.add("custom_lut")
    if qtype == "CUSTOM_PALETTE" and ("quantize" in active or palette_threshold):
        keys.add("custom_palette_replace")
    if "sprite" in active and resolved.get("sprite_part_lines", False):
        keys.add("id_map")
    if "shading" in active:
        if resolved.get("shade_band_source", "LIGHTNESS") == "LIGHT_MAP":
            keys.add("light_map")
        if resolved.get("shade_band_per_part", False):
            keys.add("id_map")
    return keys


def custom_images(settings, params=None):
    """Read only custom pins that the active pipeline path can consume."""
    params = collect_params(settings) if params is None else params
    images = {}
    for key in required_custom_image_keys(params):
        pin = getattr(settings, _PIN_ATTRIBUTES[key], None)
        if pin is not None:
            images[key] = image_to_array(pin)
    return images


def apply_settings(scene, source_image=None):
    """Run the exact pipeline and return ``(output_image, result)``.

    This shared implementation is deliberately operator-free so the compositor
    hybrid workflow and render-complete handler can use the same full-quality
    path as the Image Editor Apply button.
    """
    settings = scene.pixelatorplus
    source = source_image or settings.input_image
    if source is None:
        raise ValueError("PixelatorPlus input image required")

    src = image_to_array(source)
    params = collect_params(settings)
    accelerator = get_palette_accelerator(params, src.shape[:2])
    if accelerator is not None:
        accelerator.begin_run()
    result = run_pipeline(
        src, params, images=custom_images(settings, params), preview=False,
        palette_apply=accelerator.apply_palette if accelerator is not None else None,
    )
    result["_gpu_palette_mapping"] = bool(accelerator and accelerator.used)
    result["_gpu_palette_fallback"] = (
        accelerator.error if accelerator is not None and not accelerator.used else ""
    )

    base = source.name
    out = _write_output(
        scene, source, result["main"], "main", "last_output_name", f"{base} [PixelatorPlus]"
    )

    if result["palette"] is not None:
        _write_output(
            scene, source, result["palette"], "palette", "last_palette_name",
            f"{base} [PixelatorPlus Palette]",
        )
    else:
        settings.last_palette_name = ""
    if result["palette_index"] is not None:
        _write_output(
            scene, source, result["palette_index"], "palette_index", "last_palette_index_name",
            f"{base} [PixelatorPlus Palette Index]",
        )
    else:
        settings.last_palette_index_name = ""
    if result["lut"] is not None:
        _write_output(
            scene, source, result["lut"], "lut", "last_lut_name", f"{base} [PixelatorPlus LUT]"
        )
    else:
        settings.last_lut_name = ""
    return out, result


class PIXELATORPLUS_OT_apply(bpy.types.Operator):
    """Pixelate / dither / quantize the input image at full resolution"""

    bl_idname = "pixelatorplus.apply"
    bl_label = "Apply PixelatorPlus"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        image = context.scene.pixelatorplus.input_image if context.scene else None
        return bool(image and image.size[0] > 0 and image.size[1] > 0)

    def execute(self, context):
        try:
            out, result = apply_settings(context.scene)
        except (PipelineError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        # Show the result in the invoking Image Editor, if any
        space = getattr(context, "space_data", None)
        if space is not None and getattr(space, "type", None) == "IMAGE_EDITOR":
            space.image = out

        gw, gh = result["grid"]
        backend_note = " (GPU palette mapping)" if result.get("_gpu_palette_mapping") else ""
        self.report({"INFO"}, f"PixelatorPlus: {gw}x{gh} grid -> '{out.name}'{backend_note}")
        fallback = result.get("_gpu_palette_fallback")
        if fallback:
            detail = " ".join(str(fallback).split())[:120]
            self.report({"WARNING"}, f"GPU mapping failed; used CPU instead ({detail})")
        return {"FINISHED"}


classes = (PIXELATORPLUS_OT_apply,)

register, unregister = bpy.utils.register_classes_factory(classes)
