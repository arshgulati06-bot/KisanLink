"""
Inspect the trained quality checkpoints in ``ml/quality_models/``.

Run this on the machine that actually holds the ``.pth`` files:

    python -m ml.inspect_quality_models

For each checkpoint it prints what the file itself says — checkpoint format,
architecture fit, ``num_classes``, any embedded class names or preprocessing —
and then states plainly whether a class mapping is available or still needs a
sidecar. It reads only; nothing is modified, retrained or written.

Use it to answer "what were these models trained to output?" without guessing.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml import quality_inference as qi  # noqa: E402


def _describe(path: str) -> dict:
    import torch

    out = {"file": os.path.basename(path), "size_mb": round(os.path.getsize(path) / 1e6, 1)}
    try:
        raw = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        out["error"] = f"{exc.__class__.__name__}: {exc}"
        return out

    state, wrapper = qi._extract_state_dict(raw)
    out["checkpoint_format"] = (
        "bare state_dict" if state is wrapper else "training dict wrapping a state_dict"
    )
    if isinstance(wrapper, dict) and state is not wrapper:
        out["top_level_keys"] = sorted(k for k in wrapper if not hasattr(wrapper[k], "shape"))

    out["num_parameters_tensors"] = sum(1 for v in state.values() if hasattr(v, "shape"))
    n = qi._classifier_out_features(state)
    out["num_classes"] = n

    # final classifier layer, verbatim
    for k, v in state.items():
        if hasattr(v, "shape") and len(v.shape) == 2 and k.endswith("weight") \
                and ("classifier" in k or "fc" in k or "head" in k):
            out["classifier_layer"] = f"{k}  shape={tuple(v.shape)}"

    # does it actually fit MobileNetV3-Large?
    try:
        from torchvision import models
        net = models.mobilenet_v3_large(weights=None, num_classes=n or 2)
        missing, unexpected = net.load_state_dict(state, strict=False)
        out["architecture_fit"] = {
            "model": "torchvision mobilenet_v3_large",
            "matched": len(state) - len(unexpected),
            "missing_keys": len(missing),
            "unexpected_keys": len(unexpected),
            "verdict": "exact" if not missing and not unexpected else "partial",
        }
    except Exception as exc:
        out["architecture_fit"] = {"error": str(exc)}

    labels, label_source = qi._load_labels(path, wrapper, n or 0)
    out["labels"] = labels
    out["label_source"] = label_source
    pre, pre_src = qi.load_preprocess(path)
    out["preprocess"] = pre
    out["preprocess_source"] = pre_src
    return out


def main() -> int:
    d = qi.MODELS_DIR
    print(f"Models directory: {d}")
    if not os.path.isdir(d):
        print("  -> directory does not exist.")
        return 1

    files = sorted(f for f in os.listdir(d) if f.endswith(".pth"))
    if not files:
        print("  -> no .pth checkpoints found.")
        return 1

    needs_labels = []
    for name in files:
        info = _describe(os.path.join(d, name))
        print("\n" + "=" * 68)
        print(info["file"], f"({info['size_mb']} MB)")
        print("=" * 68)
        if "error" in info:
            print("  COULD NOT READ:", info["error"])
            continue
        print(f"  checkpoint format : {info['checkpoint_format']}")
        if info.get("top_level_keys"):
            print(f"  top-level keys    : {info['top_level_keys']}")
        print(f"  weight tensors    : {info['num_parameters_tensors']}")
        print(f"  num_classes       : {info['num_classes']}")
        print(f"  classifier layer  : {info.get('classifier_layer', 'not found')}")
        fit = info["architecture_fit"]
        if "error" in fit:
            print(f"  architecture      : ERROR {fit['error']}")
        else:
            print(f"  architecture      : {fit['model']} -> {fit['verdict']} "
                  f"(matched {fit['matched']}, missing {fit['missing_keys']}, "
                  f"unexpected {fit['unexpected_keys']})")
        print(f"  class labels      : {info['labels'] if info['labels'] else 'NOT FOUND'}")
        print(f"  label source      : {info['label_source']}")
        print(f"  preprocessing     : {json.dumps(info['preprocess'])}")
        print(f"  preprocess source : {info['preprocess_source']}")
        if not info["labels"] and info["num_classes"]:
            needs_labels.append((info["file"], info["num_classes"]))

    print("\n" + "=" * 68)
    if needs_labels:
        print("ACTION NEEDED — these checkpoints carry no class names, so the API")
        print("will report classes by index (labels_known: false) until you add a")
        print("sidecar. Create one file per model, ordered by class index:\n")
        for fname, n in needs_labels:
            base = os.path.splitext(fname)[0]
            example = json.dumps([f"<class {i} name>" for i in range(n)])
            print(f"  {os.path.join('ml', 'quality_models', base + '.labels.json')}")
            print(f"      {example}\n")
        print("Take the names from the training script's dataset class order —")
        print("torchvision's ImageFolder sorts class folders alphabetically.")
    else:
        print("All checkpoints have class names available. No action needed.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
