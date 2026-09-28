"""Render an animation into a pixel-art sprite sheet.

``SpriteSheetJob`` renders the frame range, processes every frame with the
exact PixelatorPlus pipeline (optionally with one palette shared by all
frames), collapses each frame to its native pixel grid, and packs the result
into a sheet image plus an atlas description.  It works one frame per
``step()`` so the modal operator keeps Blender responsive and cancellable;
``execute()`` drains the same job synchronously for scripts and tests.

Rendered frames go to a private temporary folder instead of memory, so long
animations stay cheap.  Every scene setting the job touches is restored when
it finishes, fails, or is cancelled.
"""

import json
import os
import shutil
import tempfile

import bpy
import numpy as np

from ..core import sheet as sheet_mod
from ..core.pipeline import build_shared_palette, run_pipeline
from ..properties import collect_params
from .apply import array_to_image, custom_images, required_custom_image_keys
from .export import save_image_copy
from .hybrid import baked_output_drives_compositor
from .rendering import (
    MAP_KINDS, TemporarySettings, load_pixels, prepare_png_render, render_still,
)

SHEET_ATLAS_KEY = "pixelatorplus_sheet_atlas"
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
            if obj.type in _RENDERABLE_OBJECT_TYPES:
                return True
            if obj.type == "EMPTY" and obj.instance_collection is not None:
                pending.append((obj.instance_collection, path))
        pending.extend((child, path) for child in collection.children)
    return False


def sheet_frame_numbers(scene):
    """Frame numbers the sprite sheet renders, in order."""
    settings = scene.pixelatorplus
    if settings.sheet_use_scene_range:
        start, end = scene.frame_start, scene.frame_end
    else:
        start, end = settings.sheet_frame_start, settings.sheet_frame_end
    if end < start:
        raise ValueError(f"the sprite sheet frame range {start}-{end} is empty")
    return list(range(start, end + 1, max(1, settings.sheet_frame_step)))


