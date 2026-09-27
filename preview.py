"""Debounced live preview.

Property edits mark the settings dirty; a bpy.app.timers callback waits for
edits to settle (DEBOUNCE seconds), then re-runs the pipeline at capped
resolution (longest side <= preview_max_size) into the 'PixelatorPlus Preview'
image and shows it in any open Image Editor. Full resolution is only ever
produced by the Apply operator.
"""

import time

import bpy

from .core.cache import PreviewCache, preview_key
from .core.pipeline import run_pipeline
from .core.pixelate import downscale_area
from .operators.apply import PREVIEW_IMAGE_NAME, array_to_image, custom_images, image_to_array
from .properties import collect_params

DEBOUNCE = 0.35
_dirty_since = None
_preview_cache = PreviewCache(max_items=3, max_bytes=64 * 1024 * 1024)


def mark_dirty(context):
    """Called from property update hooks; schedules the debounce timer."""
    global _dirty_since
    settings = getattr(context.scene, "pixelatorplus", None) if context.scene else None
    if settings is None or not settings.live_preview:
        return
    _dirty_since = time.monotonic()
    if not bpy.app.timers.is_registered(_debounce):
        bpy.app.timers.register(_debounce, first_interval=DEBOUNCE)


def _debounce():
    if _dirty_since is None:
        return None
    if time.monotonic() - _dirty_since < DEBOUNCE:
        return 0.1  # still settling; check again shortly
    _update_preview()
    return None


def _update_preview():
    global _dirty_since
    _dirty_since = None
    try:
        scene = bpy.context.scene
        if scene is None:
            return
        s = scene.pixelatorplus
        if not s.live_preview or s.input_image is None:
            return
        src = image_to_array(s.input_image)
        cap = s.preview_max_size
        h, w = src.shape[:2]
        if max(h, w) > cap:
            scale = cap / max(h, w)
            src = downscale_area(src, max(1, round(w * scale)), max(1, round(h * scale)))

        params = collect_params(s)
        if s.preview_mode == "DRAFT":
            # Painter's practical workflow applies here too: keep interaction
            # responsive while arranging an image, then inspect Final Effects
            # before committing.  Apply deliberately never reads this setting.
            params.update({
                "dither_type": "NONE",
                "quantize_type": "NONE",
                "posterize_enabled": False,
                "finish_enabled": False,
                "preview_dither_mask": False,
                "output_palette": False,
                "output_lut": False,
                "output_default_lut": False,
            })

        # The 4096x4096 custom LUT pin is intentionally omitted from preview.
        # Keep the rest of the preview useful by bypassing only that final LUT
        # stage instead of letting the missing pin cancel the whole update.
        if params.get("quantize_type") == "LUT" and params.get("lut") == "CUSTOM_LUT":
            params["quantize_type"] = "NONE"
            params["output_default_lut"] = False
        # Apply and preview share active-pin resolution.  This happens after
        # the intentional preview-only image-LUT bypass above, so a 4K LUT is
        # never read just to refresh an interactive preview.
        images = custom_images(s, params)
        cache_key = preview_key(src, params, images, s.preview_mode)
        result = _preview_cache.get(cache_key) if s.preview_cache_enabled else None
        if result is None:
            result = run_pipeline(src, params, images=images, preview=True)
            if s.preview_cache_enabled:
                _preview_cache.put(cache_key, result)
        out = array_to_image(result["main"], PREVIEW_IMAGE_NAME)

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type != "IMAGE_EDITOR":
                    continue
                space = area.spaces.active
                # A pinned editor is the user's explicit choice of image.
                if not getattr(space, "use_image_pin", False):
                    space.image = out
    except Exception as exc:
        print(f"PixelatorPlus preview: {exc}")


def unregister():
    global _dirty_since
    _dirty_since = None
    if bpy.app.timers.is_registered(_debounce):
        bpy.app.timers.unregister(_debounce)
    _preview_cache.clear()


def register():
    pass
