"""PixelatorPlus v3 canonical stage executor.

The executor remains compatible with the v2 flat settings dictionary while
supporting palette-aware dithering, expanded diffusion, `.cube` LUTs,
pixel-art scaling, tone bands, sprite cleanup and lines, and a deterministic
display-finish stack.  V3 makes the dependency order explicit (pixelate ->
posterize -> tone bands -> dither -> quantize -> sprite -> finish), allows
each stage to be disabled through the canonical stage stack, and adds
PixelatorPlus-native palette-lock and grid-coherence policies without copying
another compositor's node runtime.
"""

import numpy as np

from . import dither as dither_mod
from . import finish as finish_mod
from . import lut as lut_mod
from . import lut_cube as lut_cube_mod
from . import palette as palette_mod
from . import posterize as posterize_mod
from . import quantize as quantize_mod
from . import shading as shading_mod
from . import sprite as sprite_mod
from .palettes import resolve as resolve_builtin
from .plan import normalize_plan, plan_to_params, stage_types
from .pixelate import (
    compute_grid,
    downscale_area,
    downscale_nearest,
    pixelate,
    resample_preview,
    upscale_nearest,
)
from .stages import resize_mask


_MASK_WEIGHT_KEYS = ("huge", "big", "large", "medium", "fine", "sharp", "pixel_perfect")


class PipelineError(ValueError):
    """User-facing pipeline misconfiguration (e.g. missing custom image)."""


def _checkpoint(progress, cancel, amount, stage):
    """Report a stage boundary and honor a caller-owned cancellation flag."""
    if callable(cancel) and cancel():
        raise PipelineError(f"PixelatorPlus pipeline cancelled during {stage}")
    if callable(progress):
        progress(float(np.clip(amount, 0.0, 1.0)), stage)


def _seed(params):
    qseed = params.get("quantize_seed")
    if qseed is None:
        return int(params.get("random_seed", 0)) + 1
    return int(round(float(qseed) * 1000))


def _palette_operations(colors, params, images=None):
    """Apply optional palette editing operations after extraction."""
    images = images or {}
    colors = palette_mod.trim_palette(colors) if params.get("palette_trim", False) else np.asarray(colors, dtype=np.float32)
    sort_mode = params.get("palette_sort_mode", "NONE")
    if sort_mode != "NONE":
        colors = palette_mod.sort_palette(colors, sort_mode)
    shift = int(params.get("palette_shift", 0))
    if shift:
        colors = palette_mod.shift_palette(colors, shift)
    replacement = images.get("custom_palette_replace")
    if replacement is not None:
        replacement = quantize_mod.palette_from_image(replacement)
        colors = palette_mod.replace_palette(
            colors,
            replacement,
            params.get("palette_replace_threshold", 1.0),
            params.get("apply_palette_mode", "RGB"),
        )
    return np.clip(colors, 0.0, 1.0).astype(np.float32)


def _palette_samples(image, grid, alpha, params):
    """Return the ``(N, 3)`` colors a generated palette is built from.

    Samples the full-resolution ``image`` or, with Use Pixelated, the cell
    ``grid``.  Fully transparent pixels (a render's empty background) are
    skipped: nobody sees them, yet they would cost a palette entry and skew
    forced darkest/brightest colors.  Opaque images keep every pixel, in
    order, so their palettes are unchanged.
    """
    if params.get("use_pixelated_for_quantize", False):
        gh, gw = grid.shape[:2]
        if params.get("downscale_mode", "NEAREST") == "NEAREST_SOFTER":
            alpha = downscale_area(alpha, gw, gh)
        else:
            alpha = downscale_nearest(alpha, gw, gh)
        image = grid
    colors = np.asarray(image, dtype=np.float32)[..., :3].reshape(-1, 3)
    visible = np.asarray(alpha).reshape(-1) > 1e-6
    if visible.any() and not visible.all():
        colors = colors[visible]
    return colors