class SpriteSheetJob:
    """Incremental render -> (shared palette) -> process -> pack job."""

    def __init__(self, scene):
        if scene.camera is None:
            raise ValueError("the scene needs an active camera to render a sprite sheet")
        if not scene_has_renderable_content(scene):
            raise ValueError(
                "the scene has no renderable objects; add a visible mesh, curve, "
                "or other renderable object before rendering a sprite sheet"
            )
        self.scene = scene
        self.settings = scene.pixelatorplus
        self.frame_numbers = sheet_frame_numbers(scene)
        self.scene_name = str(scene.name)
        self.sheet_options = {
            "transparent": bool(self.settings.sheet_transparent),
            "pixel_scale": int(self.settings.sheet_pixel_scale),
            "layout": self.settings.sheet_layout,
            "columns": int(self.settings.sheet_columns),
            "spacing": int(self.settings.sheet_spacing),
            "padding": int(self.settings.sheet_padding),
            "trim": bool(self.settings.sheet_trim),
            "skip_empty": bool(self.settings.sheet_skip_empty),
            "frame_step": max(1, int(self.settings.sheet_frame_step)),
            "fps": int(scene.render.fps),
            "fps_base": float(scene.render.fps_base or 1.0),
        }
        self.params = collect_params(self.settings)
        self.images = custom_images(self.settings, self.params)
        self.shared = (
            self.settings.sheet_shared_palette
            and self.params.get("quantize_type") == "CUSTOM_PALETTE"
        )
        self.palette = None  # the shared palette, when one is built
        self.paths = []
        self.cells = []
        self.grid = None
        self.phase = "render"
        self.index = 0
        self.completed = 0
        self.image = None
        # Scene maps (ID, light) the active stages read, rendered per frame.
        self.map_keys = [key for key in MAP_KINDS
                         if key in required_custom_image_keys(self.params)]
        self.map_paths = {key: [] for key in self.map_keys}
        self._frame = scene.frame_current
        self._tmp = tempfile.mkdtemp(prefix="pixelatorplus_sheet_")
        self._temp = TemporarySettings()
        try:
            self._override_scene()
        except Exception as exc:
            try:
                self.close()
            except Exception as cleanup_error:
                raise RuntimeError(
                    f"sprite-sheet setup failed ({exc}); scene cleanup also failed ({cleanup_error})"
                ) from exc
            raise

    # -- scene settings --------------------------------------------------------
    def _override_scene(self):
        prepare_png_render(self._temp, self.scene, self.sheet_options["transparent"])
        if baked_output_drives_compositor(self.scene):
            # A connected baked Image node would make every frame that one
            # static image; frames need the raw render.
            self._temp.set(self.scene.render, "use_compositing", False)
        # Per-frame compositor bakes would run for every sheet frame.
        self._temp.set(self.settings, "auto_bake_render", False)

    def close(self):
        """Restore the scene and remove temporary frames (safe to call twice)."""
        temp, self._temp = self._temp, None
        tmp, self._tmp = self._tmp, None
        if temp is None and tmp is None:
            return
        first_error = None
        if temp is not None:
            try:
                temp.restore()
            except Exception as restore_error:
                try:
                    temp.restore()
                except Exception as retry_error:
                    self._temp = temp
                    first_error = RuntimeError(
                        f"scene restore failed ({restore_error}); retry failed ({retry_error})"
                    )
        try:
            self.scene.frame_set(self._frame)
        except Exception as exc:
            if first_error is None:
                first_error = exc
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
        if first_error is not None:
            raise first_error

    # -- progress --------------------------------------------------------------
    @property
    def total_steps(self):
        return 2 * len(self.frame_numbers) + (1 if self.shared else 0) + 1

    @property
    def status(self):
        count = len(self.frame_numbers)
        if self.phase == "render":
            extra = "".join(f" + {MAP_KINDS[key][0]}" for key in self.map_keys)
            return f"Rendering frame {self.index + 1}/{count}{extra}"
        if self.phase == "palette":
            return "Building the shared palette"
        if self.phase == "process":
            return f"Pixelating frame {self.index + 1}/{count}"
        return "Packing the sprite sheet"

    # -- work ------------------------------------------------------------------
    def step(self):
        """Do one unit of work; return ``True`` when the sheet is finished."""
        if self.phase == "render":
            self._render(self.frame_numbers[self.index])
            self.index += 1
            if self.index == len(self.frame_numbers):
                self.phase, self.index = ("palette" if self.shared else "process"), 0
        elif self.phase == "palette":
            self.palette = build_shared_palette(
                ((load_pixels(path), self._frame_maps(index))
                 for index, path in enumerate(self.paths)),
                self.params, self.images,
            )
            self.phase = "process"
        elif self.phase == "process":
            self._process(self.index)
            self.index += 1
            if self.index == len(self.paths):
                self.phase = "pack"
        else:
            self._pack()
            self.completed += 1
            return True
        self.completed += 1
        return False

    def _render(self, frame):
        self.scene.frame_set(frame)
        path = os.path.join(self._tmp, f"frame_{frame:06d}.png")
        render_still(self._temp, self.scene, path)
        self.paths.append(path)
        for key in self.map_keys:
            map_path = os.path.join(self._tmp, f"{key}_{frame:06d}.png")
            map_temp = TemporarySettings()
            try:
                MAP_KINDS[key][1](map_temp, self.scene)
                render_still(map_temp, self.scene, map_path)
            finally:
                map_temp.restore()
            self.map_paths[key].append(map_path)

    def _frame_maps(self, index):
        """The scene maps (ID, light) rendered with frame ``index``."""
        return {key: load_pixels(self.map_paths[key][index]) for key in self.map_keys}

    def _process(self, index):
        images = dict(self.images)
        if self.palette is not None:
            images["shared_palette"] = self.palette
        images.update(self._frame_maps(index))
        result = run_pipeline(load_pixels(self.paths[index]), self.params, images=images)
        self.grid = result["grid"]
        cells = sheet_mod.native_frame(result["main"], self.grid,
                                       self.sheet_options["pixel_scale"])
        # Blender buffers are bottom-up; sheets and atlases are top-down.
        self.cells.append(np.flipud(cells))

    def _pack(self):
        options = self.sheet_options
        sheet, rects, numbers, trim = sheet_mod.build_sheet(
            self.cells, self.frame_numbers, options["layout"], options["columns"],
            options["spacing"], options["padding"], options["trim"], options["skip_empty"],
        )
        name = bpy.path.clean_name(self.scene_name) or "sprite"
        fps = options["fps"] / options["fps_base"]
        frame_h, frame_w = self.cells[0].shape[:2]
        atlas = sheet_mod.atlas_json(
            rects, numbers, (sheet.shape[1], sheet.shape[0]), (frame_w, frame_h),
            f"{name}.png", 1000.0 * options["frame_step"] / fps, trim, name,
            self.palette if self.shared else None,
        )
        image = array_to_image(np.ascontiguousarray(np.flipud(sheet)),
                               f"{self.scene_name} [PixelatorPlus Sheet]")
        image[SHEET_ATLAS_KEY] = json.dumps(atlas)
        self.settings.last_sheet_name = image.name
        self.image = image


def _show_in_image_editor(context, image):
    space = getattr(context, "space_data", None)
    if space is not None and getattr(space, "type", None) == "IMAGE_EDITOR":
        space.image = image


