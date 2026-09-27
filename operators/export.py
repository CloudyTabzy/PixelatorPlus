"""Export generated PixelatorPlus images in Blender's still-image formats.

The processed image exporter has two deliberate paths. ``Preserve Pixels``
uses ``Image.save`` so the NumPy result is written without changing its values;
``Blender Output Settings`` temporarily applies Blender's format, bit depth,
codec, compression, and scene color-management settings through
``Image.save_render``. Scene settings are restored even when an export fails.
"""

import os

import bpy
from bpy_extras.io_utils import ExportHelper

from ..core import lut_cube as lut_cube_mod
from ..core import quantize as quantize_mod
from .apply import image_to_array


_FORMAT_ITEMS = [
    ("PNG", "PNG", "Lossless Portable Network Graphics"),
    ("JPEG", "JPEG", "Lossy 8-bit photo export"),
    ("JPEG2000", "JPEG 2000", "JPEG 2000 export with JP2 or J2K codec"),
    ("WEBP", "WebP", "Modern lossy or lossless web image export"),
    ("BMP", "Bitmap", "Uncompressed Windows bitmap"),
    ("TARGA", "Targa", "Targa image with compression where supported"),
    ("TARGA_RAW", "Targa Raw", "Uncompressed Targa image"),
    ("TIFF", "TIFF", "Flexible TIFF export with optional compression"),
    ("OPEN_EXR", "OpenEXR", "High-dynamic-range production image"),
    ("OPEN_EXR_MULTILAYER", "OpenEXR MultiLayer", "OpenEXR container for the flat processed layer"),
    ("HDR", "Radiance HDR", "High-dynamic-range Radiance image"),
    ("DPX", "DPX", "Digital intermediate / film image"),
    ("CINEON", "Cineon", "Cineon log film image"),
    ("IRIS", "Iris", "SGI Iris image"),
]

_FORMAT_EXTENSIONS = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "JPEG2000": ".jp2",
    "WEBP": ".webp",
    "BMP": ".bmp",
    "TARGA": ".tga",
    "TARGA_RAW": ".tga",
    "TIFF": ".tif",
    "OPEN_EXR": ".exr",
    "OPEN_EXR_MULTILAYER": ".exr",
    "HDR": ".hdr",
    "DPX": ".dpx",
    "CINEON": ".cin",
    "IRIS": ".rgb",
}

_COLOR_MODE_ITEMS = [
    ("BW", "BW", "Single-channel grayscale"),
    ("RGB", "RGB", "Three-channel color"),
    ("RGBA", "RGBA", "Color with alpha channel"),
]

_COLOR_DEPTH_ITEMS = [
    ("8", "8-bit", "8 bits per channel"),
    ("10", "10-bit", "10 bits per channel where supported"),
    ("12", "12-bit", "12 bits per channel where supported"),
    ("16", "16-bit", "16 bits per channel where supported"),
    ("32", "32-bit Float", "32-bit floating-point channels where supported"),
]

_EXR_CODEC_ITEMS = [
    ("NONE", "None", "No OpenEXR compression"),
    ("PXR24", "Pxr24 (Lossy)", "Lossy OpenEXR compression"),
    ("ZIP", "ZIP", "Lossless ZIP compression"),
    ("PIZ", "PIZ", "Lossless wavelet compression"),
    ("DWAA", "DWAA (Lossy)", "Lossy OpenEXR compression"),
    ("DWAB", "DWAB (Lossy)", "Lossy OpenEXR compression optimized for scanlines"),
    ("ZIPS", "ZIPS", "Lossless ZIP scanline compression"),
    ("RLE", "RLE", "Lossless run-length compression"),
]

_JPEG2K_CODEC_ITEMS = [
    ("JP2", "JP2", "JPEG 2000 Part 1 codestream"),
    ("J2K", "J2K", "JPEG 2000 codestream"),
]

_TIFF_CODEC_ITEMS = [
    ("NONE", "None", "No TIFF compression"),
    ("DEFLATE", "Deflate", "Lossless Deflate compression"),
    ("LZW", "LZW", "Lossless LZW compression"),
    ("PACKBITS", "Pack Bits", "Run-length PackBits compression"),
]


