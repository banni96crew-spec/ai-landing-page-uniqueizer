```markdown
---
name: media-uniqueizer-pillow-numpy-inplace
description: Implements in-place media mutation using Pillow and numpy with strict format filtering, EXIF stripping via RGB conversion, 1px crop, and bounded noise injection. Use when editing backend/worker/module_media.py in Backend / Worker.
---
# media-uniqueizer-pillow-numpy-inplace

## When to use
Use this skill when working on:

- `backend/worker/module_media.py`
- Module 4 (Media Uniqueizer)
- Image mutation logic
- M5.1–M5.5 implementation
- EC-08 handling

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§3.3, M5.1–M5.5:

- Use Pillow ≥ 10.0 and numpy.
- Supported formats:
  - `.jpg`
  - `.jpeg`
  - `.png`
  - `.webp`
- Skip GIF and SVG (log warn).
- Strip EXIF via RGB conversion + save(exif=b"").
- Crop 1px.
- Inject noise with intensity ≤ 0.01.
- Modify images **in-place**.
- Iterate via `rglob("*")`.
- EC-08: `PIL.UnidentifiedImageError` → log warn + skip.

---

## Required instruction

In `module_media.py`:

- For `img_path in rewritten_dir.rglob("*")` filter by `SUPPORTED_FORMATS`.
- Wrap in `try/except PIL.UnidentifiedImageError → log warn, skip`.
- Convert: `img.convert('RGB')`.
- Save without EXIF: `img.save(path, exif=b"")`.
- Crop: `img.crop((0,0,w-1,h-1))`.
- Noise:
  ```python
  np.clip(arr + np.random.normal(0, noise_intensity*255, arr.shape), 0, 255)
  ```
- Skip GIF/SVG with warn log.

---

## Non-negotiable rules

1. Use Pillow and numpy only.
2. Must operate in-place (overwrite original file).
3. Use `rglob("*")`.
4. Must filter by `SUPPORTED_FORMATS`.
5. Must skip `.gif` and `.svg` with warn.
6. Must catch `UnidentifiedImageError`.
7. Must strip EXIF via RGB conversion.
8. Must crop exactly 1px.
9. Noise intensity must not exceed 0.01.
10. Worker must not crash.

---

# Required constants

```python
SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.webp']
```

---

# Required implementation structure

## Directory traversal

```python
for img_path in rewritten_dir.rglob("*"):
    if not img_path.is_file():
        continue

    ext = img_path.suffix.lower()

    if ext in ('.gif', '.svg'):
        log_warn(job_id, f"Skipping unsupported format: {img_path.name}")
        continue

    if ext not in SUPPORTED_FORMATS:
        continue
```

---

## Open image (EC-08)

```python
from PIL import Image, UnidentifiedImageError

try:
    with Image.open(img_path) as img:
        ...
except UnidentifiedImageError:
    log_warn(job_id, f"Unidentified image skipped: {img_path.name}")
    continue
```

Must not fail job.

---

## EXIF stripping via RGB conversion

```python
img = img.convert("RGB")
```

Then save with:

```python
img.save(img_path, exif=b"")
```

Must explicitly pass `exif=b""`.

---

## Crop 1px

```python
w, h = img.size

if w > 1 and h > 1:
    img = img.crop((0, 0, w - 1, h - 1))
```

- Crop exactly 1px from bottom-right.
- Must not crop negative dimensions.

---

## Noise injection

```python
import numpy as np

arr = np.array(img).astype(np.float32)

sigma = noise_intensity * 255
noise = np.random.normal(0, sigma, arr.shape)

noised = np.clip(arr + noise, 0, 255).astype(np.uint8)

img = Image.fromarray(noised)
```

Rules:

- `noise_intensity ≤ 0.01`
- Never exceed 1%.
- Must multiply by 255.
- Must clip to `[0,255]`.

---

## Save in-place

```python
img.save(img_path, exif=b"")
```

- Overwrite original.
- Do not create new file.
- Do not change path.
- Do not rename.

---

# Correct execution order per image

1. Filter extension.
2. Open image.
3. Convert to RGB.
4. Crop 1px.
5. Apply noise.
6. Save with `exif=b""`.

---

# Skip logic

- `.gif` → log warn + skip.
- `.svg` → log warn + skip.
- `UnidentifiedImageError` → log warn + skip.

Must not fail job.

---

# Prohibited patterns

- ❌ Processing GIF
- ❌ Processing SVG
- ❌ Using OpenCV
- ❌ Creating new files
- ❌ Changing filenames
- ❌ Not stripping EXIF
- ❌ Noise intensity > 0.01
- ❌ Not clipping pixel range
- ❌ Crashing on corrupt image
- ❌ Not using rglob("*")

---

# Definition of done

- Only supported formats processed
- GIF/SVG skipped with warn
- `UnidentifiedImageError` handled
- RGB conversion performed
- EXIF stripped via `exif=b""`
- 1px crop applied
- Noise applied using numpy
- Values clipped to [0,255]
- Images overwritten in-place
- Worker remains stable
```