class PIXELATORPLUS_OT_render_sprite_sheet(bpy.types.Operator):
    """Render the frame range and pack the pixelated frames into a sprite sheet (Esc cancels)"""

    bl_idname = "pixelatorplus.render_sprite_sheet"
    bl_label = "Render Sprite Sheet"
    bl_options = {"REGISTER"}

    _job = None
    _timer = None
    _progress_active = False

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.scene.camera)

    def execute(self, context):
        try:
            job = SpriteSheetJob(context.scene)
        except (OSError, RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        failure = None
        try:
            while not job.step():
                pass
        except Exception as exc:
            failure = exc
        try:
            job.close()
        except Exception as exc:
            if failure is None:
                failure = exc
        if failure is not None:
            self.report({"ERROR"}, f"Sprite sheet failed: {failure}")
            return {"CANCELLED"}
        _show_in_image_editor(context, job.image)
        self._report_done(job)
        return {"FINISHED"}

    def invoke(self, context, event):
        self._job = None
        self._timer = None
        self._progress_active = False
        try:
            self._job = SpriteSheetJob(context.scene)
        except (OSError, RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        wm = context.window_manager
        try:
            self._timer = wm.event_timer_add(0.01, window=context.window)
            wm.progress_begin(0, self._job.total_steps)
            self._progress_active = True
            wm.modal_handler_add(self)
        except Exception as exc:
            self._stop(context)
            self.report({"ERROR"}, f"Could not start the sprite-sheet job: {exc}")
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._stop(context)
            self.report({"WARNING"}, "Sprite sheet cancelled")
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        try:
            done = self._job.step()
        except Exception as exc:
            self._stop(context)
            self.report({"ERROR"}, f"Sprite sheet failed: {exc}")
            return {"CANCELLED"}
        try:
            context.window_manager.progress_update(self._job.completed)
            if context.workspace is not None:
                context.workspace.status_text_set(f"{self._job.status}  (Esc to cancel)")
        except Exception as exc:
            self._stop(context)
            self.report({"ERROR"}, f"Sprite sheet UI update failed: {exc}")
            return {"CANCELLED"}
        if not done:
            return {"RUNNING_MODAL"}
        job = self._job
        self._stop(context)
        _show_in_image_editor(context, job.image)
        self._report_done(job)
        return {"FINISHED"}

    def _stop(self, context):
        wm = context.window_manager
        job, self._job = self._job, None
        timer, self._timer = self._timer, None
        first_error = None
        if timer is not None:
            try:
                wm.event_timer_remove(timer)
            except Exception as exc:
                first_error = exc
        if self._progress_active:
            self._progress_active = False
            try:
                wm.progress_end()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if context.workspace is not None:
            try:
                context.workspace.status_text_set(None)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if job is not None:
            try:
                job.close()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            self.report({"WARNING"}, f"Sprite-sheet cleanup issue: {first_error}")

    def _report_done(self, job):
        count = len(json.loads(job.image[SHEET_ATLAS_KEY])["frames"])
        width, height = job.image.size
        self.report({"INFO"}, f"Sprite sheet '{job.image.name}': {count} frames, {width}x{height}")


class PIXELATORPLUS_OT_export_sprite_sheet(bpy.types.Operator):
    """Save the sprite sheet as a PNG with a matching JSON atlas beside it"""

    bl_idname = "pixelatorplus.export_sprite_sheet"
    bl_label = "Export Sprite Sheet"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.png", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        settings = context.scene.pixelatorplus if context.scene else None
        image = bpy.data.images.get(settings.last_sheet_name) if settings else None
        return bool(image and SHEET_ATLAS_KEY in image)

    def invoke(self, context, event):
        if not self.filepath:
            image = bpy.data.images[context.scene.pixelatorplus.last_sheet_name]
            self.filepath = (bpy.path.clean_name(image.name) or "sprite_sheet") + ".png"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        image = bpy.data.images[context.scene.pixelatorplus.last_sheet_name]
        png_path = os.path.splitext(bpy.path.abspath(self.filepath))[0] + ".png"
        json_path = os.path.splitext(png_path)[0] + ".json"
        atlas = json.loads(image[SHEET_ATLAS_KEY])
        atlas["meta"]["image"] = os.path.basename(png_path)
        try:
            save_image_copy(image, png_path, "PNG")
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(atlas, handle, indent=2)
                handle.write("\n")
        except (OSError, RuntimeError) as exc:
            self.report({"ERROR"}, f"Could not export sprite sheet: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Sprite sheet saved to {png_path} (+ .json atlas)")
        return {"FINISHED"}


classes = (PIXELATORPLUS_OT_render_sprite_sheet, PIXELATORPLUS_OT_export_sprite_sheet)

register, unregister = bpy.utils.register_classes_factory(classes)