def _runtime_items(property_name, fallback):
    """Keep the operator's menus aligned with the host Blender build."""
    try:
        enum_items = bpy.types.ImageFormatSettings.bl_rna.properties[property_name].enum_items
        supported = {item.identifier for item in enum_items}
        return tuple(item for item in fallback if item[0] in supported)
    except (AttributeError, KeyError):
        return tuple(fallback)


_RUNTIME_FORMAT_ITEMS = _runtime_items("file_format", _FORMAT_ITEMS)
_RUNTIME_COLOR_DEPTH_ITEMS = _runtime_items("color_depth", _COLOR_DEPTH_ITEMS)
_RUNTIME_EXR_CODEC_ITEMS = _runtime_items("exr_codec", _EXR_CODEC_ITEMS)
_RUNTIME_JPEG2K_CODEC_ITEMS = _runtime_items("jpeg2k_codec", _JPEG2K_CODEC_ITEMS)
_RUNTIME_TIFF_CODEC_ITEMS = _runtime_items("tiff_codec", _TIFF_CODEC_ITEMS)


def _save_image(image, filepath, file_format, quality=95):
    """Save a generated image copy while preserving its Blender data settings."""
    old = (image.filepath_raw, image.file_format, image.alpha_mode)
    image.filepath_raw = filepath
    image.file_format = file_format
    image.alpha_mode = "STRAIGHT"
    try:
        image.save(filepath=filepath, quality=quality, save_copy=True)
    finally:
        (image.filepath_raw, image.file_format, image.alpha_mode) = old


def _ensure_extension(filepath, file_format):
    extension = _FORMAT_EXTENSIONS[file_format]
    root, _ = os.path.splitext(filepath)
    return root + extension


def _default_image_filepath(image, file_format):
    """Build a safe, descriptive filename from an image datablock name."""
    stem = bpy.path.clean_name(image.name)
    if not stem:
        stem = "pixelatorplus_output"
    return _ensure_extension(stem, file_format)


def set_still_format(image_settings, file_format):
    """Select a still-image ``file_format`` on ImageFormatSettings.

    Blender 5.x validates ``file_format`` against ``media_type``: a scene set
    to video output accepts only FFMPEG, and multilayer EXR needs its own
    media type.  Older versions have no ``media_type``.
    """
    if hasattr(image_settings, "media_type"):
        image_settings.media_type = (
            "MULTI_LAYER_IMAGE" if file_format == "OPEN_EXR_MULTILAYER" else "IMAGE"
        )
    image_settings.file_format = file_format


def format_setting_names(image_settings, names):
    """Settings to save and restore, with ``media_type`` first where it exists.

    Restoring in this order lets a video-output scene get its media type back
    before its FFMPEG ``file_format`` becomes valid again.
    """
    return (("media_type",) if hasattr(image_settings, "media_type") else ()) + tuple(names)


_DEPTHS = ("8", "10", "12", "16", "32")
_COLOR_MODE_FALLBACKS = {"RGBA": ("RGB", "BW"), "RGB": ("RGBA", "BW"), "BW": ("RGB", "RGBA")}


def _set_supported(settings, name, candidates):
    """Assign the first value the current file format accepts; return it or ``None``.

    Which depths, color modes, and codecs are valid depends on the format
    (EXR has no 8-bit, JPEG no alpha), and Blender rejects the rest.
    """
    for value in candidates:
        try:
            setattr(settings, name, value)
        except (TypeError, ValueError):
            continue
        return value
    return None


def _nearest_depths(depth):
    """``depth`` followed by the other bit depths, nearest first."""
    wanted = int(depth)
    return tuple(sorted(_DEPTHS, key=lambda value: (abs(int(value) - wanted), -int(value))))


