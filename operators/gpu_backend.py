"""Optional GPU compute backends for Blender-side image operations.

The core remains free of Blender imports. Callers inject this optional
accelerator; it returns ``None`` for unsupported inputs so the established
NumPy path remains the fallback.
"""

import numpy as np

from ..core.quantize import _nearest_indices
from ..core.palettes import resolve as resolve_builtin

_GPU_MODULE = None
_GPU_BACKEND_PROBED = False
_GPU_MIN_PALETTE_PIXELS = 65536
_GPU_TILE_PIXELS = 1048576


def _palette_apply_supported(params, image_shape):
    """Whether this pipeline run reaches the RGB finite-palette lookup path."""
    height, width = image_shape[:2]
    if height * width < _GPU_MIN_PALETTE_PIXELS:
        return False
    if str(params.get("apply_palette_mode", "RGB")).upper() != "RGB":
        return False
    if str(params.get("diffusion", "NONE")).upper() != "NONE":
        return False
    stage_enabled = params.get("v3_stage_enabled", {})
    if isinstance(stage_enabled, dict) and not stage_enabled.get("quantize", True):
        return False

    qtype = str(params.get("quantize_type", "NONE")).upper()
    if qtype == "CUSTOM_PALETTE":
        return True
    if qtype != "LUT":
        return False
    lut = str(params.get("lut", "AMIGA")).upper()
    if lut == "CUSTOM_PALETTE":
        return True
    if lut in ("CUSTOM_LUT", "CUBE_LUT"):
        return False
    try:
        kind, _data = resolve_builtin(lut)
    except (KeyError, ValueError):
        return False
    return kind == "palette"


