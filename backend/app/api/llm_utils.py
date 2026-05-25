import base64
import json
import math
from google import genai
from anthropic import Anthropic
from app.core.config import settings
from loguru import logger
from PIL import Image
import io
import os
from typing import Optional, List, Dict, Any

# Gold density constants
GOLD_DENSITIES = {
    "9K": 11.38,
    "14K": 13.07,
    "18K": 15.58,
    "22K": 17.50,
    "24K": 19.30
}

RING_SIZE_TO_DIAM = {
    4: 14.8, 4.5: 15.3, 5: 15.7, 5.5: 16.1,
    6: 16.5, 6.5: 16.9, 7: 17.3, 7.5: 17.7,
    8: 18.2, 8.5: 18.6, 9: 19.0, 9.5: 19.4,
    10: 19.8,
}

# ─── Profile Factors (metal volume fraction of bounding rectangle) ────────────
PROFILE_FACTORS = {
    "D-shape":      0.75,
    "flat":         0.90,
    "comfort_fit":  0.70,
    "half_round":   0.78,
    "bypass":       0.70,   # bypass/twisted shank
    "tapered":      0.72,
}

# ─── Head Factors (calibrated from 20 rings) ─────────────────────────────────
# How much of the bounding box (L × W × H) is actually metal
HEAD_FACTORS = {
    "prong":    0.20,   # 4 or 6 prongs + thin basket — 80% air
    "bezel":    0.35,   # full metal wall around stone — less air
    "bar":      0.30,   # bar-set side rails
    "tension":  0.10,   # minimal metal, just two tips
    "channel":  0.25,   # channel walls on both sides
    "east_west":0.35,   # east-west bezel bar setting (same as bezel)
}

# ─── Side Stone Factors ───────────────────────────────────────────────────────
SIDE_STONE_FACTORS = {
    "prong":    0.25,   # shared prong: air between prongs
    "pave":     0.15,   # pave: metal removed for channels
    "channel":  0.30,   # channel walls retain more metal
    "bar":      0.28,
    "none":     0.00,
}

