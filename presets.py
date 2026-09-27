"""Editable style recipes built from PixelatorPlus' existing controls.

Recipes are intentionally data-only and Blender-independent.  Loading one
establishes a complete, predictable effect baseline while preserving user
state such as input images, preview preferences, and compositor automation.
"""


# Every effect property is reset before recipe-specific values are overlaid.
# This prevents a hidden setting from the previously loaded recipe leaking into
# the next look.
EFFECT_BASELINE = {
    "v3_palette_lock": "OFF",
    "v3_palette_lock_strength": 1.0,
    "v3_grid_coherence": "OFF",
    "use_separate_pixel_count": False,
    "square_pixel_count": 256,
    "pixel_count_x": 256,
    "pixel_count_y": 256,
    "downscale_mode": "NEAREST",
    "scale_algorithm": "NEAREST",
    "scale_tolerance": 0.05,
    "content_aware_factor": 1.0,
    "content_aware_max_dimension": 128,
    "content_aware_seam_mode": "MINIMUM",
    "filter_preview": "NONE",
    "dither_type": "NONE",
    "dither_strategy": "OVERLAY",
    "custom_dither_resolution": (8, 8),
    "dither_blend_mode": "SOFT_LIGHT",
    "use_gray_dither": False,
    "dither_strength": 0.25,
    "dither_saturation": 0.5,
    "palette_dither_contrast": 1.0,
    "palette_dither_invert": False,
    "lock_dither_to_grid": False,
    "dither_mask_type": "NONE",
    "dither_cutoff": 0.0,
    "dither_mask_gamma": 1.0,
    "dither_mask_lum_low": 0.0,
    "dither_mask_lum_high": 1.0,
    "dither_mask_sat_low": 0.0,
    "dither_mask_sat_high": 1.0,
    "dither_mask_gradient_angle": 0.0,
    "dither_mask_invert": False,
    "dither_mask_blur": 0,
    "preview_dither_mask": False,
    "show_mask_controls": False,
    "huge": 1.0,
    "big": 1.0,
    "large": 0.8,
    "medium": 0.6,
    "fine": 0.4,
    "sharp": 0.2,
    "pixel_perfect": 0.2,
    "quantize_type": "NONE",
    "posterize_enabled": False,
    "posterize_levels": 8,
    "posterize_range_mode": "FULL",
    "posterize_range_low": 0.0,
    "posterize_range_high": 1.0,
    "posterize_percentile_low": 2.0,
    "posterize_percentile_high": 98.0,
    "posterize_gamma": 1.0,
    "posterize_mix": 1.0,
    "posterize_channel_mask": "RGB",
    "posterize_alpha_policy": "PRESERVE",
    "diffusion": "NONE",
    "diffusion_strength": 1.0,
    "diffusion_serpentine": True,
    "initialize_mode": "1",
    "color_mode": "RGB",
    "apply_palette_mode": "RGB",
    "quantize_quality": 2,
    "quantize_seed": 1.0,
    "use_explicit_quantize_seed": False,
    "chroma_importance": 35.0,
    "use_chroma_importance": False,
    "use_pixelated_for_quantize": False,
    "palette_extract_method": "KMEANS",
    "palette_sort_mode": "NONE",
    "palette_shift": 0,
    "palette_trim": False,
    "palette_replace_image": None,
    "palette_replace_threshold": 0.1,
    "k_num_colors": 32,
    "gamma": 1.0,
    "force_colors": "NONE",
    "output_palette": False,
    "output_lut": False,
    "use_range_adaptive": False,
    "quantize_colors_or_bits": "COLORS",
    "quantize_colors": 256,
    "quantize_bits": 8,
    "output_default_lut": False,
    "lut": "AMIGA",
    "cube_lut_path": "",
    "cube_lut_interpolation": "TRILINEAR",
    "cube_lut_strength": 1.0,
    "finish_enabled": False,
    "finish_brightness": 0.0,
    "finish_contrast": 1.0,
    "finish_exposure": 0.0,
    "finish_saturation": 1.0,
    "finish_grain": 0.0,
    "finish_grain_brightness": 0.0,
    "finish_grain_saturation": 1.0,
    "finish_scanline_strength": 0.0,
    "finish_scanline_size": 2,
    "finish_scanline_axis": "Y",
    "finish_scanline_invert": False,
    "finish_vignette_strength": 0.0,
    "finish_vignette_roundness": 1.0,
    "finish_chromatic_aberration": 0.0,
    "finish_mask_type": "NONE",
    "finish_mask_mix": 1.0,
    "finish_mask_invert": False,
    "finish_channel_mask": "RGB",
}


