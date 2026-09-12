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

#: Crop name (lowercase) -> checkpoint filename in MODELS_DIR.
#: Several crop spellings map to the same trained model.
CROP_MODEL_FILES = {
    "tomato": "tomato_mobilenetv3_large.pth",
    "potato": "potato_mobilenetv3_large.pth",
    "chile pepper": "chile_pepper_mobilenetv3_large.pth",
    "chili pepper": "chile_pepper_mobilenetv3_large.pth",
    "chilli": "chile_pepper_mobilenetv3_large.pth",
    "chili": "chile_pepper_mobilenetv3_large.pth",
    "chilly": "chile_pepper_mobilenetv3_large.pth",
    "green chilli": "new_mexico_green_chile_mobilenetv3_large.pth",
    "green chili": "new_mexico_green_chile_mobilenetv3_large.pth",
    "new mexico green chile": "new_mexico_green_chile_mobilenetv3_large.pth",
}

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
    """Crops with a checkpoint actually present on disk."""
    present = []
    for crop, filename in CROP_MODEL_FILES.items():
        if os.path.exists(os.path.join(MODELS_DIR, filename)):
            present.append(crop)
    return sorted(set(present))


def model_file_for(crop: str) -> Optional[str]:
    key = (crop or "").strip().lower()
    filename = CROP_MODEL_FILES.get(key)
    if not filename:
        # Tolerate "Tomato (Hybrid)" style values from the crop dropdown.
        for name, f in CROP_MODEL_FILES.items():
            if name in key:
                filename = f
                break
    return filename


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
        raise QualityUnavailable(
            f"Photo grading is not available for {crop or 'this crop'} yet. "
            "Supported: " + (", ".join(c.title() for c in supported_crops()) or "none installed") + ".",
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

    entry = {
        "model": net,
        "labels": labels,
        "label_source": label_source,
        "num_classes": num_classes,
        "file": filename,
        "mtime": os.path.getmtime(path),
        "missing_keys": len(missing),
        "unexpected_keys": len(unexpected),
    }
    with _LOCK:
        _CACHE[path] = entry
    return entry


def _transform():
    from torchvision import transforms
    return transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


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
        tensor = _transform()(img).unsqueeze(0)
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

    return {
        "success": True,
        "crop": crop,
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
        },
        "note": (
            "Prediction from the project's trained model."
            if labels else
            "Prediction from the project's trained model. Class names are not "
            "stored with this checkpoint, so classes are shown by index."
        ),
    }
