"""Explicit v2-to-v3 plan snapshot and restore operators.

The current PropertyGroup remains the compatibility surface for existing
scenes.  These operators make the normalized v3 stage plan visible and
portable without forcing a breaking nested-property migration.  Image pins
are intentionally left as Blender datablock links and are not serialized into
the JSON snapshot.
"""

import bpy

from ..core.plan import normalize_plan, plan_fingerprint, plan_from_json, plan_to_json, plan_to_params
from ..properties import collect_snapshot_params, ensure_v3_stages


def _apply_scalar_params(settings, params):
    """Restore only scalar settings known by the current PropertyGroup."""
    skipped = []
    for key, value in params.items():
        if key in ("v3_palette_lock", "v3_palette_lock_strength", "v3_grid_coherence"):
            setattr(settings.v3, key[3:], value)
            continue
        if key in ("v3_stage_order", "v3_stage_enabled"):
            continue
        if not hasattr(settings, key):
            skipped.append(key)
            continue
        try:
            setattr(settings, key, value)
        except (TypeError, ValueError, AttributeError):
            skipped.append(key)
    return skipped


def _restore_stage_policy(settings, params):
    """Restore v3 stage enable flags without replacing the collection object."""
    enabled = params.get("v3_stage_enabled", {})
    if not isinstance(enabled, dict):
        return
    for item in ensure_v3_stages(settings):
        if item.stage_id in enabled:
            item.enabled = bool(enabled[item.stage_id])


class PIXELATORPLUS_OT_snapshot_plan(bpy.types.Operator):
    """Normalize current flat settings and store a v3 plan in the scene."""

    bl_idname = "pixelatorplus.snapshot_plan"
    bl_label = "Capture Plan Snapshot"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene and hasattr(context.scene, "pixelatorplus"))

    def execute(self, context):
        settings = context.scene.pixelatorplus
        # Snapshot the editable values before execution-only conversion turns
        # disabled numeric controls (such as explicit seed) into ``None``.
        plan = normalize_plan(collect_snapshot_params(settings))
        settings.v3_plan_json = plan_to_json(plan)
        settings.v3_plan_fingerprint = plan_fingerprint(plan)
        self.report({"INFO"}, f"Captured plan {settings.v3_plan_fingerprint}")
        return {"FINISHED"}


class PIXELATORPLUS_OT_restore_plan(bpy.types.Operator):
    """Restore scalar settings from the stored v3 plan snapshot."""

    bl_idname = "pixelatorplus.restore_plan"
    bl_label = "Restore Plan Snapshot"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.pixelatorplus if context.scene else None
        return bool(settings and settings.v3_plan_json)

    def execute(self, context):
        settings = context.scene.pixelatorplus
        try:
            plan = plan_from_json(settings.v3_plan_json)
            params = plan_to_params(plan)
            skipped = _apply_scalar_params(settings, params)
            _restore_stage_policy(settings, params)
            settings.v3_plan_fingerprint = plan_fingerprint(plan)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        message = f"Restored plan {settings.v3_plan_fingerprint}"
        if skipped:
            message += f" ({len(skipped)} legacy value(s) skipped)"
        self.report({"INFO"}, message)
        return {"FINISHED"}


class PIXELATORPLUS_OT_init_stage_stack(bpy.types.Operator):
    """Create the editable V3 stage stack for this scene"""

    bl_idname = "pixelatorplus.init_stage_stack"
    bl_label = "Initialize Stage Stack"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene and hasattr(context.scene, "pixelatorplus"))

    def execute(self, context):
        # Panels cannot write scene data while drawing, so stack creation is
        # an explicit, undoable action rather than a side effect of drawing.
        ensure_v3_stages(context.scene.pixelatorplus)
        return {"FINISHED"}


classes = (
    PIXELATORPLUS_OT_snapshot_plan,
    PIXELATORPLUS_OT_restore_plan,
    PIXELATORPLUS_OT_init_stage_stack,
)

register, unregister = bpy.utils.register_classes_factory(classes)