def _generated_palette(source, params, images=None):
    """Build the selected generated palette from ``(N, 3)`` sample colors."""
    method = str(params.get("palette_extract_method", "KMEANS")).upper()
    if method == "RAMPS":
        colors = palette_mod.extract_ramps(
            source,
            ramps=params.get("palette_ramp_count", 4),
            steps=params.get("palette_ramp_steps", 4),
            hue_shift=params.get("palette_ramp_hue_shift", 20.0),
            seed=_seed(params),
            quality=params.get("quantize_quality", 2),
        )
    elif method in ("FREQUENCY", "EXACT"):
        colors = palette_mod.extract_palette(
            source,
            method=method,
            max_colors=params.get("k_num_colors", 32),
            space=params.get("color_mode", "RGB"),
            quality=params.get("quantize_quality", 2),
            seed=_seed(params),
            gamma=params.get("gamma", 1.0),
            force_colors=params.get("force_colors", "NONE"),
        )
    else:
        qseed = _seed(params)
        colors = quantize_mod.kmeans_palette(
            source.reshape(-1, 3),
            params.get("k_num_colors", 32),
            space=params.get("color_mode", "RGB"),
            quality=params.get("quantize_quality", 2),
            init_mode=int(params.get("initialize_mode", 1)),
            gamma=params.get("gamma", 1.0),
            force_colors=params.get("force_colors", "NONE"),
            seed=qseed,
            chroma_importance=params.get("chroma_importance"),
        )
    return _palette_operations(colors, params, images)


def _generated_or_shared_palette(image, grid, alpha, params, images):
    """The generated palette, or the animation-wide one when supplied.

    ``images["shared_palette"]`` (``(K, 3)``, from :func:`build_shared_palette`)
    replaces per-frame generation, so every frame of an animation uses the
    identical colors.  Palette edits were already applied when it was built.
    """
    shared = images.get("shared_palette")
    if shared is not None:
        return np.asarray(shared, dtype=np.float32)[:, :3]
    return _generated_palette(_palette_samples(image, grid, alpha, params), params, images)


def build_shared_palette(frames, params, images=None, samples_per_frame=65536):
    """Generate one palette from several frames so an animation never flickers.

    ``frames`` is an iterable of ``(h, w, 4)`` float32 images (it may be a
    generator that loads frames lazily).  Each frame runs the stages before
    quantization, and up to ``samples_per_frame`` evenly spaced visible colors
    per frame are pooled; the pool then goes through the normal generated
    palette workflow (extraction method, forced colors, sort, shift, trim,
    replacement).  Returns ``(K, 3)`` float32 for ``images["shared_palette"]``.
    """
    images = {key: value for key, value in dict(images or {}).items() if key != "shared_palette"}
    prep = dict(
        params,
        quantize_type="NONE", finish_enabled=False, sprite_cleanup=False,
        sprite_outline="NONE", sprite_part_lines=False, preview_dither_mask=False,
        output_palette=False,
        output_lut=False, output_default_lut=False, v3_palette_lock="OFF",
    )
    if str(params.get("dither_strategy", "OVERLAY")).upper() == "PALETTE_THRESHOLD":
        # Threshold dithering chooses between palette colors; there is no
        # palette yet, and the undithered colors are the right samples.
        prep["dither_type"] = "NONE"
    pooled = []
    for frame in frames:
        result = run_pipeline(frame, prep, images)
        main = result["main"]
        gw, gh = result["grid"]
        samples = _palette_samples(
            main[..., :3], downscale_nearest(main[..., :3], gw, gh), main[..., 3:4], params
        )
        if samples.shape[0] > samples_per_frame:
            keep = np.linspace(0, samples.shape[0] - 1, samples_per_frame).astype(np.intp)
            samples = samples[keep]
        pooled.append(samples)
    if not pooled:
        raise PipelineError("a shared palette needs at least one frame")
    return _generated_palette(np.concatenate(pooled, axis=0), params, images)


