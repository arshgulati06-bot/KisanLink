# Crop quality models

Place the project's trained checkpoints here. They are **not** committed —
`.pth` files are large binaries and are gitignored.

Expected filenames (MobileNetV3-Large):

| Crop                    | File                                             |
|-------------------------|--------------------------------------------------|
| Tomato                  | `tomato_mobilenetv3_large.pth`                   |
| Potato                  | `potato_mobilenetv3_large.pth`                   |
| Chile pepper            | `chile_pepper_mobilenetv3_large.pth`             |
| New Mexico green chile  | `new_mexico_green_chile_mobilenetv3_large.pth`   |

## Class labels

`ml/quality_inference.py` reads labels in this order:

1. from inside the checkpoint (`class_names`, `classes`, `labels` or
   `idx_to_class`), when it was saved as a training dict;
2. from a sidecar `<model>.labels.json` next to the weights, or a shared
   `labels.json` in this directory — a JSON list ordered by class index, e.g.
   `["Grade A", "Grade B", "Grade C"]`;
3. otherwise classes are reported by index and the response sets
   `labels_known: false`. **No mapping is ever invented.**

`num_classes` is read from the checkpoint's own final layer, so 2-class and
n-class heads both load without configuration.

## Preprocessing

Standard ImageNet transform: resize 256 → centre-crop 224 → normalise with
mean `[0.485, 0.456, 0.406]`, std `[0.229, 0.224, 0.225]`.

## Requirements

`torch`, `torchvision` and `Pillow` must be installed. Without a checkpoint the
API reports `available: false` and the UI asks the farmer to set the grade
manually — it never shows a guessed grade.
