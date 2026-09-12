# Crop quality models

The four trained MobileNetV3-Large checkpoints live here and **are committed**
to the repository, so a fresh clone can run photo analysis without any extra
download.

Every fact below was read out of the checkpoint binaries themselves
(`python -m ml.inspect_quality_models`) — nothing here is assumed.

| Crop                    | File                                           | Classes                                   |
|-------------------------|------------------------------------------------|-------------------------------------------|
| Tomato                  | `tomato_mobilenetv3_large.pth`                 | Damaged, Old, Ripe, Unripe                |
| Potato                  | `potato_mobilenetv3_large.pth`                 | Defective, Good Condition                 |
| Chile Pepper            | `chile_pepper_mobilenetv3_large.pth`           | Damaged, Dried, Old, Ripe, Unripe         |
| New Mexico Green Chile  | `new_mexico_green_chile_mobilenetv3_large.pth` | Damaged, Dried, Old, Ripe, Unripe         |

Architecture: torchvision `mobilenet_v3_large`, classifier head at
`classifier.3`. Each file loads with 312/312 tensors matched, 0 missing and 0
unexpected — so the architecture is confirmed, not guessed.

Checkpoint format: `{"model_state_dict": OrderedDict, "classes": [...]}`.

## What these models predict

**Physical condition / ripeness — not a market grade and not a disease.**
The API returns `result_type: "condition"` and the UI says so, because
printing "Grade A" over a class called `Ripe` would misrepresent the model.

Only these four crops are supported. Anything else — Onion included — is
refused with `reason: "unsupported_crop"`. A grade is never guessed.

## Class labels

`ml/quality_inference.py` reads labels in this order:

1. from inside the checkpoint (`classes`, `class_names`, `labels` or
   `idx_to_class`) — this is what all four files use;
2. from a sidecar `<model>.labels.json`, or a shared `labels.json` in this
   directory — a JSON list ordered by class index;
3. otherwise classes are reported by index and the response sets
   `labels_known: false`. **No mapping is ever invented.**

`num_classes` is read from the checkpoint's own final layer, so the 2-class
potato head and the 5-class chile heads both load without configuration.

## Preprocessing

The training code for these checkpoints is **not present in this repository**
(no `ml/training/`, `ml/preprocessing/` or `ml/inference/` in any branch), so
the exact transform used at training time cannot be proven from the source.
Inference therefore uses the torchvision reference pipeline for
MobileNetV3-Large — resize 256 → centre-crop 224 → normalise with mean
`[0.485, 0.456, 0.406]`, std `[0.229, 0.224, 0.225]` — and reports it in every
response as `model.preprocess_source: "default (torchvision ImageNet)"`.

If the real training transform differs, override it **without touching the
weights** by dropping a sidecar next to the checkpoint:

```json
// tomato_mobilenetv3_large.preprocess.json
{"resize": 232, "center_crop": 224, "mean": [0.5,0.5,0.5], "std": [0.5,0.5,0.5]}
```

Values saved inside a checkpoint (`preprocess`, `transform_config`,
`input_size`) take priority over a sidecar; a sidecar takes priority over the
default.

## Requirements

`torch`, `torchvision` and `Pillow` (see `requirements.txt`). Install the
torch/torchvision pair from <https://download.pytorch.org/whl/cpu> so the
versions match — a mismatched pair fails at import with
`torchvision::nms does not exist`.

Without a checkpoint the API reports `available: false` and the UI asks the
farmer to set the grade manually — it never shows a guessed grade.