def _builtin_palette(lut_name):
    kind, data = resolve_builtin(lut_name)
    if kind == "palette":
        return np.asarray(data, dtype=np.float32)[:, :3]
    return palette_mod.per_channel_palette(data)


def _lut_palette(params, images=None):
    """Resolve LUT selections that have a finite palette representation."""
    images = images or {}
    lut_name = params.get("lut", "AMIGA")
    if lut_name == "CUSTOM_PALETTE":
        custom = images.get("custom_palette")
        if custom is None:
            raise PipelineError("Custom Palette image input required (LUT = Custom Palette)")
        return quantize_mod.palette_from_image(custom)
    if lut_name in ("CUSTOM_LUT", "CUBE_LUT"):
        return None
    return _builtin_palette(lut_name)


def _cube_lut(images, params):
    lut = images.get("cube_lut")
    if lut is None and params.get("cube_lut_path"):
        try:
            lut = lut_cube_mod.load_cube(params["cube_lut_path"])
        except (OSError, ValueError) as exc:
            raise PipelineError(f"Unable to load .cube LUT: {exc}") from exc
    if lut is None or not hasattr(lut, "sample"):
        raise PipelineError("a .cube LUT file is required (choose a Cube LUT path)")
    return lut


def _palette_for_threshold(pixelated, grid, alpha, params, images):
    qtype = params.get("quantize_type", "NONE")
    if qtype == "CUSTOM_PALETTE":
        return _generated_or_shared_palette(pixelated, grid, alpha, params, images)
    if qtype == "LUT":
        return _lut_palette(params, images)
    custom = images.get("custom_palette")
    if custom is not None:
        return quantize_mod.palette_from_image(custom)
    return None


def _build_dither_mask(pixelated, params, images, mask_type=None):
    mask_type = mask_type if mask_type is not None else params.get("dither_mask_type", "NONE")
    return dither_mod.build_mask(
        mask_type,
        pixelated,
        cutoff=params.get("dither_cutoff", 0.0),
        gamma=params.get("dither_mask_gamma", 1.0),
        weights={key: params.get(key, 1.0) for key in _MASK_WEIGHT_KEYS},
        custom=images.get("custom_mask"),
        lum_range=params.get("mask_lum_range", (0.0, 1.0)),
        sat_range=params.get("mask_sat_range", (0.0, 1.0)),
        gradient_angle=params.get("mask_gradient_angle", 0.0),
        invert=params.get("mask_invert", False),
        blur=params.get("mask_blur", 0),
    )


def _palette_indices_for_exact_output(image, palette, apply_space):
    """Return palette indices only when ``image`` is already palette-exact.

    A palette lock must not turn a post-process into an unintentional nearest
    lookup.  This helper therefore performs a lookup solely to recover the
    index buffer immediately after a finite-palette quantizer, and retains it
    only when that lookup reconstructs the current pixels exactly enough for
    float32 processing.  The returned uint8 buffer covers the extension's
    documented maximum of 256 palette entries.
    """
    palette = np.asarray(palette, dtype=np.float32)
    if palette.ndim != 2 or palette.shape[0] == 0 or palette.shape[0] > 256:
        return None
    snapped, indices = quantize_mod.apply_palette(
        image, palette, apply_space, return_indices=True
    )
    if not np.allclose(snapped, np.asarray(image, dtype=np.float32)[..., :3],
                       rtol=0.0, atol=2e-6):
        return None
    return indices.astype(np.uint8, copy=False)


def _apply_palette_indices(palette, indices):
    """Expand an exact full-resolution palette-index buffer to RGB float32."""
    palette = np.asarray(palette, dtype=np.float32)[:, :3]
    indices = np.asarray(indices)
    return palette[indices.astype(np.intp, copy=False)].astype(np.float32, copy=False)


