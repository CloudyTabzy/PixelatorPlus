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
from ..core.pipeline import PipelineError, build_shared_palette, run_pipeline
from ..properties import collect_params
from .apply import array_to_image, custom_images, image_to_array
from .export import format_setting_names, save_image_copy, set_still_format
from .hybrid import baked_output_drives_compositor

SHEET_ATLAS_KEY = "pixelatorplus_sheet_atlas"


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
        self.scene = scene
        self.settings = scene.pixelatorplus
        self.frame_numbers = sheet_frame_numbers(scene)
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
        self._tmp = tempfile.mkdtemp(prefix="pixelatorplus_sheet_")
        self._saved = {}
        self._override_scene()

    # -- scene settings --------------------------------------------------------
    def _override_scene(self):
        render = self.scene.render
        formats = render.image_settings
        self._saved = {
            "frame": self.scene.frame_current,
            "render": {name: getattr(render, name)
                       for name in ("filepath", "use_file_extension", "film_transparent",
                                    "use_compositing")},
            "format": {name: getattr(formats, name)
                       for name in format_setting_names(
                           formats, ("file_format", "color_mode", "color_depth"))},
            # Per-frame compositor bakes would run for every sheet frame.
            "auto_bake": self.settings.auto_bake_render,
        }
        render.use_file_extension = True
        if baked_output_drives_compositor(self.scene):
            # A connected baked Image node would make every frame that one
            # static image; frames need the raw render.
            render.use_compositing = False
        if self.settings.sheet_transparent:
            render.film_transparent = True
        set_still_format(formats, "PNG")
        formats.color_mode = "RGBA"
        formats.color_depth = "8"
        self.settings.auto_bake_render = False

    def close(self):
        """Restore the scene and remove temporary frames (safe to call twice)."""
        if self._saved:
            render = self.scene.render
            for name, value in self._saved["format"].items():
                setattr(render.image_settings, name, value)
            for name, value in self._saved["render"].items():
                setattr(render, name, value)
            self.settings.auto_bake_render = self._saved["auto_bake"]
            self.scene.frame_set(self._saved["frame"])
            self._saved = {}
        shutil.rmtree(self._tmp, ignore_errors=True)

    # -- progress --------------------------------------------------------------
    @property
    def total_steps(self):
        return 2 * len(self.frame_numbers) + (1 if self.shared else 0) + 1

    @property
    def status(self):
        count = len(self.frame_numbers)
        if self.phase == "render":
            return f"Rendering frame {self.index + 1}/{count}"
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
                (self._load(path) for path in self.paths), self.params, self.images
            )
            self.phase = "process"
        elif self.phase == "process":
            self._process(self.paths[self.index])
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
        path = os.path.join(self._tmp, f"frame_{frame:06d}.png")
        self.scene.frame_set(frame)
        self.scene.render.filepath = path
        bpy.ops.render.render(write_still=True, scene=self.scene.name)
        if not os.path.isfile(path):
            raise RuntimeError(f"Blender did not write rendered frame {frame}")
        self.paths.append(path)

    @staticmethod
    def _load(path):
        image = bpy.data.images.load(path, check_existing=False)
        try:
            return image_to_array(image)
        finally:
            bpy.data.images.remove(image)

    def _process(self, path):
        images = dict(self.images)
        if self.palette is not None:
            images["shared_palette"] = self.palette
        result = run_pipeline(self._load(path), self.params, images=images)
        self.grid = result["grid"]
        cells =sheet_mod.native_frame(result["main"], self.grid, self.settings.sheet_pixel_scale)
        # Blender buffers are bottom-up; sheets and atlases are top-down.
        self.cells.append(np.flipud(cells))

    def _pack(self):
        s = self.settings
        sheet, rects, numbers, trim = sheet_mod.build_sheet(
            self.cells, self.frame_numbers, s.sheet_layout, s.sheet_columns,
            s.sheet_spacing, s.sheet_padding, s.sheet_trim, s.sheet_skip_empty,
        )
        name = bpy.path.clean_name(self.scene.name) or "sprite"
        render = self.scene.render
        fps = render.fps / (render.fps_base or 1.0)
        frame_h, frame_w = self.cells[0].shape[:2]
        atlas = sheet_mod.atlas_json(
            rects, numbers, (sheet.shape[1], sheet.shape[0]), (frame_w, frame_h),
            f"{name}.png", 1000.0 * max(1, s.sheet_frame_step) / fps, trim, name,
            self.palette if self.shared else None,
        )
        image = array_to_image(np.ascontiguousarray(np.flipud(sheet)),
                               f"{self.scene.name} [PixelatorPlus Sheet]")
        image[SHEET_ATLAS_KEY] = json.dumps(atlas)
        s.last_sheet_name = image.name
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

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.scene.camera)

    def execute(self, context):
        try:
            job = SpriteSheetJob(context.scene)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        try:
            while not job.step():
                pass
        except (PipelineError, ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, f"Sprite sheet failed: {exc}")
            return {"CANCELLED"}
        finally:
            job.close()
        _show_in_image_editor(context, job.image)
        self._report_done(job)
        return {"FINISHED"}

    def invoke(self, context, event):
        try:
            self._job = SpriteSheetJob(context.scene)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        wm.progress_begin(0, self._job.total_steps)
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
        except (PipelineError, ValueError, RuntimeError) as exc:
            self._stop(context)
            self.report({"ERROR"}, f"Sprite sheet failed: {exc}")
            return {"CANCELLED"}
        context.window_manager.progress_update(self._job.completed)
        if context.workspace is not None:
            context.workspace.status_text_set(f"{self._job.status}  (Esc to cancel)")
        if not done:
            return {"RUNNING_MODAL"}
        job = self._job
        self._stop(context)
        _show_in_image_editor(context, job.image)
        self._report_done(job)
        return {"FINISHED"}

    def _stop(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        wm.progress_end()
        if context.workspace is not None:
            context.workspace.status_text_set(None)
        if self._job is not None:
            self._job.close()

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
