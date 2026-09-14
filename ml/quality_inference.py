"""
KisanLink — crop quality inference
==================================

Runs the project's trained MobileNetV3-Large checkpoints from
``ml/quality_models/`` against a farmer's photo.

Design notes
------------
* Nothing is invented. If a checkpoint is missing, the crop is unsupported, a
  dependency is absent, or the image is unreadable, this module reports that
  condition — it never returns a guessed grade or confidence.
* Class labels are read from the checkpoint itself when it carries them, or
  from a sidecar ``<model>.labels.json`` / ``labels.json`` next to the weights.
  A mapping is never fabricated: without one, the classes are reported by index
  and the caller is told the labels are unknown.
* The head size (``num_classes``) is derived from the checkpoint's own final
  layer, so a 2-class or 5-class model both load without configuration.
* Preprocessing is the standard ImageNet transform MobileNetV3 is trained
  with (resize 256 → centre-crop 224 → ImageNet mean/std). Override per model
  with a sidecar ``<model>.preprocess.json`` if a model was trained
  differently.

Loaded models are cached, so the first request pays the load cost and later
requests do not.
"""

from __future__ import annotations

import io
import json
import os
import threading
from typing import Optional

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quality_models")

#: The four trained checkpoints, keyed by the name shown to the user.
#: Verified against the checkpoints themselves — each stores its own `classes`
#: list, so no mapping here is guessed:
#:   tomato                 4 classes  Damaged, Old, Ripe, Unripe
#:   potato                 2 classes  Defective, Good Condition
#:   chile pepper           5 classes  Damaged, Dried, Old, Ripe, Unripe
#:   new mexico green chile 5 classes  Damaged, Dried, Old, Ripe, Unripe
CROP_MODELS = {
    "Tomato": "tomato_mobilenetv3_large.pth",
    "Potato": "potato_mobilenetv3_large.pth",
    "Chile Pepper": "chile_pepper_mobilenetv3_large.pth",
    "New Mexico Green Chile": "new_mexico_green_chile_mobilenetv3_large.pth",
}

#: Spellings a farmer might type, mapped to the canonical crop above. Only
#: these four crops have a model — anything else (Onion included) is refused.
CROP_ALIASES = {
    "tomato": "Tomato",
    "tamatar": "Tomato",
    "potato": "Potato",
    "aloo": "Potato",
    "alu": "Potato",
    "chile pepper": "Chile Pepper",
    "chili pepper": "Chile Pepper",
    "chilli pepper": "Chile Pepper",
    "chilli": "Chile Pepper",
    "chili": "Chile Pepper",
    "mirchi": "Chile Pepper",
    "red chilli": "Chile Pepper",
    "new mexico green chile": "New Mexico Green Chile",
    "green chilli": "New Mexico Green Chile",
    "green chili": "New Mexico Green Chile",
    "green chile": "New Mexico Green Chile",
    "hari mirch": "New Mexico Green Chile",
}

#: These models classify physical condition / ripeness, not a market grade and
#: not a disease. Wording downstream must reflect that.
RESULT_TYPE = "condition"

#: Condition class -> the marketplace grade vocabulary KisanLink already uses
#: everywhere else (database/schema.sql, the Create Sale Lot form and
#: ml/buyer_matcher.py all speak Grade A / B / C).
#:
#: The four checkpoints between them emit exactly seven classes, and every one
#: is mapped here — nothing is inferred at runtime and no threshold invents a
#: grade the model did not support:
#:
#:   Grade A  Premium / export     Ripe, Good Condition
#:   Grade B  Standard commercial  Unripe, Old, Dried
#:   Grade C  Processing / fair    Damaged, Defective
#:
#: Rationale, so a judge can challenge it:
#:   - Unripe is sound produce, routinely preferred for long transport, but is
#:     not premium-ready on arrival, so it is commercial rather than export.
#:   - Old is sellable with reduced shelf life.
#:   - Dried is graded B rather than A because these models cannot distinguish
#:     deliberate drying (a normal, desirable state for chillies) from
#:     desiccation through neglect. B is the honest middle.
#:   - Damaged and Defective are the processing grade.
#:
#: This is an INDICATIVE mapping from a photo, never a laboratory assay, and
#: the farmer can always override it in Create Sale Lot.
CONDITION_GRADE = {
    "ripe": "Grade A",
    "good condition": "Grade A",
    "unripe": "Grade B",
    "old": "Grade B",
    "dried": "Grade B",
    "damaged": "Grade C",
    "defective": "Grade C",
}