def _snap_to_palette(image, palette, apply_mode, with_indices):
    """Nearest-palette snap returning ``(image, indices)``.

    ``indices`` is ``None`` unless requested, so callers keep one code path
    whether or not a palette-index buffer must be retained.
    """
    if with_indices:
        return quantize_mod.apply_palette(image, palette, apply_mode, return_indices=True)
    return quantize_mod.apply_palette(image, palette, apply_mode), None


def _grid_diffusion(image, gw, gh, snap_fn, params):
    """Error-diffuse onto ``snap_fn`` colors at pixel-grid resolution.

    Diffusion is sequential per pixel, so it runs on the small area-averaged
    grid and the result is nearest-upscaled back to the image size.
    """
    h, w = image.shape[:2]
    snapped = quantize_mod.diffuse_colors(
        downscale_area(image, gw, gh),
        snap_fn,
        params.get("diffusion", "NONE"),
        params.get("diffusion_strength", 1.0),
        params.get("diffusion_serpentine", True),
    )
    return upscale_nearest(snapped, w, h)


def _palette_quantize(image, gw, gh, palette, apply_mode, params, with_indices):
    """Quantize to a finite palette, by grid error diffusion when configured.

    Returns ``(image, indices)``; diffusion never exposes indices, so they are
    recovered later only when the diffused colors are palette-exact.
    """
    if params.get("diffusion", "NONE") != "NONE":
        snap_fn = quantize_mod.palette_snap_fn(palette, apply_mode)
        return _grid_diffusion(image, gw, gh, snap_fn, params), None
    return _snap_to_palette(image, palette, apply_mode, with_indices)


def _continuous_lut_fn(lut_name, params, images):
    """Return the color function for image/.cube LUTs, else ``None``.

    These LUT selections map colors continuously rather than through a
    finite palette.  Missing inputs raise :class:`PipelineError`.
    """
    if lut_name == "CUBE_LUT":
        cube = _cube_lut(images, params)
        interpolation = params.get("cube_lut_interpolation", "TRILINEAR")
        strength = params.get("cube_lut_strength", 1.0)
        return lambda colors: lut_cube_mod.sample(colors, cube, interpolation, strength)
    if lut_name == "CUSTOM_LUT":
        custom = images.get("custom_lut")
        if custom is None:
            raise PipelineError("Custom LUT image input required (LUT = Custom LUT)")
        return lambda colors: lut_mod.apply_lut(colors, custom[..., :3])
    return None


class _PipelineState:
    """Working state handed from stage to stage within one ``run_pipeline``.

    ``image`` is the current ``(h, w, 3)`` RGB and ``alpha`` its ``(h, w, 1)``
    alpha; ``palette``/``indices`` describe the finite palette and retained
    index buffer once a stage produces them.
    """

    def __init__(self, img, params, images, plan):
        img = np.asarray(img, dtype=np.float32)
        self.params = params
        self.images = images
        self.plan = plan
        self.active = set(stage_types(plan))
        self.h, self.w = img.shape[:2]
        self.image = img[..., :3].astype(np.float32)
        self.alpha = (
            img[..., 3:4].astype(np.float32) if img.shape[2] > 3
            else np.ones((self.h, self.w, 1), np.float32)
        )
        # Spec: Apply_Palette_Mode defaults to RGB for every nearest-palette lookup.
        self.apply_mode = params.get("apply_palette_mode", "RGB")
        self.lock_mode = str(params.get("v3_palette_lock", "OFF")).upper()
        # Output_Palette and Palette Tint both need the palette assignment made
        # by the finite-palette quantizer, before Display Finish can make
        # colors spatial or continuous.
        self.retain_indices = (
            bool(params.get("output_palette", False)) or self.lock_mode == "PALETTE_TINT"
        )
        self.grid = None
        self.gw = self.gh = None
        self.palette = None
        self.source_palette = None
        self.indices = None
        self.lut_image = None
        self.tint_applied = False

    def finite_palette(self):
        """The palette when it is small enough to lock or snap to, else ``None``."""
        if self.palette is not None and self.palette.shape[0] <= 256:
            return self.palette
        return None

    def result(self, main=None):
        return {
            "main": (np.concatenate([self.image, self.alpha], axis=-1) if main is None
                     else main).astype(np.float32),
            "palette_colors": self.palette,
            "source_palette_colors": self.source_palette,
            "palette": None,
            "palette_index": None,
            "lut": self.lut_image,
            "grid": (self.gw, self.gh),
            "plan": self.plan,
        }


