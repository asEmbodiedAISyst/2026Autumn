# Class 02 supplier and research illustrations

The current lecture uses original illustrations to connect physical devices, published implementation diagrams and research systems. Source illustrations retain their original typography. They have not been relabelled as MiSans figures. The existing course-authored physical/telemetry figures use MiSans; their generation code is listed in FIGURE-CODE.md.

## Figure-to-source record

| Lecture figure | Published filename | Source and operation |
|---|---|---|
| 1 | `02-command-reference-response.png` | Saved XC330 Mode-5 record; existing `code/lesson_figures_v08.py` |
| 2 | `01-actuator-and-geometry.png` | Existing course physical/CAD identity panel; `code/lesson_figures_v08.py` |
| 3 | `source-performance-curve.png` | Supplied original ROBOTIS performance-curve image; unchanged pixels and original labels |
| 4 | `robotis-position-controller.png` | Official ROBOTIS controller image; WebP-to-PNG format conversion only |
| 5 | `robotis-current-position-controller.png` | Official ROBOTIS current-based position image; format conversion only |
| 6 | `leap-hand-figure1.png` | Shaw, Agarwal, and Pathak (2023), Figure 1; cropped from PDF page 1 |
| 7 | `aloha-figure1.png` | Zhao, Kumar, Levine, and Finn (2023), Figure 1; cropped from PDF page 1 |
| 8 | `rs06-manual-page09.png` | Supplied RS06 revision-260713 manual, PDF page 9, printed page 8; whole-page rendering |
| 9 | `rs00-manual-page08.png` | Supplied RS00 revision-260713 manual, PDF page 8, printed page 7; whole-page rendering |
| 10 | `03-interface-components.png` | Existing course component panel; `code/lesson_figures_v08.py` |

Published filenames are relative to `2026-autumn/.gitbook/assets/class02/`. [FIGURE-CODE.md](FIGURE-CODE.md#current-lecture-figure-map) maps them to retained master files and generation functions.

The LEAP and ALOHA figure extracts omit surrounding article text and captions. Their original panel labels remain. The lecture supplies new attributed captions and does not present any paper result as a class-reproduced measurement. Copyright in source material remains with its respective authors/publishers/manufacturers; attribution is not a grant of additional reuse rights.

## Exact source inputs

Obtain source files separately from the original URLs below, using the listed local names. The complete papers are preparation inputs rather than redistributed lecture attachments. Source hashes identify the files used; publisher/project updates can change downloaded bytes.

- `robotis-position-controller.webp`: [robotis-position-controller.webp](https://docs.robotis.com/assets/images/position_controller_pid_gain-1c15742aec9fad5a25976f7a803830c9.webp); SHA-256 `02656f64db304fa8405c40a84a1cee054707703cca02824fa0f1f1e7504f39d9`.
- `robotis-current-position-controller.webp`: [robotis-current-position-controller.webp](https://docs.robotis.com/assets/images/current_position_controller_pid_gain-e8e6f02cf1c2f83282e125b62ddedb36.webp); SHA-256 `f4e04e13b5fc00caa6af9ebfaef393f064717588543d4dc2d6f0d02451da7eeb`.
- `leap-hand-2023.pdf`: [leap-hand-2023.pdf](https://arxiv.org/pdf/2309.06440); SHA-256 `ac08a57eceab8eb14aae7a322d54507567d2791f482a681b1d64bca74335d8e3`.
- `aloha-2023.pdf`: [aloha-2023.pdf](https://tonyzhaozh.github.io/aloha/aloha.pdf); SHA-256 `f949023fa5b525f8158b030f415302e892694726fba9a28a1c56f7a5ee104d0e`.

The original-brand RS manuals and STEP files are listed at [RobStride Product Information](https://github.com/RobStride/Product_Information). The class includes the exact manuals under `materials/additional_material/manuals/`. Their hashes and rendered page numbers are in `supplier/source-extraction.json`.

## Reproduce the six new source extracts

Code: `code/extract_supplier_figures.py`. Dependencies: `source/requirements-source-extraction.txt` and Poppler's `pdftoppm`. Use a separate virtual environment for authoring if these tools are not already available. No change to a teaching or training environment is required.

Prepare a writable source directory containing the four original inputs above. Create a fontconfig file with actual local font directories and a writable cache; this avoids substitution/cache errors in the PDF renderer. For example, after replacing the paths for your machine:

```xml
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>/System/Library/Fonts</dir>
  <dir>/Library/Fonts</dir>
  <cachedir>/absolute/writable/font-cache</cachedir>
</fontconfig>
```

Run from the downloaded Class 02 resource folder:

```sh
python code/extract_supplier_figures.py   --sources /absolute/path/to/original-source-files   --output /absolute/path/to/reviewed-extracts   --fontconfig /absolute/path/to/fonts.conf
```

The script reads the two class-manual PDFs, converts the two original controller images, crops the paper figures using PDF-point coordinates, and writes the PNGs plus a hash/method receipt. It writes intermediate cropped PDFs in the explicitly supplied source directory; it does not modify the original PDFs. LEAP crop coordinates from the page top are `(45, 150, 570, 365)`; ALOHA coordinates are `(46, 160.5, 568, 322)`. Paper-figure output has a 1,800-pixel longest dimension; whole manual pages use 1,600 pixels.

Source geometry, labels and colours are preserved. Do not apply new typefaces to source diagrams or describe them as newly generated MiSans illustrations. For a new authored figure, follow the course's MiSans style and retain its own generation code and data.
