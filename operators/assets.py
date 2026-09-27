"""Compositor asset-library registration for bundled native-node presets."""

import os

import bpy

ASSET_LIBRARY_NAME = "PixelatorPlus Compositor Assets"
ASSET_LIBRARY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "compositor_library",
)
ASSET_BLEND = os.path.join(ASSET_LIBRARY_DIR, "pixelatorplus_compositor_assets.blend")


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def compositor_assets_registered():
    """Whether Blender's current preferences already include this library."""
    for library in bpy.context.preferences.filepaths.asset_libraries:
        if _same_path(library.path, ASSET_LIBRARY_DIR):
            return True
    return False


def ensure_compositor_assets(preferences=None):
    """Register the bundled catalog, updating its path after extension updates."""
    if not os.path.isfile(ASSET_BLEND):
        raise FileNotFoundError("bundled compositor asset library is missing")
    preferences = preferences or bpy.context.preferences
    libraries = preferences.filepaths.asset_libraries
    library = next(
        (entry for entry in libraries if _same_path(entry.path, ASSET_LIBRARY_DIR)),
        None,
    )
    if library is None:
        # Reuse the named entry after an extension update, whose install
        # directory can change, instead of accumulating stale duplicates.
        library = next((entry for entry in libraries if entry.name == ASSET_LIBRARY_NAME), None)
        if library is None:
            library = libraries.new(name=ASSET_LIBRARY_NAME)
        library.path = ASSET_LIBRARY_DIR
    return library


def _refresh_open_asset_shelf(context):
    """Refresh an open Asset Shelf when one is available in the UI."""
    if bpy.ops.asset.library_refresh.poll():
        bpy.ops.asset.library_refresh()
        return True
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            for region in area.regions:
                if region.type != "ASSET_SHELF":
                    continue
                with context.temp_override(
                    window=window, screen=window.screen, area=area, region=region
                ):
                    if bpy.ops.asset.library_refresh.poll():
                        bpy.ops.asset.library_refresh()
                        return True
    return False


class PIXELATORPLUS_OT_install_compositor_assets(bpy.types.Operator):
    """Add bundled native compositor presets to Blender's Asset Libraries"""

    bl_idname = "pixelatorplus.install_compositor_assets"
    bl_label = "Register Compositor Asset Library"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            ensure_compositor_assets(context.preferences)
        except FileNotFoundError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        # This operator requires an Asset Browser context.  Find an open Asset
        # Shelf when the button was pressed from the Compositor sidebar; if no
        # shelf is open yet, Blender discovers the library when it is opened.
        _refresh_open_asset_shelf(context)
        self.report(
            {"INFO"},
            "Compositor assets registered. Open the Compositor Asset Shelf and choose "
            "PixelatorPlus / Compositor.",
        )
        return {"FINISHED"}


classes = (PIXELATORPLUS_OT_install_compositor_assets,)


register, unregister = bpy.utils.register_classes_factory(classes)