# ---------------------------------------------------------------------------
# Stages (canonical order; each updates the shared state)
# ---------------------------------------------------------------------------

def _pixelate_stage(state, preview):
    params = state.params
    requested_gw, requested_gh = compute_grid(
        state.w, state.h,
        params.get("square_pixel_count", 256),
        params.get("use_separate_pixel_count", False),
        params.get("pixel_count_x", 256),
        params.get("pixel_count_y", 256),
    )
    state.image, state.grid = pixelate(
        state.image,
        requested_gw,
        requested_gh,
        params.get("downscale_mode", "NEAREST"),
        params.get("scale_algorithm", "NEAREST"),
        params.get("scale_tolerance", 0.05),
        params.get("content_aware_factor", 1.0),
        params.get("content_aware_max_dimension", 256),
        params.get("content_aware_seam_mode", "MINIMUM"),
    )
    state.gw, state.gh = state.grid.shape[1], state.grid.shape[0]
    if preview and params.get("filter_preview", "NONE") != "NONE":
        state.image = resample_preview(state.grid, state.w, state.h, params["filter_preview"])


def _posterize_stage(state):
    params = state.params
    posterized = posterize_mod.apply_posterize(
        np.concatenate([state.image, state.alpha], axis=-1),
        levels=params.get("posterize_levels", 8),
        range_mode=params.get("posterize_range_mode", "FULL"),
        range_low=params.get("posterize_range_low", 0.0),
        range_high=params.get("posterize_range_high", 1.0),
        percentile_low=params.get("posterize_percentile_low", 2.0),
        percentile_high=params.get("posterize_percentile_high", 98.0),
        gamma=params.get("posterize_gamma", 1.0),
        mix=params.get("posterize_mix", 1.0),
        channels=params.get("posterize_channel_mask", "RGB"),
        alpha_policy=params.get("posterize_alpha_policy", "PRESERVE"),
        range_map=state.images.get("range_map"),
    )
    state.image = posterized[..., :3]
    state.alpha = posterized[..., 3:4]


def _shading_stage(state):
    """Tone Bands: quantize lightness into flat tones (per part with an ID map)."""
    params, images = state.params, state.images
    light = None
    if params.get("shade_band_source", "LIGHTNESS") == "LIGHT_MAP":
        light = images.get("light_map")
        if light is None:
            raise PipelineError("Tone Bands from a light map need a Light Map image "
                                "(use Render Light Map)")
    id_map = None
    if params.get("shade_band_per_part", False):
        id_map = images.get("id_map")
        if id_map is None:
            raise PipelineError("Tone Bands per part need an ID map image (use Render ID Map)")
    state.image = shading_mod.tone_bands(
        state.image, state.alpha, params.get("shade_band_count", 3), light, id_map,
        params.get("shade_flatten", True),
    )