# ─── MASTER CALIBRATION TABLE (from 20-ring ground truth) ────────────────────
# Key: (style_name): {band_width_mm, band_thickness_mm, profile_factor,
#                     head_factor_key, side_factor_key,
#                     typical_side_coverage_pct, pave_reduction_pct,
#                     has_milgrain}
#
# band_width: what the LLM should estimate from visual (guidance)
# band_thickness: THE CRITICAL CALIBRATED CONSTANT — do not change
#
STYLE_CALIBRATION = {
    "bypass": {
        "band_width_guidance":    "2.0–2.5mm — bypass shanks are narrow",
        "band_thickness_mm":      2.07,   # THICK! bypass twist adds metal
        "profile_factor":         0.70,   # bypass curve
        "head_factor":            "prong",
        "side_factor":            "none",  # no side stones on bypass
        "side_coverage_pct":      0,
        "pave_reduction_pct":     0,
        "milgrain_add":           False,
        "notes": "Two large center stones on bypass shank. Shank is thicker "
                 "than it looks because the twist/curve requires more metal. "
                 "Head volume from BOTH stones.",
    },
    "toi_et_moi": {  # alias for bypass
        "band_width_guidance":    "2.0–2.5mm",
        "band_thickness_mm":      2.07,
        "profile_factor":         0.70,
        "head_factor":            "prong",
        "side_factor":            "none",
        "side_coverage_pct":      0,
        "pave_reduction_pct":     0,
        "milgrain_add":           False,
        "notes": "Same as bypass.",
    },
    "halo": {
        "band_width_guidance":    "2.5–3.0mm",
        "band_thickness_mm":      1.73,
        "profile_factor":         0.75,
        "head_factor":            "prong",
        "side_factor":            "prong",
        "side_coverage_pct":      80,    # halo ring around center
        "pave_reduction_pct":     5,
        "milgrain_add":           True,
        "notes": "Halo frame counts as 'side stones' with 80% coverage. "
                 "The milgrain adds ~4% metal.",
    },
    "vintage": {
        "band_width_guidance":    "2.8–3.5mm",
        "band_thickness_mm":      1.27,
        "profile_factor":         0.75,
        "head_factor":            "prong",
        "side_factor":            "prong",
        "side_coverage_pct":      70,
        "pave_reduction_pct":     0,
        "milgrain_add":           True,
        "notes": "Milgrain edges + side stones on band. Calibrated from img9.",
    },
    "solitaire": {
        "band_width_guidance":    "2.0–3.0mm",
        "band_thickness_mm":      1.20,
        "profile_factor":         0.75,
        "head_factor":            "prong",
        "side_factor":            "none",
        "side_coverage_pct":      0,
        "pave_reduction_pct":     0,
        "milgrain_add":           False,
        "notes": "Clean plain shank, single center stone.",
    },
    "cluster": {
        "band_width_guidance":    "2.5–3.0mm",
        "band_thickness_mm":      1.25,
        "profile_factor":         0.75,
        "head_factor":            "prong",
        "side_factor":            "prong",
        "side_coverage_pct":      40,
        "pave_reduction_pct":     0,
        "milgrain_add":           False,
        "notes": "Marquise or small stone clusters on shoulders. Calibrated img17.",
    },
    "pave_single": {
        "band_width_guidance":    "3.5–5.0mm",
        "band_thickness_mm":      1.10,
        "profile_factor":         0.75,
        "head_factor":            "prong",
        "side_factor":            "pave",
        "side_coverage_pct":      85,
        "pave_reduction_pct":     15,
        "milgrain_add":           False,
        "notes": "Single row of pave diamonds. Metal removed for channels.",
    },
    "pave_double": {
        "band_width_guidance":    "7.0–9.0mm — visually VERY wide",
        "band_thickness_mm":      1.05,   # thin wall despite wide band
        "profile_factor":         0.75,
        "head_factor":            "prong",
        "side_factor":            "pave",
        "side_coverage_pct":      85,
        "pave_reduction_pct":     20,     # significant metal removed for channels
        "milgrain_add":           False,
        "notes": "Two rows of pave. Wide but thin-walled. Calibrated from imgs 11-14.",
    },
    "eternity": {
        "band_width_guidance":    "3.0–4.5mm",
        "band_thickness_mm":      0.92,
        "profile_factor":         0.80,
        "head_factor":            "prong",
        "side_factor":            "prong",
        "side_coverage_pct":      100,   # full circumference
        "pave_reduction_pct":     0,
        "milgrain_add":           False,
        "notes": "Full eternity: 100% stone coverage. No separate center head. "
                 "Calibrated from img10 (baguette eternity).",
    },
    "chevron": {
        "band_width_guidance":    "3.5–4.5mm at center, tapers",
        "band_thickness_mm":      0.80,  # very thin
        "profile_factor":         0.75,
        "head_factor":            "prong",
        "side_factor":            "pave",
        "side_coverage_pct":      50,    # only top arc has stones
        "pave_reduction_pct":     15,
        "milgrain_add":           False,
        "notes": "Curved/chevron band, stones on top arc only. Very thin. Img16.",
    },
    "bezel": {
        "band_width_guidance":    "3.5–4.5mm — bezel needs wider shank",
        "band_thickness_mm":      0.88,  # very thin shank, boxy head
        "profile_factor":         0.90,  # flat shank profile
        "head_factor":            "bezel",
        "side_factor":            "none",
        "side_coverage_pct":      0,
        "pave_reduction_pct":     0,
        "milgrain_add":           False,
        "notes": "East-west bar/bezel setting. Thin round shank, thick boxy head. "
                 "Calibrated from imgs 18-19. Img20 was slightly off (oval bezel "
                 "bar is more metal than emerald bezel).",
    },
    "band": {
        "band_width_guidance":    "4.0–8.0mm",
        "band_thickness_mm":      1.20,
        "profile_factor":         0.80,
        "head_factor":            "prong",
        "side_factor":            "none",
        "side_coverage_pct":      0,
        "pave_reduction_pct":     0,
        "milgrain_add":           False,
        "notes": "Plain wedding band. No stones.",
    },
    "default": {
        "band_width_guidance":    "2.5–3.0mm",
        "band_thickness_mm":      1.20,
        "profile_factor":         0.75,
        "head_factor":            "prong",
        "side_factor":            "prong",
        "side_coverage_pct":      0,
        "pave_reduction_pct":     0,
        "milgrain_add":           False,
        "notes": "Fallback when style not recognized.",
    },
}