# These are artistic starting points, not hardware emulators.  Historical
# display dimensions and public built-in palettes establish each visual idiom;
# the full controls remain editable after loading.
PRESETS = (
    {
        "id": "MODERN_INDIE_24",
        "name": "Modern Indie 24-Color",
        "description": "Crisp perceptual palette, subtle blue noise, and a flexible 24-color look",
        "values": {
            "square_pixel_count": 128,
            "dither_type": "BLUE_NOISE",
            "dither_blend_mode": "SOFT_LIGHT_LINEAR",
            "dither_strength": 0.18,
            "dither_saturation": 0.35,
            "lock_dither_to_grid": True,
            "quantize_type": "CUSTOM_PALETTE",
            "initialize_mode": "2",
            "color_mode": "OKLAB",
            "apply_palette_mode": "OKLAB",
            "quantize_quality": 3,
            "k_num_colors": 24,
            "force_colors": "DARKEST_BRIGHTEST",
            "use_pixelated_for_quantize": True,
        },
    },
    {
        "id": "ONE_BIT_INK",
        "name": "1-Bit Ink",
        "description": "Bold black-and-white ordered dithering for comics, stamps, and print",
        "values": {
            "square_pixel_count": 96,
            "dither_type": "BAYER",
            "dither_blend_mode": "OVERLAY_LINEAR",
            "use_gray_dither": True,
            "dither_strength": 0.72,
            "dither_saturation": 0.0,
            "lock_dither_to_grid": True,
            "quantize_type": "CUSTOM_PALETTE",
            "initialize_mode": "3",
            "color_mode": "CIELAB",
            "apply_palette_mode": "CIELAB",
            "quantize_quality": 3,
            "k_num_colors": 2,
            "force_colors": "BLACK_WHITE",
            "use_pixelated_for_quantize": True,
        },
    },
    {
        "id": "HANDHELD_DMG",
        "name": "Handheld 4-Tone",
        "description": "Classic 160x144 green four-shade handheld display",
        "values": {
            "use_separate_pixel_count": True,
            "pixel_count_x": 160,
            "pixel_count_y": 144,
            "dither_type": "BAYER",
            "dither_strength": 0.34,
            "dither_saturation": 0.0,
            "lock_dither_to_grid": True,
            "quantize_type": "LUT",
            "apply_palette_mode": "CIELAB",
            "lut": "GAMEBOY",
        },
    },
    {
        "id": "POCKET_COLOR",
        "name": "Pocket Color",
        "description": "Color-handheld resolution with gentle blue-noise texture",
        "values": {
            "use_separate_pixel_count": True,
            "pixel_count_x": 160,
            "pixel_count_y": 144,
            "dither_type": "BLUE_NOISE",
            "dither_blend_mode": "SOFT_LIGHT_LINEAR",
            "dither_strength": 0.16,
            "dither_saturation": 0.25,
            "lock_dither_to_grid": True,
            "quantize_type": "LUT",
            "apply_palette_mode": "OKLAB",
            "lut": "GAMEBOY_COLOR",
        },
    },
    {
        "id": "EIGHT_BIT_CONSOLE",
        "name": "8-Bit Console",
        "description": "256x240 ordered-dither treatment using the built-in console palette",
        "values": {
            "use_separate_pixel_count": True,
            "pixel_count_x": 256,
            "pixel_count_y": 240,
            "dither_type": "BAYER",
            "dither_strength": 0.24,
            "dither_saturation": 0.3,
            "lock_dither_to_grid": True,
            "quantize_type": "LUT",
            "apply_palette_mode": "CIELAB",
            "lut": "NES",
        },
    },
    {
        "id": "HOME_COMPUTER",
        "name": "Home Computer 16",
        "description": "Chunky 320x200 clustered pattern with a compact 16-color palette",
        "values": {
            "use_separate_pixel_count": True,
            "pixel_count_x": 320,
            "pixel_count_y": 200,
            "dither_type": "PATTERN",
            "dither_strength": 0.32,
            "dither_saturation": 0.45,
            "lock_dither_to_grid": True,
            "quantize_type": "LUT",
            "apply_palette_mode": "CIELAB",
            "lut": "C64",
        },
    },
    {
        "id": "DEMOSCENE_32",
        "name": "Demoscene 32",
        "description": "Low-resolution clustered color texture with a vivid 32-color palette",
        "values": {
            "use_separate_pixel_count": True,
            "pixel_count_x": 320,
            "pixel_count_y": 256,
            "dither_type": "PATTERN",
            "dither_blend_mode": "OVERLAY",
            "dither_strength": 0.3,
            "dither_saturation": 0.7,
            "lock_dither_to_grid": True,
            "quantize_type": "LUT",
            "apply_palette_mode": "CIELAB",
            "lut": "AMIGA",
        },
    },
    {
        "id": "ARCADE_64",
        "name": "Arcade 64-Color",
        "description": "Punchy arcade color with a 6-bit RGB palette and restrained blue noise",
        "values": {
            "square_pixel_count": 224,
            "dither_type": "BLUE_NOISE",
            "dither_blend_mode": "OVERLAY_LINEAR",
            "dither_strength": 0.14,
            "dither_saturation": 0.45,
            "lock_dither_to_grid": True,
            "quantize_type": "LUT",
            "apply_palette_mode": "RGB",
            "lut": "MASTER_SYSTEM",
        },
    },
    {
        "id": "APPLE_HIRES",
        "name": "Hi-Res Artifact Color",
        "description": "Sparse six-color 280x192 computer-art look with patterned transitions",
        "values": {
            "use_separate_pixel_count": True,
            "pixel_count_x": 280,
            "pixel_count_y": 192,
            "dither_type": "PATTERN",
            "dither_strength": 0.42,
            "dither_saturation": 0.7,
            "lock_dither_to_grid": True,
            "quantize_type": "LUT",
            "apply_palette_mode": "CIELAB",
            "lut": "APPLE2_HIRES",
        },
    },
    {
        "id": "PAINTERLY_MOSAIC",
        "name": "Painterly Mosaic",
        "description": "Soft block sampling and a hand-picked-looking perceptual 12-color palette",
        "values": {
            "square_pixel_count": 48,
            "downscale_mode": "NEAREST_SOFTER",
            "dither_type": "BLUE_NOISE",
            "dither_blend_mode": "SOFT_LIGHT_LINEAR",
            "dither_strength": 0.08,
            "dither_saturation": 0.2,
            "quantize_type": "CUSTOM_PALETTE",
            "initialize_mode": "3",
            "color_mode": "OKLAB",
            "apply_palette_mode": "OKLAB",
            "quantize_quality": 4,
            "k_num_colors": 12,
            "gamma": 1.1,
            "force_colors": "DARKEST_BRIGHTEST",
            "use_pixelated_for_quantize": True,
        },
    },
    {
        "id": "Y2K_WEB",
        "name": "Y2K Web-Safe",
        "description": "Noisy late-1990s web graphics constrained to the web-safe palette",
        "values": {
            "square_pixel_count": 128,
            "dither_type": "WHITE_NOISE",
            "dither_blend_mode": "OVERLAY",
            "dither_strength": 0.2,
            "dither_saturation": 0.6,
            "quantize_type": "LUT",
            "apply_palette_mode": "RGB",
            "lut": "WEB",
        },
    },
    {
        "id": "GLITCHPUNK_RGB",
        "name": "Glitchpunk RGB",
        "description": "Aggressive noise and adaptive 3-bit channels for crunchy neon color",
        "values": {
            "square_pixel_count": 80,
            "dither_type": "WHITE_NOISE",
            "dither_blend_mode": "OVERLAY_LINEAR",
            "dither_strength": 0.58,
            "dither_saturation": 1.0,
            "dither_mask_type": "EDGES",
            "dither_cutoff": 0.18,
            "dither_mask_gamma": 0.8,
            "quantize_type": "PER_CHANNEL",
            "use_range_adaptive": True,
            "quantize_colors_or_bits": "BITS",
            "quantize_bits": 3,
        },
    },
    {
        "id": "MAC_CLASSIC_1BIT",
        "name": "Macintosh 1-Bit",
        "description": "Atkinson error diffusion onto black and white — the 1984 Macintosh look",
        "values": {
            "square_pixel_count": 256,
            "quantize_type": "LUT",
            "lut": "GRAYSCALE_2",
            "diffusion": "ATKINSON",
        },
    },
    {
        "id": "NEWSPRINT_HALFTONE",
        "name": "Newsprint Halftone",
        "description": "45-degree dot screen under a four-tone gray ramp, newspaper-print style",
        "values": {
            "square_pixel_count": 192,
            "dither_type": "HALFTONE_DOT",
            "dither_blend_mode": "SOFT_LIGHT",
            "use_gray_dither": True,
            "dither_strength": 0.5,
            "dither_saturation": 0.0,
            "lock_dither_to_grid": True,
            "quantize_type": "LUT",
            "lut": "GRAYSCALE_4",
        },
    },
    {
        "id": "MONKEY_BUSINESS",
        "name": "Monkey Business",
        "description": "The Suzanne mascot dither over a classic 32-color palette — pure Blender mischief",
        "values": {
            "square_pixel_count": 128,
            "dither_type": "SUZANNE",
            "dither_blend_mode": "SOFT_LIGHT",
            "dither_strength": 0.6,
            "lock_dither_to_grid": True,
            "quantize_type": "LUT",
            "apply_palette_mode": "CIELAB",
            "lut": "DB32",
        },
    },
)