def _dither_stage(state):
    """Apply dithering; return a finished result when previewing the mask."""
    params, images = state.params, state.images
    dither_type = params.get("dither_type", "NONE")
    lock_to_grid = (
        params.get("lock_dither_to_grid", False)
        or params.get("v3_grid_coherence", "OFF") == "DITHER_CELL"
    )
    map_h, map_w = (state.gh, state.gw) if lock_to_grid else (state.h, state.w)
    dmap = dither_mod.dither_map(
        dither_type, map_h, map_w,
        seed=params.get("random_seed", 0),
        custom=images.get("custom_dither"),
        custom_res=params.get("custom_dither_resolution", (8, 8)),
    )
    if lock_to_grid:
        dmap = upscale_nearest(dmap, state.w, state.h)

    mask_type = params.get("dither_mask_type", "NONE")
    show_mask = params.get("preview_dither_mask", False)
    mask = None
    if mask_type != "NONE" or show_mask or images.get("strength_map") is not None:
        mask = _build_dither_mask(state.image, params, images)
    if images.get("strength_map") is not None:
        strength_map = resize_mask(images["strength_map"], state.image.shape)
        mask = strength_map if mask is None else mask * strength_map
    if show_mask:
        preview = np.concatenate([np.repeat(mask[..., None], 3, axis=-1), state.alpha], axis=-1)
        return state.result(main=preview)

    if str(params.get("dither_strategy", "OVERLAY")).upper() == "PALETTE_THRESHOLD":
        state.palette = _palette_for_threshold(
            state.image, state.grid, state.alpha, params, images
        )
        if state.palette is None or state.palette.shape[0] < 2:
            raise PipelineError(
                "Palette Threshold dithering requires a palette quantization mode "
                "or a custom palette image"
            )
        threshold = dmap[..., 0]
        if images.get("threshold_map") is not None:
            threshold_map = resize_mask(images["threshold_map"], threshold.shape)
            strength = float(np.clip(params.get("dither_strength", 1.0), 0.0, 1.0))
            threshold = threshold * (1.0 - strength) + threshold_map * strength
        state.image = dither_mod.palette_threshold_dither(
            state.image,
            state.palette,
            threshold,
            state.apply_mode,
            params.get("dither_strength", 1.0),
            params.get("palette_dither_contrast", 1.0),
            params.get("palette_dither_invert", False),
            mask,
        )
    else:
        state.image = dither_mod.apply_dither(
            state.image,
            dmap,
            blend_mode=params.get("dither_blend_mode", "SOFT_LIGHT"),
            strength=params.get("dither_strength", 0.25),
            saturation=params.get("dither_saturation", 0.5),
            use_gray=params.get("use_gray_dither", False),
            mask=mask,
        )
    return None


def _quantize_stage(state):
    params, images = state.params, state.images
    qtype = params.get("quantize_type", "NONE")
    diffuse = params.get("diffusion", "NONE") != "NONE"
    gw, gh = state.gw, state.gh

    if qtype == "CUSTOM_PALETTE":
        if state.palette is None:
            state.palette = _generated_or_shared_palette(
                state.image, state.grid, state.alpha, params, images
            )
        state.image, state.indices = _palette_quantize(
            state.image, gw, gh, state.palette, state.apply_mode, params, state.retain_indices
        )

    elif qtype == "PER_CHANNEL":
        if diffuse:
            levels = quantize_mod.per_channel_levels(
                params.get("quantize_colors_or_bits", "COLORS"),
                params.get("quantize_colors", 256),
                params.get("quantize_bits", 8),
            )
            state.image = _grid_diffusion(
                state.image, gw, gh, quantize_mod.per_channel_snap_fn(levels), params
            )
        else:
            state.image = quantize_mod.per_channel(
                state.image,
                params.get("quantize_colors_or_bits", "COLORS"),
                params.get("quantize_colors", 256),
                params.get("quantize_bits", 8),
                params.get("use_range_adaptive", False),
            )

    elif qtype == "LUT":
        lut_sel = params.get("lut", "AMIGA")
        color_fn = _continuous_lut_fn(lut_sel, params, images)
        if color_fn is not None:
            # Image and .cube LUTs map colors continuously; there is no finite
            # palette, so diffusion snaps through the LUT itself.
            state.image = (
                _grid_diffusion(state.image, gw, gh, color_fn, params) if diffuse
                else color_fn(state.image)
            )
        else:
            kind, bits = (
                resolve_builtin(lut_sel) if lut_sel != "CUSTOM_PALETTE" else ("palette", None)
            )
            if kind == "reduce":
                if diffuse:
                    state.image = _grid_diffusion(
                        state.image, gw, gh, quantize_mod.per_channel_snap_fn(1 << bits), params
                    )
                else:
                    state.image = quantize_mod.reduce_bits(state.image, bits)
            else:
                state.palette = _lut_palette(params, images)
                state.image, state.indices = _palette_quantize(
                    state.image, gw, gh, state.palette, state.apply_mode, params,
                    state.retain_indices,
                )
        if params.get("output_default_lut", False):
            state.lut_image = lut_mod.identity_lut()