def calculate_volume(
    ring_size: float,
    style: str,
    band_width_mm: float,           # estimated from image
    heads: list,                    # list of (length_mm, width_mm, height_mm)
    side_coverage_pct: float = None, # override if known
    pave_reduction_pct: float = None,
    has_milgrain: bool = None,
    band_thickness_override: float = None,  # if LLM provides, use it; else calibrated
) -> dict:
    """
    Calculate gold volume using calibrated constants.
    Returns dict with volume_mm3 and per-karat weights.
    """
    cal = STYLE_CALIBRATION.get(style.lower(), STYLE_CALIBRATION["default"])

    # Inner circumference from ring size
    sizes = sorted(RING_SIZE_TO_DIAM.keys())
    closest = min(sizes, key=lambda s: abs(s - ring_size))
    inner_diam = RING_SIZE_TO_DIAM[closest]
    inner_circ = inner_diam * math.pi

    # Band thickness: use calibrated unless LLM provides AND it's reasonable
    bt = cal["band_thickness_mm"]
    if band_thickness_override is not None:
        # Only use LLM's estimate if it's close to calibrated (within 50%)
        if 0.5 * bt <= band_thickness_override <= 1.5 * bt:
            bt = band_thickness_override
        # else: discard LLM's estimate, use calibrated

    pf  = cal["profile_factor"]
    hf  = HEAD_FACTORS[cal["head_factor"]]
    sf  = SIDE_STONE_FACTORS[cal["side_factor"]]
    cov = side_coverage_pct if side_coverage_pct is not None else cal["side_coverage_pct"]
    pr  = pave_reduction_pct if pave_reduction_pct is not None else cal["pave_reduction_pct"]
    mg  = has_milgrain if has_milgrain is not None else cal["milgrain_add"]

    shank    = inner_circ * band_width_mm * bt * pf
    head_vol = sum(L * W * H * hf for L, W, H in heads)
    side     = shank * (cov / 100) * sf
    pave_red = shank * (pr / 100)
    milgrain = shank * 0.04 if mg else 0

    total_vol = shank + head_vol + side - pave_red + milgrain
    safe_vol  = total_vol * 1.08   # +8% safety buffer

    weights = {}
    for karat, density in GOLD_DENSITIES.items():
        w_base = total_vol * density / 1000
        w_safe = safe_vol  * density / 1000
        weights[karat] = {
            "min_g":      round(w_base * 0.90, 3),
            "base_g":     round(w_base, 3),
            "safe_cap_g": round(w_safe, 3),
        }

    return {
        "volume_mm3":     round(total_vol, 1),
        "safe_volume_mm3":round(safe_vol, 1),
        "breakdown": {
            "shank_mm3":    round(shank, 1),
            "head_mm3":     round(head_vol, 1),
            "side_mm3":     round(side, 1),
            "pave_red_mm3": round(pave_red, 1),
            "milgrain_mm3": round(milgrain, 1),
        },
        "params": {
            "inner_diam_mm":    inner_diam,
            "inner_circ_mm":    round(inner_circ, 2),
            "band_thickness_mm":bt,
            "profile_factor":   pf,
            "head_factor":      hf,
        },
        "weights": weights,
    }

GEOMETRY_PROMPT = """You are an expert Jewelry CAD Engineer. Analyze this ring image.

IMPORTANT: You are estimating ONLY these dimensions. Band thickness is handled by the
backend using calibrated constants — do NOT estimate it, it will be ignored.

STYLE RECOGNITION IS CRITICAL. Pick exactly one:
  "bypass"       — Two stones on a twisted bypass shank (toi-et-moi style)
  "halo"         — Center stone surrounded by halo of smaller stones  
  "vintage"      — Milgrain edges + side stones, ornate setting
  "solitaire"    — Single center stone, plain or simple shank
  "cluster"      — Center stone flanked by marquise/petal clusters
  "pave_single"  — Single row of pave diamonds on band
  "pave_double"  — TWO rows of pave diamonds (band looks very wide 7-9mm)
  "eternity"     — Diamonds all the way around the band, no plain back
  "chevron"      — Thin curved/chevron band, diamonds on top arc only
  "bezel"        — Stone set in metal bezel/bar (east-west orientation common)
  "band"         — Plain band, no center stone
  "other"        — None of the above

ESTIMATE THESE (in millimeters):
  band_width_mm         — Width of the shank (NOT including side stones visually)
  head_stones           — Array of objects, one per center stone:
    {{ "shape": "round|oval|pear|marquise|emerald|radiant|heart|cushion|trillion",
      "length_mm": X, "width_mm": Y, "height_mm": Z,
      "setting": "prong|bezel|bar|channel|tension" }}
  side_stone_coverage_pct — What % of visible band has side stones (0–100)
  side_stone_setting      — "prong"|"pave"|"channel"|"none"
  pave_reduction_pct      — Extra metal removed for pave channels (0=prong, 15=single pave, 20=double pave)
  has_milgrain            — true/false
  complexity_notes        — One sentence

RING PARAMETERS:
{ring_params}

Return ONLY valid JSON — no markdown, no extra text:
{{
  "ring_style": "bypass",
  "band_width_mm": 2.2,
  "head_stones": [
    {{"shape": "oval", "length_mm": 8.0, "width_mm": 6.0, "height_mm": 3.5, "setting": "prong"}},
    {{"shape": "oval", "length_mm": 8.0, "width_mm": 6.0, "height_mm": 3.5, "setting": "prong"}}
  ],
  "side_stone_coverage_pct": 0,
  "side_stone_setting": "none",
  "pave_reduction_pct": 0,
  "has_milgrain": false,
  "complexity_notes": "Two oval stones on twisted bypass shank"
}}"""

