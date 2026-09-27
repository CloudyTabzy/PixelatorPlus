"""Validated stage plans for the PixelatorPlus v3 canonical executor.

The public v2 entry points remain flat dictionaries.  This module adds the
internal seam needed for larger feature work without changing saved settings
or operator IDs: legacy dictionaries are normalized into a small stage plan,
then flattened back for the existing executor.  V3 adds explicit stage enable
flags and policies while keeping dependency order deterministic.  The plan is
deliberately plain Python data so the core remains usable without Blender.
"""

import copy
import hashlib
import json
import math


PLAN_SCHEMA_VERSION = 4
PLAN_FORMAT = "PixelatorPlus Plan"
_KNOWN_STAGES = {
    "pre_adjust",
    "pixelate",
    "posterize",
    "palette",
    "dither",
    "diffusion",
    "quantize",
    "display_finish",
}
_CANONICAL_STAGE_ORDER = (
    "pre_adjust", "pixelate", "posterize", "palette", "dither",
    "diffusion", "quantize", "display_finish",
)
_V3_PALETTE_LOCKS = {"OFF", "SNAP_BACK", "PALETTE_TINT"}
_V3_GRID_COHERENCE = {"OFF", "DITHER_CELL", "FINAL_CELL"}


def _stage(stage_type, params, keys):
    settings = {key: params[key] for key in keys if key in params}
    return {"type": stage_type, "schema_version": 1, "settings": settings}


def legacy_to_plan(params):
    """Convert the current flat v2 settings dictionary to a stage plan."""
    params = dict(params or {})
    stages = [
        _stage(
            "pixelate",
            params,
            (
                "square_pixel_count", "use_separate_pixel_count", "pixel_count_x",
                "pixel_count_y", "downscale_mode", "filter_preview",
                "scale_algorithm", "scale_tolerance", "content_aware_factor",
                "content_aware_max_dimension", "content_aware_seam_mode",
            ),
        )
    ]
    if params.get("posterize_enabled", False):
        stages.append(
            _stage(
                "posterize",
                params,
                (
                    "posterize_levels", "posterize_range_mode", "posterize_range_low",
                    "posterize_range_high", "posterize_percentile_low",
                    "posterize_percentile_high", "posterize_gamma", "posterize_mix",
                    "posterize_channel_mask", "posterize_alpha_policy",
                ),
            )
        )
    if params.get("dither_type", "NONE") != "NONE":
        stages.append(
            _stage(
                "dither",
                params,
                (
                    "dither_type", "dither_strategy", "dither_blend_mode",
                    "use_gray_dither", "dither_strength", "dither_saturation",
                    "custom_dither_resolution", "dither_mask_lum_low",
                    "dither_mask_lum_high", "dither_mask_sat_low",
                    "dither_mask_sat_high", "dither_mask_gradient_angle",
                    "dither_mask_invert", "dither_mask_blur", "show_mask_controls",
                    "lock_dither_to_grid", "dither_mask_type", "dither_cutoff",
                    "dither_mask_gamma", "palette_dither_contrast",
                    "palette_dither_invert",
                ),
            )
        )
    if params.get("quantize_type", "NONE") != "NONE":
        stages.append(
            _stage(
                "quantize",
                params,
                (
                    "quantize_type", "diffusion", "diffusion_strength",
                    "diffusion_serpentine", "initialize_mode", "color_mode",
                    "apply_palette_mode", "quantize_quality",
                    "quantize_seed", "use_explicit_quantize_seed",
                    "chroma_importance", "use_chroma_importance",
                    "use_pixelated_for_quantize", "k_num_colors", "gamma",
                    "force_colors", "palette_extract_method", "palette_sort_mode",
                    "palette_shift", "palette_trim", "palette_replace_threshold",
                    "output_palette", "output_lut",
                    "use_range_adaptive", "quantize_colors_or_bits",
                    "quantize_colors", "quantize_bits", "output_default_lut", "lut",
                    "cube_lut_interpolation", "cube_lut_strength",
                ),
            )
        )
    finish_keys = (
        "finish_enabled", "finish_brightness", "finish_contrast", "finish_exposure",
        "finish_saturation", "finish_grain", "finish_grain_brightness",
        "finish_grain_saturation", "finish_scanline_strength", "finish_scanline_size",
        "finish_scanline_axis", "finish_scanline_invert", "finish_vignette_strength", "finish_vignette_roundness",
        "finish_chromatic_aberration", "finish_mask_type", "finish_mask_mix",
        "finish_mask_invert", "finish_channel_mask",
    )
    if params.get("finish_enabled", False) or any(key in params for key in finish_keys[1:]):
        stages.append(_stage("display_finish", params, finish_keys))
    stage_order = params.get("v3_stage_order")
    stage_enabled = params.get("v3_stage_enabled", {})
    if not isinstance(stage_enabled, dict):
        stage_enabled = {}
    if stage_order:
        by_type = {stage["type"]: stage for stage in stages}
        ordered = []
        for stage_type in stage_order:
            stage = by_type.pop(stage_type, None)
            if stage is not None:
                stage["enabled"] = bool(stage_enabled.get(stage_type, True))
                ordered.append(stage)
        # Keep a valid plan if a future UI removed a stage from its collection.
        ordered.extend(by_type.values())
        stages = ordered
    elif stage_enabled:
        for stage in stages:
            if stage["type"] in stage_enabled:
                stage["enabled"] = bool(stage_enabled[stage["type"]])
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "stages": stages,
        "outputs": {
            "palette": bool(params.get("output_palette", False)),
            # These are distinct user-facing outputs.  Older snapshots used
            # ``lut`` as an aggregate; :func:`plan_to_params` retains a
            # compatibility path for plans without ``default_lut``.
            "lut": bool(params.get("output_lut", False)),
            "default_lut": bool(params.get("output_default_lut", False)),
        },
        "policies": {
            "v3_palette_lock": params.get("v3_palette_lock", "OFF"),
            "v3_palette_lock_strength": float(params.get("v3_palette_lock_strength", 1.0)),
            "v3_grid_coherence": params.get("v3_grid_coherence", "OFF"),
        },
        "legacy_params": copy.deepcopy(params),
    }