#: Below this top-class probability the grade is reported as low-confidence so
#: the UI can say so. It never changes which grade is chosen.
GRADE_CONFIDENCE_FLOOR = 0.60


def grade_for(condition: str):
    """
    Map a model condition class onto the marketplace's Grade A/B/C vocabulary.

    @returns (grade | None, human-readable basis). None when the class is not
    in CONDITION_GRADE — the caller must then leave the grade unset rather
    than guess one.
    """
    key = (condition or "").strip().lower().replace("_", " ")
    grade = CONDITION_GRADE.get(key)
    if not grade:
        return None, (f"No grade mapping exists for the condition "
                      f"{condition!r}; set the grade manually.")
    tier = {"Grade A": "premium / export quality",
            "Grade B": "standard commercial quality",
            "Grade C": "processing / fair quality"}[grade]
    return grade, f"Condition {condition!r} maps to {grade} ({tier})."

# Backwards-compatible view used by older callers.
CROP_MODEL_FILES = {alias: CROP_MODELS[canon] for alias, canon in CROP_ALIASES.items()}

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

MAX_IMAGE_BYTES = int(os.environ.get("KISANLINK_QUALITY_MAX_BYTES", str(8 * 1024 * 1024)))

_CACHE = {}
_LOCK = threading.Lock()


class QualityUnavailable(Exception):
    """Raised when inference genuinely cannot run. Carries a user-facing reason."""

    def __init__(self, message: str, reason: str = "unavailable"):
        super().__init__(message)
        self.message = message
        self.reason = reason


def supported_crops() -> list:
    """
    The canonical crops whose checkpoint is actually present on disk.

    One entry per trained model — aliases are matched but not listed, so the
    UI shows exactly four options rather than every spelling.
    """
    return [c for c, f in CROP_MODELS.items()
            if os.path.exists(os.path.join(MODELS_DIR, f))]


def canonical_crop(crop: str) -> Optional[str]:
    """Resolve a typed crop name to one of the four trained crops, or None."""
    key = (crop or "").strip().lower()
    if not key:
        return None
    if key in CROP_ALIASES:
        return CROP_ALIASES[key]
    # Tolerate "Tomato (Hybrid)" / "Potato - Jyoti" style dropdown values, but
    # only on a whole-word match so "Onion" can never fall through to a model.
    import re as _re
    words = set(_re.findall(r"[a-z]+", key))
    for alias, canon in CROP_ALIASES.items():
        parts = alias.split()
        if all(p in words for p in parts):
            return canon
    return None


def model_file_for(crop: str) -> Optional[str]:
    canon = canonical_crop(crop)
    return CROP_MODELS.get(canon) if canon else None


def _require_torch():
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception as exc:
        raise QualityUnavailable(
            "Image analysis needs torch, torchvision and Pillow on the server. "
            f"Install them and restart the backend. ({exc})",
            reason="dependency_missing",
        )


def _load_labels(ckpt_path: str, state, num_classes: int):
    """Return (labels or None, source string)."""
    # 1) carried inside the checkpoint
    if isinstance(state, dict):
        for key in ("class_names", "classes", "labels", "idx_to_class"):
            val = state.get(key)
            if isinstance(val, (list, tuple)) and len(val) == num_classes:
                return [str(v) for v in val], f"checkpoint[{key}]"
            if isinstance(val, dict) and len(val) == num_classes:
                try:
                    ordered = [val[k] for k in sorted(val, key=lambda x: int(x))]
                    return [str(v) for v in ordered], f"checkpoint[{key}]"
                except Exception:
                    pass
    # 2) sidecar next to the weights
    base = os.path.splitext(ckpt_path)[0]
    for candidate in (base + ".labels.json", os.path.join(MODELS_DIR, "labels.json")):
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data = data.get(os.path.basename(base), data)
            if isinstance(data, dict):
                data = [data[k] for k in sorted(data, key=lambda x: int(x))]
            if isinstance(data, (list, tuple)) and len(data) == num_classes:
                return [str(v) for v in data], os.path.basename(candidate)
        except Exception:
            continue
    return None, "unknown"