def _save_with_blender_settings(image, filepath, options, scene):
    """Save with temporary scene output settings, restoring the scene afterward.

    Returns a list of ``"setting: requested -> used"`` notes for options the
    chosen format does not support.
    """
    settings = scene.render.image_settings
    names = format_setting_names(settings, (
        "file_format", "color_mode", "color_depth", "quality", "compression",
        "exr_codec", "jpeg2k_codec", "tiff_codec", "use_preview",
        "color_management",
    ))
    old = {name: getattr(settings, name) for name in names}
    notes = []
    file_format = options["format"]
    if file_format == "OPEN_EXR_MULTILAYER":
        # save_render writes render layers; a processed image is one flat
        # layer, which Blender only saves this way as regular OpenEXR.
        file_format = "OPEN_EXR"
        notes.append("format: OpenEXR MultiLayer -> OpenEXR")
    try:
        set_still_format(settings, file_format)
        for name, candidates in (
            ("color_mode", (options["color_mode"],) + _COLOR_MODE_FALLBACKS[options["color_mode"]]),
            ("color_depth", _nearest_depths(options["color_depth"])),
        ):
            used = _set_supported(settings, name, candidates)
            if used is not None and used != candidates[0]:
                notes.append(f"{name.replace('_', ' ')}: {candidates[0]} -> {used}")
        settings.quality = options["quality"]
        settings.compression = options["compression"]
        # Codecs only apply to their own formats; keep the default elsewhere.
        for name in ("exr_codec", "jpeg2k_codec", "tiff_codec"):
            _set_supported(settings, name, (options[name],))
        settings.use_preview = options["use_preview"]
        settings.color_management = "FOLLOW_SCENE"
        image.save_render(filepath, scene=scene, quality=options["quality"])
    finally:
        for name, value in old.items():
            setattr(settings, name, value)
    return notes