class PaletteApplyAccelerator:
    """Nearest-palette RGB mapping with a compute shader and CPU fallback."""

    def __init__(self, gpu):
        self.gpu = gpu
        self.shader = None
        self.enabled = True
        self.used = False
        self.error = ""

    def begin_run(self):
        """Reset the per-pipeline usage flag."""
        self.used = False

    def _get_shader(self):
        if self.shader is not None:
            return self.shader
        info = self.gpu.types.GPUShaderCreateInfo()
        info.image(0, "RGBA32F", "FLOAT_2D", "source_image", qualifiers={"READ"})
        info.image(1, "RGBA32F", "FLOAT_2D", "palette_image", qualifiers={"READ"})
        info.image(2, "RGBA32F", "FLOAT_2D", "output_image", qualifiers={"WRITE"})
        info.push_constant("IVEC2", "image_size")
        info.push_constant("INT", "palette_size")
        info.local_group_size(8, 8, 1)
        info.compute_source("""
void main()
{
  ivec2 xy = ivec2(gl_GlobalInvocationID.xy);
  if (xy.x >= image_size.x || xy.y >= image_size.y) {
    return;
  }

  precise vec3 color = imageLoad(source_image, xy).rgb;
  precise float best_distance = 3.402823e38;
  int best_index = 0;
  for (int i = 0; i < palette_size; i++) {
    precise vec3 delta = color - imageLoad(palette_image, ivec2(i, 0)).rgb;
    precise float distance = delta.r * delta.r;
    distance = distance + delta.g * delta.g;
    distance = distance + delta.b * delta.b;
    if (distance < best_distance) {
      best_distance = distance;
      best_index = i;
    }
  }
  vec4 entry = imageLoad(palette_image, ivec2(best_index, 0));
  imageStore(output_image, xy, vec4(entry.rgb, entry.a));
}
""")
        self.shader = self.gpu.shader.create_from_info(info)
        return self.shader

    def apply_palette(self, image, palette, apply_space="RGB", return_indices=False):
        """Return a quantized image, or ``None`` so the caller uses NumPy."""
        if not self.enabled or str(apply_space).upper() != "RGB":
            return None
        source = np.asarray(image, dtype=np.float32)[..., :3]
        colors = np.asarray(palette, dtype=np.float32)[:, :3]
        h, w = source.shape[:2]
        if (h * w < _GPU_MIN_PALETTE_PIXELS
                or colors.shape[0] < 1 or colors.shape[0] > 256):
            return None

        try:
            mapped = self._apply_rgb(source, colors, return_indices)
            if mapped is None:
                self.error = self.error or "image dimensions exceed GPU texture limits"
                return None
            result, indices = mapped
        except MemoryError as exc:
            self.error = str(exc)
            return None
        except Exception as exc:
            # GPU drivers and contexts vary. Disable this backend after an API
            # or shader failure, then let current and future calls use CPU.
            self.enabled = False
            self.error = str(exc)
            return None
        self.used = True
        return (result, indices) if return_indices else result

    def _apply_rgb(self, source, palette, return_indices):
        h, w = source.shape[:2]
        k = palette.shape[0]
        max_texture_get = getattr(self.gpu.capabilities, "max_texture_size_get", None)
        max_texture_size = max_texture_get() if callable(max_texture_get) else None
        if max_texture_size is not None and w > max_texture_size:
            self.error = "image width exceeds the GPU texture-size limit"
            return None
        canonical = (
            _nearest_indices(palette, palette) if return_indices
            else np.arange(k, dtype=np.int32)
        )
        palette_rgba = np.ones((1, k, 4), dtype=np.float32)
        palette_rgba[0, :, :3] = palette
        palette_rgba[0, :, 3] = canonical
        palette_buffer = self.gpu.types.Buffer(
            "FLOAT", palette_rgba.size, palette_rgba.ravel()
        )
        palette_texture = self.gpu.types.GPUTexture(
            (k, 1), format="RGBA32F", data=palette_buffer
        )
        shader = self._get_shader()
        shader.image("palette_image", palette_texture)
        shader.uniform_int("palette_size", k)

        output = np.empty((h, w, 3), dtype=np.float32)
        output_indices = np.empty((h, w), dtype=np.int32) if return_indices else None
        rows_per_tile = max(1, _GPU_TILE_PIXELS // w)
        if max_texture_size is not None:
            rows_per_tile = min(rows_per_tile, max_texture_size)
        for y0 in range(0, h, rows_per_tile):
            y1 = min(h, y0 + rows_per_tile)
            tile_h = y1 - y0
            tile_rgba = np.empty((tile_h, w, 4), dtype=np.float32)
            tile_rgba[..., :3] = source[y0:y1]
            tile_rgba[..., 3] = 1.0
            source_buffer = self.gpu.types.Buffer(
                "FLOAT", tile_rgba.size, tile_rgba.ravel()
            )
            source_texture = self.gpu.types.GPUTexture(
                (w, tile_h), format="RGBA32F", data=source_buffer
            )
            output_texture = self.gpu.types.GPUTexture(
                (w, tile_h), format="RGBA32F"
            )
            shader.image("source_image", source_texture)
            shader.image("output_image", output_texture)
            shader.uniform_int("image_size", (w, tile_h))
            self.gpu.compute.dispatch(
                shader, (w + 7) // 8, (tile_h + 7) // 8, 1
            )
            rgba = np.asarray(output_texture.read(), dtype=np.float32)
            if rgba.shape != (tile_h, w, 4):
                raise RuntimeError("GPU palette readback has unexpected dimensions")
            output[y0:y1] = rgba[..., :3]
            if output_indices is not None:
                output_indices[y0:y1] = np.rint(rgba[..., 3]).astype(np.int32)
            del output_texture, source_texture, source_buffer, tile_rgba, rgba
        del palette_texture, palette_buffer
        return output, output_indices


def get_palette_accelerator(params=None, image_shape=None):
    """Return the detected GPU backend when this run can use it, else ``None``."""
    global _GPU_MODULE, _GPU_BACKEND_PROBED
    if params is not None and image_shape is not None:
        if not _palette_apply_supported(params, image_shape):
            return None
    if _GPU_BACKEND_PROBED:
        return PaletteApplyAccelerator(_GPU_MODULE) if _GPU_MODULE is not None else None
    _GPU_BACKEND_PROBED = True
    try:
        import gpu

        compute = getattr(gpu, "compute", None)
        if not callable(getattr(compute, "dispatch", None)):
            return None
        gpu.init()
        backend_type = gpu.platform.backend_type_get()
        device_type = gpu.platform.device_type_get()
        if backend_type in ("NONE", "UNKNOWN") or device_type in ("SOFTWARE", "UNKNOWN"):
            return None
        capabilities = gpu.capabilities
        image_support = getattr(capabilities, "shader_image_load_store_support_get", None)
        if callable(image_support) and not image_support():
            return None
        probe = gpu.types.Buffer("FLOAT", 4, (0.0, 0.0, 0.0, 0.0))
        memoryview(probe)
        _GPU_MODULE = gpu
    except Exception:
        # CPU processing remains supported if the GPU context, driver, or
        # required Blender API is unavailable.
        _GPU_MODULE = None
    return PaletteApplyAccelerator(_GPU_MODULE) if _GPU_MODULE is not None else None
