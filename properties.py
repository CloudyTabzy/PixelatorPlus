"""PixelatorPlus settings: the unified Pixel8r-derived feature surface.

The add-on starts with the latest v2.72-style defaults, while exposing useful
controls reconstructed from every documented Pixel8r release.  It deliberately
has no compatibility-version selector: artists can combine all capabilities.
The nested v3 settings add the canonical stage policy and PixelatorPlus-native
palette/grid controls without breaking the flat compatibility surface.

Property definitions live in ``settings/``, one mixin per sidebar section;
this module composes them and owns parameter collection and registration.
"""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    PointerProperty,
)

from .settings.color import ColorSettings
from .settings.common import mark_dirty
from .settings.dither import DitherSettings
from .settings.finish import FinishSettings
from .settings.items import V3_GRID_COHERENCE, V3_PALETTE_LOCKS, V3_STAGE_ITEMS
from .settings.pixels import PixelSettings
from .settings.sheet import SpriteSheetSettings
from .settings.sprite import SpriteSettings
from .settings.workflow import WorkflowSettings


class PixelatorPlusV3Stage(bpy.types.PropertyGroup):
    stage_id: EnumProperty(name="Stage", items=V3_STAGE_ITEMS, options={"HIDDEN"})
    enabled: BoolProperty(name="Enabled", default=True, update=mark_dirty)


class PixelatorPlusV3Settings(bpy.types.PropertyGroup):
    """Canonical settings for additive v3 policies and the stage stack."""

    palette_lock: EnumProperty(
        name="Palette Lock", default="OFF", items=V3_PALETTE_LOCKS,
        update=mark_dirty,
        description="PixelatorPlus-exclusive guard for preserving palette identity through finishing",
    )
    palette_lock_strength: FloatProperty(
        name="Palette Tint Strength", default=1.0, min=0.0, max=1.0,
        subtype="FACTOR", update=mark_dirty,
        description="Blend between the source palette and its display-tinted version",
    )
    grid_coherence: EnumProperty(
        name="Grid Coherence", default="OFF", items=V3_GRID_COHERENCE,
        update=mark_dirty,
        description="Keep dither and finishing aligned with the selected pixel grid",
    )
    stage_stack: CollectionProperty(type=PixelatorPlusV3Stage)


class PixelatorPlusSettings(
    WorkflowSettings,
    PixelSettings,
    ColorSettings,
    DitherSettings,
    SpriteSettings,
    FinishSettings,
    SpriteSheetSettings,
    bpy.types.PropertyGroup,
):
    """All PixelatorPlus scene settings (``Scene.pixelatorplus``)."""

    v3: PointerProperty(
        name="V3 Settings", type=PixelatorPlusV3Settings,
        description="Canonical PixelatorPlus v3 policies and stage stack",
    )



# Settings that describe the workflow or UI state rather than the look.
# Every other non-pin setting is an *effect* setting: it is captured by plan
# snapshots and reset by style recipes (see presets.EFFECT_BASELINE).  New
# workflow settings belong here or under a workflow prefix.
_WORKFLOW_SETTINGS = frozenset({
    "style_preset", "live_preview", "preview_mode", "preview_max_size",
    "preview_cache_enabled", "preview_status", "preview_failed",
    "v3_plan_json", "v3_plan_fingerprint", "auto_bake_render",
    "auto_connect_baked_output",
})
_WORKFLOW_PREFIXES = ("sheet_", "last_")


def setting_annotations():
    """All ``PixelatorPlusSettings`` property definitions, section by section.

    The section mixins each carry their own ``__annotations__``; this merges
    them in declaration order, as Blender registers them.
    """
    merged = {}
    for cls in reversed(PixelatorPlusSettings.__mro__):
        merged.update(vars(cls).get("__annotations__", {}))
    return merged


def _effect_setting_names():
    """Effect settings in declaration order; image pins are excluded."""
    return tuple(
        name for name, prop in setting_annotations().items()
        if getattr(prop, "function", None) is not PointerProperty
        and name not in _WORKFLOW_SETTINGS
        and not name.startswith(_WORKFLOW_PREFIXES)
    )