def _sprite_stage(state):
    params, images = state.params, state.images
    if params.get("sprite_part_lines", False) and images.get("id_map") is None:
        raise PipelineError("Part Lines need an ID map image (use Render ID Map)")
    state.image, state.alpha = sprite_mod.apply_sprite_stage(
        state.image, state.alpha, state.gw, state.gh, params,
        state.finite_palette(), images.get("id_map"),
    )
    # Changed cells invalidate the quantizer's index buffer; it is recovered
    # afterwards only if the result is still palette-exact.
    state.indices = None


def _recover_indices(state):
    """Recover the index buffer before finishing, when the image is palette-exact.

    Diffusion and threshold dithering emit palette colors without exposing
    indices, and the sprite stage invalidates them.
    """
    if state.retain_indices and state.indices is None and state.palette is not None:
        state.indices = _palette_indices_for_exact_output(
            state.image, state.palette, state.apply_mode
        )


def _palette_tint(state):
    """Restyle the palette entries (Palette Tint) and repaint by retained index."""
    params = state.params
    source = state.finite_palette()
    tinted = finish_mod.adjust_color(
        source.reshape(1, -1, 3),
        params.get("finish_brightness", 0.0),
        params.get("finish_contrast", 1.0),
        params.get("finish_exposure", 0.0),
        params.get("finish_saturation", 1.0),
    ).reshape(-1, 3)
    amount = float(np.clip(params.get("v3_palette_lock_strength", 1.0), 0.0, 1.0))
    state.palette = (source * (1.0 - amount) + tinted * amount).astype(np.float32)
    if state.indices is not None:
        # Palette Tint owns the discrete assignment.  It must transform
        # entries by their retained index rather than nearest-matching the
        # finished color, which can collapse distinct source indices.
        state.image = _apply_palette_indices(state.palette, state.indices)
        state.tint_applied = True


def _finish_stage(state):
    params, images = state.params, state.images
    finish_mask = None
    finish_mask_type = params.get("finish_mask_type", "NONE")
    if finish_mask_type != "NONE":
        mask_params = dict(params)
        mask_params["mask_invert"] = params.get("finish_mask_invert", False)
        finish_mask = _build_dither_mask(state.image, mask_params, images, finish_mask_type)
    if images.get("strength_map") is not None:
        strength_map = resize_mask(images["strength_map"], state.image.shape)
        finish_mask = strength_map if finish_mask is None else finish_mask * strength_map
    finish_settings = params
    if state.tint_applied:
        # Palette Tint consumes the global color controls while preserving
        # the discrete palette.  Grain, scanlines, vignette, aberration, and
        # their masks remain true post-index display effects; their pixels
        # are intentionally not reclassified afterwards.
        finish_settings = dict(params)
        finish_settings.update({
            "finish_brightness": 0.0,
            "finish_contrast": 1.0,
            "finish_exposure": 0.0,
            "finish_saturation": 1.0,
        })
    rgba = finish_mod.apply_finish(
        np.concatenate([state.image, state.alpha], axis=-1),
        finish_settings, params.get("random_seed", 0), finish_mask,
    )
    state.image = rgba[..., :3]