def format_rag_context(rag_results: list) -> tuple[str, float, float]:
    """
    Format RAG results for the Stage 2 prompt context.
    Returns (formatted_string, rag_mean_vol, rag_mean_weight).
    """
    if not rag_results:
        return "No RAG context available.", 0.0, 0.0

    lines = []
    total_vol = 0.0
    total_weight = 0.0
    count_vol = 0
    count_weight = 0

    for i, r in enumerate(rag_results):
        meta = r.get("metadata", {})
        score = r.get("score", 0.0)
        p_name = meta.get("product_name", "Unknown Ring")
        karat = str(meta.get("karat", "18K")).upper()

        # Get volume and weight, resolving from each other if needed
        vol = meta.get("actual_volume_mm3") or meta.get("predicted_volume_mm3")
        weight = meta.get("actual_weight_g") or meta.get("predicted_weight_14k") or meta.get("predicted_weight_18k")

        if vol is None and weight is not None:
            density = GOLD_DENSITIES.get(karat, 15.58)
            vol = (weight / density) * 1000.0 if density else 0.0

        if weight is None and vol is not None:
            density = GOLD_DENSITIES.get(karat, 15.58)
            weight = (vol * density) / 1000.0 if density else 0.0

        vol_val = float(vol) if vol is not None else 0.0
        w_val = float(weight) if weight is not None else 0.0

        lines.append(
            f"- Ref {i+1}: Name: {p_name} | Karat: {karat} | Volume: {vol_val:.1f} mm³ | Weight: {w_val:.2f}g | Similarity Score: {score:.4f}"
        )

        if vol_val > 0:
            total_vol += vol_val
            count_vol += 1
        if w_val > 0:
            total_weight += w_val
            count_weight += 1

    mean_vol = total_vol / count_vol if count_vol > 0 else 0.0
    mean_weight = total_weight / count_weight if count_weight > 0 else 0.0

    formatted_str = "\n".join(lines)
    return formatted_str, mean_vol, mean_weight

def volume_to_weights(volume_mm3: float) -> dict:
    """
    Returns dict: karat -> {"min_g": base * 0.90, "base_g": base, "safe_cap_g": base * 1.08}
    Formula: weight_g = (density * volume) / 1000
    """
    res = {}
    for karat, density in GOLD_DENSITIES.items():
        base = (density * volume_mm3) / 1000.0
        res[karat] = {
            "min_g": base * 0.90,
            "base_g": base,
            "safe_cap_g": base * 1.08
        }
    return res

def _extract_json(text: str) -> dict:
    """Extracts the first complete JSON object from LLM text output."""
    start = text.find('{')
    end = text.rfind('}') + 1
    
    if start == -1 or end == 0:
        logger.error(f"Failed to find JSON in response: {text[:500]}")
        raise ValueError("LLM response did not contain valid JSON")
    
    return json.loads(text[start:end])