class PIXELATORPLUS_OT_export_output(bpy.types.Operator, ExportHelper):
    """Save the last processed PixelatorPlus output in a chosen still format"""

    bl_idname = "pixelatorplus.export_output"
    bl_label = "Export Processed Image"
    filename_ext = ".png"
    filter_glob: bpy.props.StringProperty(
        default="*.png;*.jpg;*.jpeg;*.jp2;*.j2k;*.webp;*.bmp;*.tga;*.tif;*.tiff;*.exr;*.hdr;*.dpx;*.cin;*.rgb",
        options={"HIDDEN"},
    )
    filepath: bpy.props.StringProperty(default="pixelatorplus_output.png")
    export_format: bpy.props.EnumProperty(
        name="Format", items=_RUNTIME_FORMAT_ITEMS, default="PNG",
    )
    export_mode: bpy.props.EnumProperty(
        name="Export Mode",
        items=[
            ("PIXELS", "Preserve Pixels", "Write the generated PixelatorPlus values directly"),
            ("BLENDER", "Blender Output Settings", "Use temporary Blender format and color-management settings"),
        ],
        default="PIXELS",
    )
    color_mode: bpy.props.EnumProperty(
        name="Color Mode", items=_COLOR_MODE_ITEMS, default="RGBA",
    )
    color_depth: bpy.props.EnumProperty(
        name="Color Depth", items=_RUNTIME_COLOR_DEPTH_ITEMS, default="8",
    )
    quality: bpy.props.IntProperty(
        name="Quality", description="Lossy quality and format quality setting",
        default=95, min=1, max=100, subtype="PERCENTAGE",
    )
    compression: bpy.props.IntProperty(
        name="Compression", description="PNG/TIFF and compatible codec compression setting",
        default=15, min=0, max=100, subtype="PERCENTAGE",
    )
    exr_codec: bpy.props.EnumProperty(
        name="OpenEXR Codec", items=_RUNTIME_EXR_CODEC_ITEMS, default="ZIP",
    )
    jpeg2k_codec: bpy.props.EnumProperty(
        name="JPEG 2000 Codec", items=_RUNTIME_JPEG2K_CODEC_ITEMS, default="JP2",
    )
    tiff_codec: bpy.props.EnumProperty(
        name="TIFF Codec", items=_RUNTIME_TIFF_CODEC_ITEMS, default="DEFLATE",
    )
    use_preview: bpy.props.BoolProperty(
        name="Embed Preview", default=False,
        description="Embed a preview when the selected Blender format supports it",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_format")
        layout.prop(self, "export_mode")
        layout.prop(self, "quality", slider=True)
        if self.export_mode == "BLENDER":
            layout.prop(self, "color_mode")
            layout.prop(self, "color_depth")
            layout.prop(self, "compression", slider=True)
            layout.prop(self, "exr_codec")
            layout.prop(self, "jpeg2k_codec")
            layout.prop(self, "tiff_codec")
            layout.prop(self, "use_preview")
            layout.label(text="Uses the scene view transform temporarily; scene settings are restored.", icon="INFO")
        else:
            layout.label(text="Generated pixel values are preserved; quality applies to lossy formats.", icon="INFO")

    def invoke(self, context, event):
        s = context.scene.pixelatorplus if context.scene else None
        image = bpy.data.images.get(s.last_output_name) if s else None
        if image is not None and self.filepath in ("", "pixelatorplus_output.png"):
            self.filepath = _default_image_filepath(image, self.export_format)
        return ExportHelper.invoke(self, context, event)

    @classmethod
    def poll(cls, context):
        s = context.scene.pixelatorplus if context.scene else None
        return bool(s and s.last_output_name and bpy.data.images.get(s.last_output_name))

    def check(self, context):
        filepath = _ensure_extension(self.filepath, self.export_format)
        if filepath != self.filepath:
            self.filepath = filepath
            return True
        return False

    def execute(self, context):
        s = context.scene.pixelatorplus
        image = bpy.data.images[s.last_output_name]
        filepath = _ensure_extension(self.filepath, self.export_format)
        try:
            notes = []
            if self.export_mode == "BLENDER":
                notes = _save_with_blender_settings(image, filepath, {
                    "format": self.export_format,
                    "color_mode": self.color_mode,
                    "color_depth": self.color_depth,
                    "quality": self.quality,
                    "compression": self.compression,
                    "exr_codec": self.exr_codec,
                    "jpeg2k_codec": self.jpeg2k_codec,
                    "tiff_codec": self.tiff_codec,
                    "use_preview": self.use_preview,
                }, context.scene)
            else:
                _save_image(image, filepath, self.export_format, quality=self.quality)
        except (OSError, RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, f"Could not export image: {exc}")
            return {"CANCELLED"}
        if notes:
            self.report({"WARNING"}, f"Saved {filepath}; adjusted for this format: "
                        + ", ".join(notes))
            return {"FINISHED"}
        self.report({"INFO"}, f"Processed image saved to {filepath}")
        return {"FINISHED"}


class PIXELATORPLUS_OT_export_palette(bpy.types.Operator, ExportHelper):
    """Save the last generated palette swatch as a PNG"""

    bl_idname = "pixelatorplus.export_palette"
    bl_label = "Export Palette PNG"
    filename_ext = ".png"
    filepath: bpy.props.StringProperty(default="palette.png")

    def invoke(self, context, event):
        s = context.scene.pixelatorplus if context.scene else None
        image = bpy.data.images.get(s.last_palette_name) if s else None
        if image is not None and self.filepath in ("", "palette.png"):
            self.filepath = _default_image_filepath(image, "PNG")
        return ExportHelper.invoke(self, context, event)

    @classmethod
    def poll(cls, context):
        s = context.scene.pixelatorplus if context.scene else None
        return bool(s and s.last_palette_name and bpy.data.images.get(s.last_palette_name))

    def execute(self, context):
        s = context.scene.pixelatorplus
        image = bpy.data.images[s.last_palette_name]
        _save_image(image, self.filepath, "PNG")
        self.report({"INFO"}, f"Palette saved to {self.filepath}")
        return {"FINISHED"}


class PIXELATORPLUS_OT_export_lut(bpy.types.Operator, ExportHelper):
    """Save the last generated 4K LUT as a PNG"""

    bl_idname = "pixelatorplus.export_lut"
    bl_label = "Export 4K LUT PNG"
    filename_ext = ".png"
    filepath: bpy.props.StringProperty(default="lut_4k.png")

    def invoke(self, context, event):
        s = context.scene.pixelatorplus if context.scene else None
        image = bpy.data.images.get(s.last_lut_name) if s else None
        if image is not None and self.filepath in ("", "lut_4k.png"):
            self.filepath = _default_image_filepath(image, "PNG")
        return ExportHelper.invoke(self, context, event)

    @classmethod
    def poll(cls, context):
        s = context.scene.pixelatorplus if context.scene else None
        return bool(s and s.last_lut_name and bpy.data.images.get(s.last_lut_name))

    def execute(self, context):
        s = context.scene.pixelatorplus
        image = bpy.data.images[s.last_lut_name]
        _save_image(image, self.filepath, "PNG")
        self.report({"INFO"}, f"LUT saved to {self.filepath}")
        return {"FINISHED"}


class PIXELATORPLUS_OT_export_palette_json(bpy.types.Operator, ExportHelper):
    """Save the generated palette as a portable PixelatorPlus JSON asset."""

    bl_idname = "pixelatorplus.export_palette_json"
    bl_label = "Export Palette JSON"
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})
    filepath: bpy.props.StringProperty(default="pixelatorplus_palette.json")

    @classmethod
    def poll(cls, context):
        s = context.scene.pixelatorplus if context.scene else None
        return bool(s and s.last_palette_name and bpy.data.images.get(s.last_palette_name))

    def invoke(self, context, event):
        s = context.scene.pixelatorplus if context.scene else None
        image = bpy.data.images.get(s.last_palette_name) if s else None
        if image is not None and self.filepath == "pixelatorplus_palette.json":
            self.filepath = bpy.path.clean_name(image.name) + ".json"
        return ExportHelper.invoke(self, context, event)

    def check(self, context):
        root, _ = os.path.splitext(self.filepath)
        filepath = root + ".json"
        if filepath != self.filepath:
            self.filepath = filepath
            return True
        return False

    def execute(self, context):
        s = context.scene.pixelatorplus
        image = bpy.data.images.get(s.last_palette_name)
        try:
            colors = quantize_mod.palette_from_image(image_to_array(image))
            from ..core.palette import PaletteAsset

            PaletteAsset(colors, image.name, {"source": "PixelatorPlus output"}).save_json(self.filepath)
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, f"Could not export palette JSON: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Palette JSON saved to {self.filepath}")
        return {"FINISHED"}


