"""PixelatorPlus v3 canonical stage executor.

The executor remains compatible with the v2 flat settings dictionary while
supporting palette-aware dithering, expanded diffusion, `.cube` LUTs,
pixel-art scaling, sprite cleanup and outlines, and a deterministic
display-finish stack.  V3 makes the dependency order explicit (pixelate ->
posterize -> dither -> quantize -> sprite -> finish), allows each stage to be
disabled through the canonical stage stack, and adds PixelatorPlus-native
palette-lock and grid-coherence policies without copying another compositor's
node runtime.
"""

import numpy as np

from . import dither as dither_mod
from . import finish as finish_mod
from . import lut as lut_mod
from . import lut_cube as lut_cube_mod
from . import palette as palette_mod
from . import posterize as posterize_mod
from . import quantize as quantize_mod
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
    if method in ("FREQUENCY", "EXACT"):
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
        sprite_outline="NONE", preview_dither_mask=False, output_palette=False,
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


def run_pipeline(img, params, images=None, preview=False, progress=None, cancel=None):
    """Run PixelatorPlus on an ``(h,w,4)`` float32 image in 0..1.

    ``progress`` receives ``(fraction, stage_name)`` at safe stage boundaries;
    ``cancel`` is a caller-owned zero-argument predicate.  Both are optional
    and are intentionally synchronous so Blender never has to share its data
    API with a Python worker thread.  Palette Tint retains an exact palette
    index buffer before Display Finish when one exists: color controls tint
    palette entries, while spatial finish effects remain post-index display
    effects and are never nearest-color reclassified.
    """
    images = dict(images or {})
    plan = normalize_plan(params)
    params = plan_to_params(plan)
    active_stages = set(stage_types(plan))
    _checkpoint(progress, cancel, 0.0, "prepare")
    img = np.asarray(img, dtype=np.float32)
    h, w = img.shape[:2]
    rgb = img[..., :3].astype(np.float32)
    alpha = img[..., 3:4].astype(np.float32) if img.shape[2] > 3 else np.ones((h, w, 1), np.float32)
    # Spec: Apply_Palette_Mode defaults to RGB for every nearest-palette lookup.
    apply_mode = params.get("apply_palette_mode", "RGB")

    # -- 1. Pixelate -------------------------------------------------------
    requested_gw, requested_gh = compute_grid(
        w, h,
        params.get("square_pixel_count", 256),
        params.get("use_separate_pixel_count", False),
        params.get("pixel_count_x", 256),
        params.get("pixel_count_y", 256),
    )
    pixelated, grid = pixelate(
        rgb,
        requested_gw,
        requested_gh,
        params.get("downscale_mode", "NEAREST"),
        params.get("scale_algorithm", "NEAREST"),
        params.get("scale_tolerance", 0.05),
        params.get("content_aware_factor", 1.0),
        params.get("content_aware_max_dimension", 256),
        params.get("content_aware_seam_mode", "MINIMUM"),
    )
    gw, gh = grid.shape[1], grid.shape[0]
    if preview and params.get("filter_preview", "NONE") != "NONE":
        pixelated = resample_preview(grid, w, h, params["filter_preview"])
    _checkpoint(progress, cancel, 0.2, "pixelate")

    # -- 2. Posterize / Levels ---------------------------------------------
    if "posterize" in active_stages:
        posterized = posterize_mod.apply_posterize(
            np.concatenate([pixelated, alpha], axis=-1),
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
            range_map=images.get("range_map"),
        )
        pixelated = posterized[..., :3]
        alpha = posterized[..., 3:4]
    _checkpoint(progress, cancel, 0.35, "posterize")

    # -- 3. Dither ----------------------------------------------------------
    palette_colors = None
    dither_type = params.get("dither_type", "NONE")
    dither_strategy = str(params.get("dither_strategy", "OVERLAY")).upper()
    if "dither" in active_stages and dither_type != "NONE":
        dither_h, dither_w = h, w
        lock_dither_to_grid = (
            params.get("lock_dither_to_grid", False)
            or params.get("v3_grid_coherence", "OFF") == "DITHER_CELL"
        )
        if lock_dither_to_grid:
            dither_h, dither_w = gh, gw
        dmap = dither_mod.dither_map(
            dither_type, dither_h, dither_w,
            seed=params.get("random_seed", 0),
            custom=images.get("custom_dither"),
            custom_res=params.get("custom_dither_resolution", (8, 8)),
        )
        if lock_dither_to_grid:
            dmap = upscale_nearest(dmap, w, h)

        mask_type = params.get("dither_mask_type", "NONE")
        show_mask = params.get("preview_dither_mask", False)
        mask = None
        if mask_type != "NONE" or show_mask or images.get("strength_map") is not None:
            mask = _build_dither_mask(pixelated, params, images)
        if images.get("strength_map") is not None:
            strength_map = resize_mask(images["strength_map"], pixelated.shape)
            mask = strength_map if mask is None else mask * strength_map
        if show_mask:
            main = np.concatenate([np.repeat(mask[..., None], 3, axis=-1), alpha], axis=-1)
            return {
                "main": main.astype(np.float32), "palette_colors": None,
                "palette": None, "palette_index": None, "lut": None,
                "grid": (gw, gh), "plan": plan, "source_palette_colors": None,
            }
        if dither_strategy == "PALETTE_THRESHOLD":
            palette_colors = _palette_for_threshold(pixelated, grid, alpha, params, images)
            if palette_colors is None or palette_colors.shape[0] < 2:
                raise PipelineError(
                    "Palette Threshold dithering requires a palette quantization mode "
                    "or a custom palette image"
                )
            threshold = dmap[..., 0]
            if images.get("threshold_map") is not None:
                threshold_map = resize_mask(images["threshold_map"], threshold.shape)
                strength = float(np.clip(params.get("dither_strength", 1.0), 0.0, 1.0))
                threshold = threshold * (1.0 - strength) + threshold_map * strength
            pixelated = dither_mod.palette_threshold_dither(
                pixelated,
                palette_colors,
                threshold,
                apply_mode,
                params.get("dither_strength", 1.0),
                params.get("palette_dither_contrast", 1.0),
                params.get("palette_dither_invert", False),
                mask,
            )
        else:
            pixelated = dither_mod.apply_dither(
                pixelated,
                dmap,
                blend_mode=params.get("dither_blend_mode", "SOFT_LIGHT"),
                strength=params.get("dither_strength", 0.25),
                saturation=params.get("dither_saturation", 0.5),
                use_gray=params.get("use_gray_dither", False),
                mask=mask,
            )
    _checkpoint(progress, cancel, 0.55, "dither")

    # -- 4. Quantize --------------------------------------------------------
    out = pixelated
    palette_img = None
    palette_index_img = None
    lut_img = None
    qtype = params.get("quantize_type", "NONE")
    diffuse = params.get("diffusion", "NONE") != "NONE"
    lock_mode = str(params.get("v3_palette_lock", "OFF")).upper()
    # Output_Palette and Palette Tint both need the palette assignment made by
    # the finite-palette quantizer, before Display Finish can make colors
    # spatial or continuous.
    retain_palette_indices = (
        bool(params.get("output_palette", False)) or lock_mode == "PALETTE_TINT"
    )
    palette_indices = None

    if "quantize" in active_stages and qtype == "CUSTOM_PALETTE":
        if palette_colors is None:
            palette_colors = _generated_or_shared_palette(out, grid, alpha, params, images)
        out, palette_indices = _palette_quantize(
            out, gw, gh, palette_colors, apply_mode, params, retain_palette_indices
        )

    elif "quantize" in active_stages and qtype == "PER_CHANNEL":
        if diffuse:
            levels = quantize_mod.per_channel_levels(
                params.get("quantize_colors_or_bits", "COLORS"),
                params.get("quantize_colors", 256),
                params.get("quantize_bits", 8),
            )
            out = _grid_diffusion(out, gw, gh, quantize_mod.per_channel_snap_fn(levels), params)
        else:
            out = quantize_mod.per_channel(
                out,
                params.get("quantize_colors_or_bits", "COLORS"),
                params.get("quantize_colors", 256),
                params.get("quantize_bits", 8),
                params.get("use_range_adaptive", False),
            )

    elif "quantize" in active_stages and qtype == "LUT":
        lut_sel = params.get("lut", "AMIGA")
        color_fn = _continuous_lut_fn(lut_sel, params, images)
        if color_fn is not None:
            # Image and .cube LUTs map colors continuously; there is no finite
            # palette, so diffusion snaps through the LUT itself.
            out = _grid_diffusion(out, gw, gh, color_fn, params) if diffuse else color_fn(out)
        else:
            kind, bits = (
                resolve_builtin(lut_sel) if lut_sel != "CUSTOM_PALETTE" else ("palette", None)
            )
            if kind == "reduce":
                if diffuse:
                    out = _grid_diffusion(
                        out, gw, gh, quantize_mod.per_channel_snap_fn(1 << bits), params
                    )
                else:
                    out = quantize_mod.reduce_bits(out, bits)
            else:
                palette_colors = _lut_palette(params, images)
                out, palette_indices = _palette_quantize(
                    out, gw, gh, palette_colors, apply_mode, params, retain_palette_indices
                )
        if params.get("output_default_lut", False):
            lut_img = lut_mod.identity_lut()

    _checkpoint(progress, cancel, 0.75, "quantize")

    # -- 5. Sprite cleanup / outline ---------------------------------------
    if "sprite" in active_stages:
        sprite_palette = (
            palette_colors
            if palette_colors is not None and palette_colors.shape[0] <= 256 else None
        )
        out, alpha = sprite_mod.apply_sprite_stage(out, alpha, gw, gh, params, sprite_palette)
        # Changed cells invalidate the quantizer's index buffer; it is
        # recovered below only if the result is still palette-exact.
        palette_indices = None

    # Diffusion and threshold dithering already emit palette colors, but their
    # quantizers do not expose indices.  Recover an index buffer now, before
    # any finish effect, only if it faithfully reproduces those colors.
    if retain_palette_indices and palette_indices is None and palette_colors is not None:
        palette_indices = _palette_indices_for_exact_output(out, palette_colors, apply_mode)
    # The palette as quantized, before Palette Tint restyles it.  Freezing a
    # palette for animation reuses this, so tinting is never applied twice.
    source_palette_colors = palette_colors
    _checkpoint(progress, cancel, 0.8, "sprite")

    # -- 6. Display finish --------------------------------------------------
    lock_palette = (
        palette_colors if palette_colors is not None and palette_colors.shape[0] <= 256 else None
    )
    palette_tint_applied = False
    if lock_mode == "PALETTE_TINT" and lock_palette is not None:
        tinted = finish_mod.adjust_color(
            lock_palette.reshape(1, -1, 3),
            params.get("finish_brightness", 0.0),
            params.get("finish_contrast", 1.0),
            params.get("finish_exposure", 0.0),
            params.get("finish_saturation", 1.0),
        ).reshape(-1, 3)
        amount = float(np.clip(params.get("v3_palette_lock_strength", 1.0), 0.0, 1.0))
        palette_colors = (
            lock_palette * (1.0 - amount) + tinted * amount
        ).astype(np.float32)
        if palette_indices is not None:
            # Palette Tint owns the discrete assignment.  It must transform
            # entries by their retained index rather than nearest-matching the
            # finished color, which can collapse distinct source indices.
            out = _apply_palette_indices(palette_colors, palette_indices)
            palette_tint_applied = True

    if "display_finish" in active_stages and params.get("finish_enabled", False):
        finish_mask = None
        finish_mask_type = params.get("finish_mask_type", "NONE")
        if finish_mask_type != "NONE":
            mask_params = dict(params)
            mask_params["mask_invert"] = params.get("finish_mask_invert", False)
            finish_mask = _build_dither_mask(out, mask_params, images, finish_mask_type)
        if images.get("strength_map") is not None:
            strength_map = resize_mask(images["strength_map"], out.shape)
            finish_mask = strength_map if finish_mask is None else finish_mask * strength_map
        finish_settings = params
        if palette_tint_applied:
            # Palette Tint consumes the global color controls while preserving
            # the discrete palette.  Grain, scanlines, vignette, aberration,
            # and their masks remain true post-index display effects; their
            # pixels are intentionally not reclassified afterwards.
            finish_settings = dict(params)
            finish_settings.update({
                "finish_brightness": 0.0,
                "finish_contrast": 1.0,
                "finish_exposure": 0.0,
                "finish_saturation": 1.0,
            })
        rgba = np.concatenate([out, alpha], axis=-1)
        rgba = finish_mod.apply_finish(
            rgba, finish_settings, params.get("random_seed", 0), finish_mask
        )
        out = rgba[..., :3]

    # -- 7. V3 pixel-grid coherence and palette identity -------------------
    if params.get("v3_grid_coherence", "OFF") == "FINAL_CELL":
        out = upscale_nearest(downscale_area(out, gw, gh), w, h)
    if lock_mode == "SNAP_BACK" and lock_palette is not None:
        # Only Output_Palette consumes the indices after this point.
        out, palette_indices = _snap_to_palette(
            out, palette_colors, apply_mode, bool(params.get("output_palette", False))
        )

    # Derived outputs describe the finalized palette state, not the palette
    # that existed before Palette Tint.  A retained index buffer remains the
    # authoritative Output_Palette representation when a spatial finish has
    # subsequently changed display pixels.
    if params.get("output_palette", False) and palette_colors is not None:
        palette_img = quantize_mod.palette_swatch(palette_colors)
        palette_index_img = quantize_mod.palette_index_image(
            out, palette_colors, apply_mode, indices=palette_indices,
        )
    if (
        "quantize" in active_stages and qtype == "CUSTOM_PALETTE"
        and params.get("output_lut", False) and palette_colors is not None
    ):
        lut_img = lut_mod.encode_lut_from_palette(palette_colors)
    _checkpoint(progress, cancel, 0.95, "display_finish")

    main = np.concatenate([out, alpha], axis=-1).astype(np.float32)
    _checkpoint(progress, cancel, 1.0, "complete")
    return {
        "main": main,
        "palette_colors": palette_colors,
        "source_palette_colors": source_palette_colors,
        "palette": palette_img,
        "palette_index": palette_index_img,
        "lut": lut_img,
        "grid": (gw, gh),
        "plan": plan,
    }