def validate_plan(plan):
    """Validate a plan and return it, raising ValueError for bad user data."""
    if not isinstance(plan, dict):
        raise ValueError("PixelatorPlus plan must be a dictionary")
    version = int(plan.get("schema_version", PLAN_SCHEMA_VERSION))
    if version > PLAN_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported PixelatorPlus plan schema {version}; "
            f"maximum supported schema is {PLAN_SCHEMA_VERSION}"
        )
    stages = plan.get("stages", [])
    if not isinstance(stages, (list, tuple)):
        raise ValueError("PixelatorPlus plan stages must be a list")
    positions = []
    seen = set()
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("type") not in _KNOWN_STAGES:
            raise ValueError(f"unknown PixelatorPlus stage: {stage!r}")
        stage_type = stage["type"]
        if stage_type in seen:
            raise ValueError(f"duplicate PixelatorPlus stage: {stage_type}")
        seen.add(stage_type)
        if not isinstance(stage.get("settings", {}), dict):
            raise ValueError("PixelatorPlus stage settings must be a dictionary")
        if "enabled" in stage and not isinstance(stage["enabled"], bool):
            raise ValueError("PixelatorPlus stage enabled flag must be boolean")
        positions.append(_CANONICAL_STAGE_ORDER.index(stage_type))
    if positions != sorted(positions):
        raise ValueError("PixelatorPlus v3 stages must use dependency order")
    policies = plan.get("policies", {})
    if not isinstance(policies, dict):
        raise ValueError("PixelatorPlus plan policies must be a dictionary")
    palette_lock = str(policies.get("v3_palette_lock", "OFF")).upper()
    if palette_lock not in _V3_PALETTE_LOCKS:
        raise ValueError(f"unknown PixelatorPlus palette lock: {palette_lock}")
    grid_coherence = str(policies.get("v3_grid_coherence", "OFF")).upper()
    if grid_coherence not in _V3_GRID_COHERENCE:
        raise ValueError(f"unknown PixelatorPlus grid coherence: {grid_coherence}")
    try:
        lock_strength = float(policies.get("v3_palette_lock_strength", 1.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("PixelatorPlus palette lock strength must be numeric") from exc
    if not math.isfinite(lock_strength) or not 0.0 <= lock_strength <= 1.0:
        raise ValueError("PixelatorPlus palette lock strength must be between 0 and 1")
    return plan


def plan_to_params(plan):
    """Flatten a validated plan over its optional legacy settings snapshot.

    The legacy snapshot preserves scalar settings that are not represented by
    a stage declaration, including inactive controls.  Canonical stages,
    output declarations, and policies are authoritative whenever both forms
    name the same setting.
    """
    validate_plan(plan)
    params = dict(plan.get("legacy_params", {}))
    for stage in plan.get("stages", []):
        params.update(stage.get("settings", {}))

    # A plan is the source of truth for its executable stage declarations.
    # Preserve flags for stage slots absent from the executable plan (so a
    # snapshot retains inactive UI choices), then replace every declared
    # stage's legacy flag with the canonical value.  Rebuild the order in the
    # fixed dependency sequence rather than allowing legacy metadata to
    # reorder a validated plan on its next normalization.
    legacy_order = params.get("v3_stage_order", ())
    if not isinstance(legacy_order, (list, tuple)):
        legacy_order = ()
    legacy_enabled = params.get("v3_stage_enabled", {})
    if not isinstance(legacy_enabled, dict):
        legacy_enabled = {}
    stage_ids = {
        stage_type for stage_type in legacy_order
        if stage_type in _KNOWN_STAGES
    }
    stage_ids.update(
        stage_type for stage_type in legacy_enabled
        if stage_type in _KNOWN_STAGES
    )
    stage_ids.update(stage["type"] for stage in plan.get("stages", ()))
    params["v3_stage_order"] = tuple(
        stage_type for stage_type in _CANONICAL_STAGE_ORDER
        if stage_type in stage_ids
    )
    params["v3_stage_enabled"] = {
        stage_type: bool(value)
        for stage_type, value in legacy_enabled.items()
        if stage_type in _KNOWN_STAGES
    }
    for stage in plan.get("stages", ()):
        params["v3_stage_enabled"][stage["type"]] = bool(
            stage.get("enabled", True)
        )

    outputs = plan.get("outputs", {})
    if "palette" in outputs:
        params["output_palette"] = bool(outputs["palette"])
    if "lut" in outputs:
        params["output_lut"] = bool(outputs["lut"])
    if "default_lut" in outputs:
        params["output_default_lut"] = bool(outputs["default_lut"])
    elif "lut" in outputs:
        # Schema-4 snapshots written before ``default_lut`` used ``lut`` as
        # a single generated-LUT switch.  A disabled canonical declaration
        # must still disable a contradictory legacy default-LUT flag.
        params["output_default_lut"] = (
            bool(params.get("output_default_lut", False))
            and bool(outputs["lut"])
        )
    params.update(plan.get("policies", {}))
    return params


def normalize_plan(params):
    """Return a validated plan for either legacy params or plan-shaped input."""
    if isinstance(params, dict) and "stages" in params:
        plan = copy.deepcopy(params)
        plan.setdefault("schema_version", PLAN_SCHEMA_VERSION)
        plan.setdefault("legacy_params", plan_to_params(plan))
        validate_plan(plan)
        return plan
    return validate_plan(legacy_to_plan(params))


def stage_types(plan):
    """Return stable stage identifiers in execution order."""
    return tuple(
        stage["type"] for stage in validate_plan(plan).get("stages", ())
        if stage.get("enabled", True)
    )


def plan_to_dict(plan):
    """Return a deep-copied, validated plan suitable for serialization."""
    return copy.deepcopy(validate_plan(plan))


def plan_to_json(plan, indent=2):
    """Serialize a validated plan as a portable scene/recipe snapshot.

    Image datablocks are deliberately not embedded: the plan contains scalar
    settings and stage order, while image pins remain Blender datablock links
    owned by the current scene.
    """
    payload = {
        "format": PLAN_FORMAT,
        "format_version": 1,
        "plan": plan_to_dict(plan),
    }
    return json.dumps(payload, indent=indent, sort_keys=True) + "\n"


def plan_from_json(text):
    """Parse and validate a plan snapshot produced by :func:`plan_to_json`."""
    try:
        payload = json.loads(str(text))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid PixelatorPlus plan JSON") from exc
    if not isinstance(payload, dict) or payload.get("format") != PLAN_FORMAT:
        raise ValueError("not a PixelatorPlus plan snapshot")
    if int(payload.get("format_version", 0)) != 1:
        raise ValueError("unsupported PixelatorPlus plan snapshot format")
    plan = payload.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("PixelatorPlus plan snapshot has no plan object")
    return validate_plan(plan)


def plan_fingerprint(plan):
    """Return a stable short fingerprint for UI confirmation and cache logs."""
    encoded = plan_to_json(plan, indent=None).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:12]