_CUBE_SIZE_ITEMS = [
    ("8", "8³", "Compact portable LUT"),
    ("16", "16³", "Balanced portable LUT"),
    ("32", "32³", "Higher fidelity portable LUT"),
    ("64", "64³", "Large portable LUT"),
]


class PIXELATORPLUS_OT_export_cube(bpy.types.Operator, ExportHelper):
    """Export the latest palette or native 4K LUT as a standard `.cube`."""

    bl_idname = "pixelatorplus.export_cube"
    bl_label = "Export .cube LUT"
    filename_ext = ".cube"
    filter_glob: bpy.props.StringProperty(default="*.cube", options={"HIDDEN"})
    filepath: bpy.props.StringProperty(default="pixelatorplus_lut.cube")
    cube_size: bpy.props.EnumProperty(name="Cube Size", items=_CUBE_SIZE_ITEMS, default="16")

    @classmethod
    def poll(cls, context):
        s = context.scene.pixelatorplus if context.scene else None
        return bool(s and (
            (s.last_lut_name and bpy.data.images.get(s.last_lut_name)) or
            (s.last_palette_name and bpy.data.images.get(s.last_palette_name))
        ))

    def invoke(self, context, event):
        s = context.scene.pixelatorplus if context.scene else None
        image = bpy.data.images.get(s.last_lut_name) if s and s.last_lut_name else None
        if image is None and s and s.last_palette_name:
            image = bpy.data.images.get(s.last_palette_name)
        if image is not None and self.filepath == "pixelatorplus_lut.cube":
            self.filepath = bpy.path.clean_name(image.name) + ".cube"
        return ExportHelper.invoke(self, context, event)

    def draw(self, context):
        self.layout.prop(self, "cube_size")
        self.layout.label(text="Uses the latest 4K LUT, or the latest palette as a color transform.", icon="INFO")

    def check(self, context):
        root, _ = os.path.splitext(self.filepath)
        filepath = root + ".cube"
        if filepath != self.filepath:
            self.filepath = filepath
            return True
        return False

    def execute(self, context):
        s = context.scene.pixelatorplus
        try:
            image = bpy.data.images.get(s.last_lut_name) if s.last_lut_name else None
            if image is not None:
                lut = lut_cube_mod.cube_from_tiled_lut(
                    image_to_array(image)[..., :3], int(self.cube_size), image.name,
                )
            else:
                image = bpy.data.images.get(s.last_palette_name)
                colors = quantize_mod.palette_from_image(image_to_array(image))
                lut = lut_cube_mod.cube_from_palette(colors, int(self.cube_size), image.name)
            lut_cube_mod.export_cube(lut, self.filepath)
        except (OSError, ValueError, TypeError) as exc:
            self.report({"ERROR"}, f"Could not export .cube LUT: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f".cube LUT saved to {self.filepath}")
        return {"FINISHED"}


classes = (
    PIXELATORPLUS_OT_export_output,
    PIXELATORPLUS_OT_export_palette,
    PIXELATORPLUS_OT_export_lut,
    PIXELATORPLUS_OT_export_palette_json,
    PIXELATORPLUS_OT_export_cube,
)


register, unregister = bpy.utils.register_classes_factory(classes)