EFFECT_SETTINGS = _effect_setting_names()


def ensure_v3_stages(settings):
    """Complete the canonical v3 stage stack and return it.

    Adds any stage missing from the collection (a new scene, or a file saved
    before a stage existed), keeps the dependency order, and re-enables the
    mandatory Pixelate stage.  It only writes when something is wrong, so
    calling it on a complete stack does not fire update hooks or invalidate
    the live preview.  This mutates scene data: call it from operators, never
    from ``Panel.draw`` or parameter collection.
    """
    stack = settings.v3.stage_stack
    present = {item.stage_id for item in stack}
    for stage_id, _label, _description in V3_STAGE_ITEMS:
        if stage_id not in present:
            item = stack.add()
            item.stage_id = stage_id
    # Appended stages must still follow the dependency order the plan
    # validator enforces.
    for target, (stage_id, _label, _description) in enumerate(V3_STAGE_ITEMS):
        current = next(i for i, item in enumerate(stack) if item.stage_id == stage_id)
        if current != target:
            stack.move(current, target)
    for item in stack:
        # The grid is the required input for every v3 stage.
        if item.stage_id == "pixelate" and not item.enabled:
            item.enabled = True
    return stack


def collect_snapshot_params(settings):
    """Copy raw scalar settings for a lossless v3 plan snapshot.

    Unlike :func:`collect_params`, this does not replace inactive execution
    controls with ``None``.  Snapshot restore must be able to write every
    stored value back to its Blender property even while its matching option
    is disabled.
    """
    params = {}
    for name in EFFECT_SETTINGS:
        value = getattr(settings, name)
        if hasattr(value, "__len__") and not isinstance(value, str):
            value = tuple(value)  # vector properties (colors, tile sizes)
        params[name] = value
    # Parameter collection runs from preview and Apply paths.  It must report
    # an existing stage policy without initializing the collection or forcing
    # a disabled flag back on; operators and presets explicitly initialize
    # the stack when that mutation is wanted.
    stack = settings.v3.stage_stack
    params["v3_stage_order"] = tuple(item.stage_id for item in stack)
    params["v3_stage_enabled"] = {item.stage_id: bool(item.enabled) for item in stack}
    params["v3_palette_lock"] = settings.v3.palette_lock
    params["v3_palette_lock_strength"] = settings.v3.palette_lock_strength
    params["v3_grid_coherence"] = settings.v3.grid_coherence
    return params


def collect_params(settings):
    """Derive the plain execution dictionary consumed by core.pipeline."""
    params = collect_snapshot_params(settings)
    # mask shaping extras (build_mask kwargs)
    params["mask_lum_range"] = (settings.dither_mask_lum_low, settings.dither_mask_lum_high)
    params["mask_sat_range"] = (settings.dither_mask_sat_low, settings.dither_mask_sat_high)
    params["mask_gradient_angle"] = settings.dither_mask_gradient_angle
    params["mask_invert"] = settings.dither_mask_invert
    params["mask_blur"] = settings.dither_mask_blur
    params["quantize_seed"] = (
        settings.quantize_seed if settings.use_explicit_quantize_seed else None
    )
    params["chroma_importance"] = (
        settings.chroma_importance if settings.use_chroma_importance else None
    )
    # Blender stores FILE_PATH values relative to the .blend ("//...") by
    # default; the core opens plain filesystem paths.
    if settings.cube_lut_path:
        params["cube_lut_path"] = bpy.path.abspath(settings.cube_lut_path)
    return params


def register():
    bpy.utils.register_class(PixelatorPlusV3Stage)
    bpy.utils.register_class(PixelatorPlusV3Settings)
    bpy.utils.register_class(PixelatorPlusSettings)
    bpy.types.Scene.pixelatorplus = PointerProperty(type=PixelatorPlusSettings)


def unregister():
    del bpy.types.Scene.pixelatorplus
    bpy.utils.unregister_class(PixelatorPlusSettings)
    bpy.utils.unregister_class(PixelatorPlusV3Settings)
    bpy.utils.unregister_class(PixelatorPlusV3Stage)
