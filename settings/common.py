"""Shared pieces for settings modules: the preview update hook and path options."""

import bpy


# collect_params() resolves "//" paths itself.  Newer Blender versions warn
# unless a path property declares that; older ones reject the unknown option
# at registration, so the option is feature-tested.
BLEND_RELATIVE_PATH_OPTIONS = {"ANIMATABLE"} | (
    {"PATH_SUPPORTS_BLEND_RELATIVE"}
    if "is_path_supports_blend_relative" in bpy.types.Property.bl_rna.properties
    else set()
)


def mark_dirty(self, context):
    """Property update hook: ask the live preview to recompute (debounced)."""
    try:
        from .. import preview

        preview.mark_dirty(context)
    except Exception:
        pass  # preview must never break property edits