def _grid_and_identity(state):
    """Final-cell grid coherence, then Index Guard (snap back to the palette)."""
    params = state.params
    if params.get("v3_grid_coherence", "OFF") == "FINAL_CELL":
        state.image = upscale_nearest(
            downscale_area(state.image, state.gw, state.gh), state.w, state.h
        )
    if state.lock_mode == "SNAP_BACK" and state.finite_palette() is not None:
        # Only Output_Palette consumes the indices after this point.
        state.image, state.indices = _snap_to_palette(
            state.image, state.palette, state.apply_mode,
            bool(params.get("output_palette", False)),
        )


def _derived_outputs(state, result):
    """Swatch, index image, and generated LUT from the finalized palette.

    A retained index buffer remains the authoritative Output_Palette
    representation when a spatial finish has since changed display pixels.
    """
    params = state.params
    if params.get("output_palette", False) and state.palette is not None:
        result["palette"] = quantize_mod.palette_swatch(state.palette)
        result["palette_index"] = quantize_mod.palette_index_image(
            state.image, state.palette, state.apply_mode, indices=state.indices,
        )
    if (
        "quantize" in state.active and params.get("quantize_type", "NONE") == "CUSTOM_PALETTE"
        and params.get("output_lut", False) and state.palette is not None
    ):
        result["lut"] = lut_mod.encode_lut_from_palette(state.palette)


def run_pipeline(img, params, images=None, preview=False, progress=None, cancel=None):
    """Run PixelatorPlus on an ``(h,w,4)`` float32 image in 0..1.

    Stages run in the canonical order (pixelate -> posterize -> tone bands ->
    dither -> quantize -> sprite -> finish); the plan's stage stack can
    disable each.
    ``progress`` receives ``(fraction, stage_name)`` at safe stage boundaries;
    ``cancel`` is a caller-owned zero-argument predicate.  Both are optional
    and are intentionally synchronous so Blender never has to share its data
    API with a Python worker thread.  Palette Tint retains an exact palette
    index buffer before Display Finish when one exists: color controls tint
    palette entries, while spatial finish effects remain post-index display
    effects and are never nearest-color reclassified.
    """
    plan = normalize_plan(params)
    params = plan_to_params(plan)
    state = _PipelineState(img, params, dict(images or {}), plan)
    active = state.active
    _checkpoint(progress, cancel, 0.0, "prepare")

    _pixelate_stage(state, preview)
    _checkpoint(progress, cancel, 0.2, "pixelate")
    if "posterize" in active:
        _posterize_stage(state)
    if "shading" in active:
        _shading_stage(state)
    _checkpoint(progress, cancel, 0.35, "posterize")
    if "dither" in active and params.get("dither_type", "NONE") != "NONE":
        mask_preview = _dither_stage(state)
        if mask_preview is not None:
            return mask_preview
    _checkpoint(progress, cancel, 0.55, "dither")
    if "quantize" in active:
        _quantize_stage(state)
    _checkpoint(progress, cancel, 0.75, "quantize")
    if "sprite" in active:
        _sprite_stage(state)
    _recover_indices(state)
    # The palette as quantized, before Palette Tint restyles it.  Freezing a
    # palette for animation reuses this, so tinting is never applied twice.
    state.source_palette = state.palette
    _checkpoint(progress, cancel, 0.8, "sprite")

    if state.lock_mode == "PALETTE_TINT" and state.finite_palette() is not None:
        _palette_tint(state)
    if "display_finish" in active and params.get("finish_enabled", False):
        _finish_stage(state)
    _grid_and_identity(state)
    result = state.result()
    _derived_outputs(state, result)
    _checkpoint(progress, cancel, 0.95, "display_finish")
    _checkpoint(progress, cancel, 1.0, "complete")
    return result