_PRESETS_BY_ID = {preset["id"]: preset for preset in PRESETS}
PRESET_ITEMS = tuple(
    (preset["id"], preset["name"], preset["description"])
    for preset in PRESETS
)
SURPRISE_IDS = tuple(preset["id"] for preset in PRESETS)


def preset_info(identifier):
    """Return a recipe definition, raising ``KeyError`` for an unknown ID."""
    return _PRESETS_BY_ID[identifier]


def preset_values(identifier):
    """Return a fresh complete effect-settings dict for ``identifier``."""
    values = dict(EFFECT_BASELINE)
    values.update(preset_info(identifier)["values"])
    return values


def surprise_values(rng):
    """Return ``(recipe_id, values)`` with bounded, recipe-aware variation.

    ``rng`` follows the small API shared by ``random.Random`` and
    ``random.SystemRandom``.  Accepting it as an argument keeps tests fully
    deterministic while interactive use remains unpredictable.
    """
    identifier = rng.choice(SURPRISE_IDS)
    values = preset_values(identifier)
    scale = rng.choice((0.75, 1.0, 1.25))

    if values["use_separate_pixel_count"]:
        values["pixel_count_x"] = max(16, min(2048, round(values["pixel_count_x"] * scale)))
        values["pixel_count_y"] = max(16, min(2048, round(values["pixel_count_y"] * scale)))
    else:
        count = round(values["square_pixel_count"] * scale)
        values["square_pixel_count"] = max(16, min(2048, count))

    if values["dither_type"] != "NONE":
        strength = values["dither_strength"] + rng.uniform(-0.1, 0.1)
        values["dither_strength"] = round(max(0.02, min(1.0, strength)), 3)

    if values["quantize_type"] == "CUSTOM_PALETTE" and identifier != "ONE_BIT_INK":
        colors = values["k_num_colors"] + rng.choice((-4, 0, 4))
        values["k_num_colors"] = max(2, min(256, colors))
    elif values["quantize_type"] == "PER_CHANNEL":
        bits = values["quantize_bits"] + rng.choice((-1, 0, 1))
        values["quantize_bits"] = max(1, min(8, bits))

    values["random_seed"] = rng.randint(0, 9999)
    return identifier, values