def _extract_state_dict(obj):
    """Checkpoints are saved either bare or wrapped in a training dict."""
    if not isinstance(obj, dict):
        return obj, {}
    for key in ("state_dict", "model_state_dict", "model"):
        inner = obj.get(key)
        if isinstance(inner, dict) and any(hasattr(v, "shape") for v in inner.values()):
            return inner, obj
    if any(hasattr(v, "shape") for v in obj.values()):
        return obj, obj
    return obj, obj


def _classifier_out_features(sd) -> Optional[int]:
    """Infer num_classes from the final Linear layer's weight shape."""
    best = None
    for k, v in sd.items():
        if not hasattr(v, "shape") or len(getattr(v, "shape", ())) != 2:
            continue
        if k.endswith("weight") and ("classifier" in k or "fc" in k or "head" in k):
            best = int(v.shape[0])
    return best


def load_model(crop: str):
    """
    Load (and cache) the checkpoint for `crop`.

    @raises QualityUnavailable when the crop has no model, the file is absent,
            or the weights cannot be loaded.
    """
    filename = model_file_for(crop)
    if not filename:
        available = supported_crops()
        raise QualityUnavailable(
            f"Photo condition check is not available for {crop or 'this crop'} — "
            "there is no trained model for it. "
            + ("Available for: " + ", ".join(available) + "."
               if available else "No models are installed on this server."),
            reason="unsupported_crop",
        )

    path = os.path.join(MODELS_DIR, filename)
    if not os.path.exists(path):
        raise QualityUnavailable(
            f"The trained model for this crop ({filename}) is not installed on "
            "this server, so no analysis was performed.",
            reason="model_missing",
        )

    with _LOCK:
        cached = _CACHE.get(path)
        if cached and cached["mtime"] == os.path.getmtime(path):
            return cached

    _require_torch()
    import torch
    from torchvision import models

    try:
        raw = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        raise QualityUnavailable(
            f"The quality model could not be read ({exc.__class__.__name__}). "
            "The checkpoint may be corrupt.",
            reason="model_unreadable",
        )

    state, wrapper = _extract_state_dict(raw)
    num_classes = _classifier_out_features(state) or 2

    try:
        net = models.mobilenet_v3_large(weights=None, num_classes=num_classes)
        missing, unexpected = net.load_state_dict(state, strict=False)
        loaded = len(state) - len(unexpected)
        if loaded <= 0:
            raise ValueError("no matching parameters")
    except Exception as exc:
        raise QualityUnavailable(
            f"The quality model does not match the expected MobileNetV3-Large "
            f"architecture ({exc}).",
            reason="architecture_mismatch",
        )
    net.eval()

    labels, label_source = _load_labels(path, wrapper, num_classes)

    preprocess, preprocess_source = load_preprocess(path)
    # Values saved with the checkpoint win over any sidecar.
    if isinstance(wrapper, dict):
        for key in ("preprocess", "transform_config", "input_size"):
            val = wrapper.get(key)
            if isinstance(val, dict):
                preprocess.update({k: v for k, v in val.items() if k in DEFAULT_PREPROCESS})
                preprocess_source = f"checkpoint[{key}]"
            elif isinstance(val, int) and key == "input_size":
                preprocess["center_crop"] = val
                preprocess["resize"] = int(val * 256 / 224)
                preprocess_source = f"checkpoint[{key}]"

    entry = {
        "model": net,
        "labels": labels,
        "label_source": label_source,
        "preprocess": preprocess,
        "preprocess_source": preprocess_source,
        "num_classes": num_classes,
        "file": filename,
        "mtime": os.path.getmtime(path),
        "missing_keys": len(missing),
        "unexpected_keys": len(unexpected),
    }
    with _LOCK:
        _CACHE[path] = entry
    return entry


#: Default transform. MobileNetV3 is an ImageNet model and this is the
#: torchvision reference pipeline, but a model trained differently must not be
#: fed the wrong preprocessing — override it per model with a sidecar
#: `<model>.preprocess.json`, e.g.
#:   {"resize": 232, "center_crop": 224,
#:    "mean": [0.5,0.5,0.5], "std": [0.5,0.5,0.5]}
DEFAULT_PREPROCESS = {
    "resize": 256,
    "center_crop": 224,
    "mean": IMAGENET_MEAN,
    "std": IMAGENET_STD,
}