def _compute_confidence(
    volume_source: str,
    stage1_vol: float,
    rag_mean_vol: float,
    top_rag_score: float
) -> float:
    """
    Calculates confidence score based on LLM/RAG deviation and similarity scores.
    """
    if volume_source == "physics_fallback":
        return 0.20
        
    conf = 0.50
    if rag_mean_vol > 0:
        deviation = abs(stage1_vol - rag_mean_vol) / rag_mean_vol
        if deviation < 0.10:
            conf += 0.25
        elif deviation < 0.20:
            conf += 0.10
        else:
            conf -= 0.10
            
    if top_rag_score > 0.90:
        conf += 0.20
    elif top_rag_score > 0.80:
        conf += 0.10
        
    return max(0.05, min(0.95, conf))

async def predict_gold_weight(
    client: Optional[genai.Client],
    images: List[bytes],
    ring_size: Optional[float],
    style: Optional[str],
    karat: int = 18,
    rag_results: Optional[List[dict]] = None,
    xgboost_prediction: Optional[float] = None
) -> dict:
    """
    Two-stage LLM prediction pipeline with RAG blending and XGBoost ensemble.
    """
    logger.info("Executing two-stage LLM gold weight prediction pipeline...")
    
    # 1. Geometry Calculations
    ring_size_val = ring_size if ring_size is not None else 7.0
    diameter_lookup = {
        4: 14.8, 4.5: 15.3, 5: 15.7, 5.5: 16.1, 6: 16.5, 6.5: 16.9,
        7: 17.3, 7.5: 17.7, 8: 18.2, 8.5: 18.6, 9: 19.0, 9.5: 19.4, 10: 19.8
    }
    
    # Find closest size in lookup
    closest_size = min(diameter_lookup.keys(), key=lambda s: abs(s - ring_size_val))
    inner_diameter_mm = diameter_lookup[closest_size]
    inner_circumference_mm = inner_diameter_mm * math.pi
    
    karat_str = str(karat).upper().strip()
    if not karat_str.endswith("K"):
        karat_str = f"{karat_str}K"
    density = GOLD_DENSITIES.get(karat_str, 15.58)

    # Resolve client if none provided
    if client is None:
        gemini_key = settings.GEMINI_API_KEY
        if gemini_key:
            client = genai.Client(api_key=gemini_key, http_options={'api_version': 'v1beta'})
            
    # Initialise default fallback data
    fallback_vol_data = calculate_volume(ring_size_val, style or "default", 2.8, [], None, None, None)
    fallback_vol = fallback_vol_data["volume_mm3"]
    
    # Check if Gemini Client is active
    if client is None:
        logger.warning("No Gemini Client or API key found. Using physics fallback path.")
        stage1_data = {
            "band_width_mm": 2.8,
            "band_thickness_mm": 1.2,
            "band_profile": "comfort_fit",
            "head_length_mm": 0.0,
            "head_width_mm": 0.0,
            "head_height_mm": 0.0,
            "num_prongs": 0,
            "has_gallery": False,
            "side_stone_coverage_pct": 0,
            "pave_metal_reduction_pct": 0,
            "ring_style": style or "unknown",
            "complexity_notes": "Fallback default",
            "volume_mm3": fallback_vol
        }
        stage1_ok = False
    else:
        # --- STAGE 1: Geometry Extraction ---
        ring_params_str = f"- US Ring Size: {ring_size_val}\n- Inner Diameter: {inner_diameter_mm:.2f} mm\n- Inner Circumference: {inner_circumference_mm:.2f} mm\n- User Provided Ring Style: {style or 'Not specified'}\n- Target Karat: {karat_str}"
        stage1_prompt = GEOMETRY_PROMPT.format(ring_params=ring_params_str)
        try:
            logger.info("Executing Stage 1: Geometry Extraction...")
            contents = [stage1_prompt]
            for img_bytes in images:
                img = Image.open(io.BytesIO(img_bytes))
                contents.append(img)
                
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=contents
            )
            
            if not response or not response.text:
                raise ValueError("Empty response from Stage 1 LLM call")
                
            stage1_data = _extract_json(response.text)
            
            ring_style = stage1_data.get("ring_style", style or "default")
            bw = float(stage1_data.get("band_width_mm", 2.8))
            heads_raw = stage1_data.get("head_stones", [])
            heads = []
            for h in heads_raw:
                heads.append((float(h.get("length_mm", 0)), float(h.get("width_mm", 0)), float(h.get("height_mm", 0))))
            
            cov = stage1_data.get("side_stone_coverage_pct")
            cov = float(cov) if cov is not None else None
            
            pr = stage1_data.get("pave_reduction_pct")
            pr = float(pr) if pr is not None else None
            
            mg = stage1_data.get("has_milgrain")
            mg = bool(mg) if mg is not None else None
            
            calc_result = calculate_volume(ring_size_val, ring_style, bw, heads, cov, pr, mg)
            stage1_data["volume_mm3"] = calc_result["volume_mm3"]
            stage1_data["band_thickness_mm"] = calc_result["params"]["band_thickness_mm"]
            
            logger.info(f"Stage 1 success: volume={stage1_data.get('volume_mm3')} mm³")
            stage1_ok = True
        except Exception as e:
            logger.error(f"Stage 1 LLM extraction failed: {e}. Falling back to physics formula.")
            stage1_data = {
                "band_width_mm": 2.8,
                "band_thickness_mm": 1.2,
                "band_profile": "comfort_fit",
                "head_length_mm": 0.0,
                "head_width_mm": 0.0,
                "head_height_mm": 0.0,
                "num_prongs": 0,
                "has_gallery": False,
                "side_stone_coverage_pct": 0,
                "pave_metal_reduction_pct": 0,
                "ring_style": style or "unknown",
                "complexity_notes": "Fallback default",
                "volume_mm3": fallback_vol
            }
            stage1_ok = False

    # Get stage 1 geometry volume
    stage1_vol = float(stage1_data.get("volume_mm3") or fallback_vol)
    
    # 2. RAG Context Integration
    rag_context_str, rag_mean_vol, rag_mean_weight = format_rag_context(rag_results)
    
    # Get min/max and scores from RAG
    rag_min_vol = 0.0
    rag_max_vol = 0.0
    top_rag_score = 0.0
    rag_count = 0
    
    if rag_results:
        rag_vols = []
        for r in rag_results:
            meta = r.get("metadata", {})
            score = r.get("score", 0.0)
            top_rag_score = max(top_rag_score, score)
            
            vol = meta.get("actual_volume_mm3") or meta.get("predicted_volume_mm3")
            if vol is None:
                w = meta.get("actual_weight_g") or meta.get("predicted_weight_14k")
                k = str(meta.get("karat", "18K")).upper()
                if w is not None:
                    d = GOLD_DENSITIES.get(k, 15.58)
                    vol = (w / d) * 1000.0 if d else 0.0
            if vol:
                rag_vols.append(float(vol))
                
        if rag_vols:
            rag_min_vol = min(rag_vols)
            rag_max_vol = max(rag_vols)
            rag_count = len(rag_vols)

    # Apply Two-Stage Blend & Refinement
    final_vol = stage1_vol
    volume_source = "geometry_llm"
    confidence_lbl = "medium"
    reasoning = "Calculated directly from visual geometry."
    
    # If RAG results exist, execute Stage 2 prompt (or run python fallback if LLM is disabled)
    if rag_results and rag_count > 0:
        if client is None:
            # Run local Python refinement fallback directly
            logger.info("Running Python-based RAG refinement fallback...")
            ref_data = {
                "final_volume_mm3": stage1_vol,
                "volume_source": "geometry_llm",
                "confidence": "medium",
                "reasoning": "RAG exists but Gemini client is unavailable. Applied default pipeline."
            }
            # Perform calculations in python
            deviation = abs(stage1_vol - rag_mean_vol) / rag_mean_vol if rag_mean_vol > 0 else 0.0
            if deviation > 0.15:
                ref_data["final_volume_mm3"] = 0.5 * stage1_vol + 0.5 * rag_mean_vol
                ref_data["volume_source"] = "ensemble_rag_blend"
            
            ref_data["final_volume_mm3"] = ref_data["final_volume_mm3"] * 1.08 # +8% safety buffer
            
            # Clamp to [RAG_min * 0.6, RAG_max * 1.4]
            lower = rag_min_vol * 0.6
            upper = rag_max_vol * 1.4
            ref_data["final_volume_mm3"] = max(lower, min(upper, ref_data["final_volume_mm3"]))
            
            final_vol = ref_data["final_volume_mm3"]
            volume_source = ref_data["volume_source"]
            reasoning = ref_data["reasoning"]
        else:
            # --- STAGE 2: Refinement with RAG Context ---
            stage2_prompt = f"""You are a master goldsmith and estimator. Refine the estimated ring volume using the visually similar RAG reference designs.

=== STAGE 1 EXTRACTED GEOMETRY JSON ===
{json.dumps(stage1_data, indent=2)}

=== VISUALLY SIMILAR REFERENCE DESIGNS (RAG Context) ===
{rag_context_str}

- RAG Mean Volume: {rag_mean_vol:.2f} mm³
- RAG Min Volume: {rag_min_vol:.2f} mm³
- RAG Max Volume: {rag_max_vol:.2f} mm³

=== REFINEMENT RULES ===
1. Compare the Stage 1 geometry volume ({stage1_vol:.2f} mm³) with the RAG Mean Volume ({rag_mean_vol:.2f} mm³).
2. Deviation Check:
   - Calculate deviation = abs(geometry_volume - RAG_mean_volume) / RAG_mean_volume.
   - If deviation is greater than 15% (i.e. > 0.15), you must blend the volumes:
     blended_volume = 0.5 * geometry_volume + 0.5 * RAG_mean_volume
     Set volume_source = "ensemble_rag_blend"
   - Otherwise, keep the original geometry volume:
     blended_volume = geometry_volume
     Set volume_source = "geometry_llm"
3. Apply safety buffer:
   buffered_volume = blended_volume * 1.08  (apply a strict +8% manufacturing safety buffer)
4. Clamp the volume:
   - Ensure the final volume is clamped between:
     Minimum: {rag_min_vol * 0.6:.2f} mm³ (RAG_min * 0.6)
     Maximum: {rag_max_vol * 1.4:.2f} mm³ (RAG_max * 1.4)
   - If buffered_volume is outside this range, clamp it to the boundaries.

=== EXPECTED STRICT JSON OUTPUT ===
Return a strict JSON object with EXACTLY these keys:
{{
  "final_volume_mm3": float,
  "volume_source": "geometry_llm" | "ensemble_rag_blend",
  "confidence": "high" | "medium" | "low",
  "reasoning": string
}}
"""
            try:
                logger.info("Executing Stage 2: RAG Context Refinement...")
                response = client.models.generate_content(
                    model='gemini-3-flash-preview',
                    contents=[stage2_prompt]
                )
                
                if not response or not response.text:
                    raise ValueError("Empty response from Stage 2 LLM call")
                    
                ref_data = _extract_json(response.text)
                final_vol = float(ref_data.get("final_volume_mm3") or stage1_vol)
                volume_source = ref_data.get("volume_source") or "geometry_llm"
                confidence_lbl = ref_data.get("confidence") or "medium"
                reasoning = ref_data.get("reasoning") or "Refined with Stage 2 RAG context"
                logger.info(f"Stage 2 success: final_volume={final_vol} mm³, source={volume_source}")
            except Exception as e:
                logger.error(f"Stage 2 LLM refinement failed: {e}. Executing python-based fallback math.")
                # Run python mathematical logic fallback
                deviation = abs(stage1_vol - rag_mean_vol) / rag_mean_vol if rag_mean_vol > 0 else 0.0
                if deviation > 0.15:
                    blended = 0.5 * stage1_vol + 0.5 * rag_mean_vol
                    source = "ensemble_rag_blend"
                else:
                    blended = stage1_vol
                    source = "geometry_llm"
                    
                buffered = blended * 1.08
                lower = rag_min_vol * 0.6
                upper = rag_max_vol * 1.4
                final_vol = max(lower, min(upper, buffered))
                volume_source = f"{source}_fallback"
                reasoning = f"Stage 2 failed. Python refined volume: {final_vol:.1f} mm³"
    else:
        # No RAG context at all. Just apply 8% safety buffer to Stage 1 geometry volume
        final_vol = stage1_vol * 1.08
        volume_source = "geometry_llm"
        reasoning = "No RAG context available. Applied +8% safety buffer to visual geometry."

    # If Stage 1 call was aborted or failed AND no RAG refinement was applied,
    # use the physics fallback. But if RAG refinement did run, keep that result.
    if not stage1_ok and client is None:
        if rag_results and rag_count > 0:
            # RAG refinement already ran and produced a meaningful volume — keep it
            volume_source = f"rag_refined_no_llm"
            reasoning = (
                f"LLM unavailable (no Gemini API key). Used RAG visual similarity "
                f"({rag_count} refs, mean vol={rag_mean_vol:.1f} mm³) blended with "
                f"physics calibration. Add a Gemini API key in Admin Panel for full AI reasoning."
            )
            logger.info(f"No LLM client but RAG refinement preserved: final_vol={final_vol:.1f} mm³")
        else:
            # No RAG and no LLM — true fallback
            volume_source = "physics_fallback"
            final_vol = fallback_vol
            reasoning = "Using physics-based default formula fallback. Please verify Gemini API key connection."

    # 3. Base weight calculation
    base_weight = (density * final_vol) / 1000.0
    
    # 4. XGBoost Ensemble Blend (80% LLM/RAG, 20% XGBoost converted from 14K)
    ensemble_applied = False
    if xgboost_prediction is not None:
        xgb_weight_for_karat = xgboost_prediction * (density / 13.07)  # convert from 14K grams to target karat density
        final_weight = 0.80 * base_weight + 0.20 * xgb_weight_for_karat
        ensemble_applied = True
        logger.info(f"Ensemble blended: LLM/RAG Weight={base_weight:.3f}g, XGB Weight={xgb_weight_for_karat:.3f}g, Final={final_weight:.3f}g")
    else:
        final_weight = base_weight
        logger.info(f"No XGBoost prediction available. final_weight = base_weight = {final_weight:.3f}g")

    # 5. Confidence scoring
    confidence_val = _compute_confidence(
        volume_source=volume_source,
        stage1_vol=stage1_vol,
        rag_mean_vol=rag_mean_vol,
        top_rag_score=top_rag_score
    )

    # 6. Multi-karat generation
    all_karats = {}
    for k_name, k_density in GOLD_DENSITIES.items():
        base_w = (k_density * final_vol) / 1000.0
        if xgboost_prediction is not None:
            xgb_w = xgboost_prediction * (k_density / 13.07)
            predict_w = 0.80 * base_w + 0.20 * xgb_w
        else:
            predict_w = base_w
            
        all_karats[k_name] = {
            "min_g": base_w * 0.90,
            "base_g": base_w,
            "predict_g": predict_w,
            "safe_cap_g": base_w * 1.08
        }

    # Format explanatory note
    geom_note = f"Band width: {stage1_data.get('band_width_mm')}mm, thickness: {stage1_data.get('band_thickness_mm')}mm. "
    full_explanation = f"Source: {volume_source}. {geom_note}Reasoning: {reasoning}. Confidence: {confidence_val:.2f}."

    return {
        "predicted_weight_g": final_weight,
        "karat": karat_str,
        "volume_mm3": stage1_vol,
        "safe_volume_mm3": final_vol,
        "volume_source": volume_source,
        "ensemble_applied": ensemble_applied,
        "confidence": confidence_val,
        "all_karats": all_karats,
        "rag_mean_weight_g": rag_mean_weight,
        "rag_count": rag_count,
        "geometry": {
            "band_width_mm": stage1_data.get("band_width_mm", 0.0),
            "band_thickness_mm": stage1_data.get("band_thickness_mm", 0.0),
            "ring_style": stage1_data.get("ring_style", style or "unknown"),
            "complexity_notes": stage1_data.get("complexity_notes", "")
        },
        "explanation": full_explanation,
        # Maintain backwards compatibility outputs
        "min_weight_14k": all_karats["14K"]["min_g"],
        "max_weight_14k": all_karats["14K"]["safe_cap_g"],
        "min_weight_18k": all_karats["18K"]["min_g"],
        "max_weight_18k": all_karats["18K"]["safe_cap_g"],
        "min_weight_22k": all_karats["22K"]["min_g"],
        "max_weight_22k": all_karats["22K"]["safe_cap_g"],
        "predicted_weight_14k": all_karats["14K"]["predict_g"],
        "predicted_weight_18k": all_karats["18K"]["predict_g"],
        "predicted_weight_22k": all_karats["22K"]["predict_g"],
        "raw": {
            "confidence": confidence_lbl,
            "confidence_note": reasoning,
            "volume_breakdown": {
                "total_volume_mm3": final_vol,
                "stage1_geometry_volume_mm3": stage1_vol,
                "band_width_mm": stage1_data.get("band_width_mm"),
                "band_thickness_mm": stage1_data.get("band_thickness_mm"),
                "ring_style": stage1_data.get("ring_style"),
                "complexity_notes": stage1_data.get("complexity_notes")
            }
        }
    }