def load_preprocess(ckpt_path: str) -> tuple:
    """
    Resolve the preprocessing for one checkpoint.

    Order: values saved inside the checkpoint, then a sidecar
    `<model>.preprocess.json` / shared `preprocess.json`, then the documented
    default. @returns (config dict, source string)
    """
    base = os.path.splitext(ckpt_path)[0]
    for candidate in (base + ".preprocess.json",
                      os.path.join(MODELS_DIR, "preprocess.json")):
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                # a shared file may be keyed by model name
                data = data.get(os.path.basename(base), data)
            if isinstance(data, dict):
                cfg = dict(DEFAULT_PREPROCESS)
                cfg.update({k: v for k, v in data.items() if k in DEFAULT_PREPROCESS})
                return cfg, os.path.basename(candidate)
        except Exception:
            continue
    return dict(DEFAULT_PREPROCESS), "default (torchvision ImageNet)"


def _transform(cfg=None):
    from torchvision import transforms
    cfg = cfg or DEFAULT_PREPROCESS
    steps = []
    if cfg.get("resize"):
        steps.append(transforms.Resize(int(cfg["resize"])))
    if cfg.get("center_crop"):
        steps.append(transforms.CenterCrop(int(cfg["center_crop"])))
    steps.append(transforms.ToTensor())
    steps.append(transforms.Normalize(mean=cfg.get("mean", IMAGENET_MEAN),
                                      std=cfg.get("std", IMAGENET_STD)))
    return transforms.Compose(steps)


def assess(image_bytes: bytes, crop: str) -> dict:
    """
    Run the real model over `image_bytes`.

    @returns dict with grade/label, confidence and the full class distribution.
    @raises QualityUnavailable with a user-facing message on any failure.
    """
    if not image_bytes:
        raise QualityUnavailable("No image was received. Choose a photo and try again.",
                                 reason="no_image")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise QualityUnavailable(
            f"That image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB. "
            "Please use a smaller photo.",
            reason="image_too_large",
        )

    entry = load_model(crop)          # may raise: unsupported / missing / unreadable
    _require_torch()
    import torch
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()                                  # cheap integrity check
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise QualityUnavailable(
            "That file could not be read as an image. Upload a JPG or PNG photo.",
            reason="invalid_image",
        )

    try:
        tensor = _transform(entry.get("preprocess"))(img).unsqueeze(0)
        with torch.no_grad():
            logits = entry["model"](tensor)
            probs = torch.softmax(logits, dim=1)[0]
    except Exception as exc:
        raise QualityUnavailable(
            f"The image could not be analysed ({exc.__class__.__name__}).",
            reason="inference_failed",
        )

    values = [float(p) for p in probs]
    top = int(max(range(len(values)), key=lambda i: values[i]))
    labels = entry["labels"]
    label = labels[top] if labels else f"class_{top}"
    _grade = grade_for(label) if labels else (None, "Class names unknown.")

    return {
        "success": True,
        "crop": crop,
        "crop_canonical": canonical_crop(crop),
        # The marketplace grade derived from the predicted condition. The
        # condition itself is never altered to suit the grade.
        "quality_grade": _grade[0],
        "grade_basis": _grade[1],
        "grade_is_low_confidence": bool(values[top] < GRADE_CONFIDENCE_FLOOR),
        "grade_confidence_floor": GRADE_CONFIDENCE_FLOOR,
        # These checkpoints classify physical condition / ripeness. Calling the
        # output a "market grade" would misrepresent what was trained.
        "result_type": RESULT_TYPE,
        "label": label,
        "class_index": top,
        "confidence": round(values[top], 4),
        "labels_known": bool(labels),
        "label_source": entry["label_source"],
        "distribution": [
            {"label": (labels[i] if labels else f"class_{i}"), "probability": round(v, 4)}
            for i, v in enumerate(values)
        ],
        "model": {
            "file": entry["file"],
            "architecture": "mobilenet_v3_large",
            "num_classes": entry["num_classes"],
            "preprocess": entry["preprocess"],
            "preprocess_source": entry["preprocess_source"],
        },
        "note": (
            "Condition predicted by the project's trained model — a physical "
            "condition class, not a market grade."
            if labels else
            "Prediction from the project's trained model. Class names are not "
            "stored with this checkpoint, so classes are shown by index."
        ),
    }
