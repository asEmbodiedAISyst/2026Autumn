# Six-face ArUco cube tracker

This is a separate D455 project for tracking cube face identity and pose. It
uses six unique `DICT_4X4_50` markers, one centered on each face. A single fully
visible marker is enough to recover the complete cube pose; two or more visible
markers are combined in one multi-face pose refinement.

## How many markers?

- **One marker** is the mathematical minimum, but tracking disappears whenever
  that particular face turns away or is covered.
- **Five markers** can work if one face is permanently unavailable as the bottom.
- **Six markers are recommended** for a cube manipulated by the LEAP hand. The
  redundancy is valuable when fingers cover one or two faces.

A marker must be detected as a complete square. A partially covered marker is
normally rejected, but another visible face marker can maintain the cube pose.

## 1. Measure and configure

Measure the real cube edge and choose a black marker-square size that leaves a
clean white margin. The current values are based on the observed cube:

```json
"cube_size_m": 0.062,
"marker_size_m": 0.032
```

Edit [cube_config.json](cube_config.json) if either measurement differs. Pose
scale is directly proportional to the printed black-square measurement, so do
not guess it.

## 2. Generate and print

From this folder:

```bash
../.venv/bin/python generate_markers.py
```

Print [markers/aruco_cube_sheet_A4.svg](markers/aruco_cube_sheet_A4.svg) with:

- paper size A4;
- scale **100% / Actual Size**;
- **Fit to Page disabled**;
- high-quality black ink or toner.

Measure the black square after printing. It must be exactly the configured
`marker_size_m` (currently 32.0 mm). Keep a white border around every marker.
Before separating the labels, mark each cutout's ID and top edge on its back.

## Embedded 3D-printable version

Generate the models with:

```bash
../.venv/bin/python -m pip install -r requirements_mesh.txt
../.venv/bin/python generate_stl_cube.py
```

The ready-made 62 mm cube files are in `stl/`:

- `cube_62mm_aruco32mm_recessed_paint.stl`: one-material white cube with
  0.8 mm-deep black-cell recesses. Print it white and fill only the recesses
  with matte-black acrylic paint or a paint pen.
- `cube_62mm_aruco32mm_body_white.stl` and
  `cube_62mm_aruco32mm_inlays_black.stl`: aligned complementary parts for a
  dual-material printer. Import both without moving or auto-arranging them,
  combine them as one multipart object, and assign white/black materials.
- `cube_62mm_aruco32mm_preview.glb`: colorized inspection model; do not slice
  this instead of the STLs.

STL files do not contain color information. A one-piece single-color print is
not camera-detectable until the recessed cells are painted black. Use matte
white and matte black; glossy surfaces create thresholding glare.

Suggested starting slicer settings are 0.20 mm layers, three walls, and 8–12%
infill to keep the cube light enough for the LEAP hand. Keep model scale at
100%; the cube must remain 62 mm and the marker boundary 32 mm. The geometry is
watertight and expressed in millimeters.

## 3. Define and label the cube axes

Choose one physical face as `+Z`. Looking straight at that face with marker 0
upright, marker right is cube `+X` and marker top is cube `+Y`. Opposite faces
are `-X`, `-Y`, and `-Z`.

Attach every marker centered and flat:

| ID | Cube face | Marker top (`+Y`) points toward |
|---:|:---:|:---|
| 0 | `+Z` | cube `+Y` |
| 1 | `+X` | cube `+Z` |
| 2 | `+Y` | cube `+Z` |
| 3 | `-X` | cube `+Z` |
| 4 | `-Y` | cube `+Z` |
| 5 | `-Z` | cube `+Y` |

The orientation is essential. Rotating one sticker by 90 degrees makes poses
from that face disagree with the rest of the cube.

## 4. Calibrate physical up once

The D455 camera is tilted, so camera-image up is not the same as gravity up.
With the camera fixed, place the cube so face `+Z` is physically upward and run:

```bash
../.venv/bin/python track_cube_faces.py \
  --calibrate-up \
  --calibration-face +Z
```

Hold the cube still until 60 valid samples are collected. This creates
`up_calibration.json`. Recalibrate whenever the camera mount moves.

## 5. Track and record

```bash
../.venv/bin/python track_cube_faces.py \
  --jsonl captures/cube_faces.jsonl
```

The tracker defaults to the verified D455 profile `1280x720 @ 15 FPS`. This is
important for the smaller 32 mm tags: at the current distance they are roughly
38 pixels wide. Press `Q` or Escape to exit. Detection is restricted to the
current LEAP-hand region `(450, 280, 340, 300)`. Override it after moving the
camera or hand:

```bash
../.venv/bin/python track_cube_faces.py --roi X Y WIDTH HEIGHT
```

For the D455 at the current hand distance, returning to 640x480 makes the
32 mm marker too marginal; use a larger marker (about 40 mm) in that specific
setup. The iPhone section below has a different field of view and tests its
working distance directly.

Each JSON record contains:

- `cube_center_m`, quaternion, and rotation matrix in the color optical frame;
- `visible_marker_ids` and `visible_faces` measured in that image;
- `up_face`, using the saved physical-up calibration;
- `camera_facing_face`;
- all six face centers, outward normals, and up-alignment scores;
- pixel reprojection error for measurement quality.

The RealSense optical frame is `+X` right, `+Y` down, `+Z` forward.

## Headless test and output preview

```bash
../.venv/bin/python track_cube_faces.py \
  --headless --frames 120 --print-every 15 \
  --save-preview captures/face_tracking_preview.png
```

## iPhone/asMagic tracking and nearest-distance measurement

The pose-estimation core also works with the standalone asMagic iOS stream. The
adapter in [track_cube_faces_asmagic.py](track_cube_faces_asmagic.py) receives
the JPEG RGB image and per-frame camera intrinsics from the phone; it does not
use the RealSense camera or the D455-specific ROI.

Install the additional receiver dependency in the existing environment:

```bash
../.venv/bin/python -m pip install -r requirements_asmagic.txt
```

Connect the iPhone and workstation to the same private network. For example,
leave the workstation on Ethernet, create a workstation Wi-Fi hotspot, join the
iPhone to it, then enable **Panel** -> **Tools** -> **Data Streaming** ->
**AR Data** in asMagic. Keep the iPhone in landscape orientation, the app
foregrounded, and the screen unlocked.

Start the tracker with the current IP shown by asMagic. The address below is
only the last observed example; replace it if DHCP assigned a new address:

```bash
../.venv/bin/python track_cube_faces_asmagic.py \
  --iphone-ip 10.42.0.235 \
  --jsonl captures/iphone_cube_range.jsonl \
  --save-preview captures/iphone_cube_range_preview.png \
  --verbose
```

The preview reports:

- camera-optical-center to cube-center distance;
- model-based distance from the optical center to the estimated 62 mm cube
  surface;
- detected marker IDs and mean marker edge length in pixels;
- reprojection RMS error;
- timed-hold duration, sample count, detection percentage, and distance spread;
  and
- the closest stationary surface distance. A hold is accepted only when it
  spans at least 2 seconds and 30 samples, has at least 95% valid poses, contains
  no gap over 0.25 seconds, has range MAD at most 0.2 cm, and has 5th-to-95th
  percentile range spread at most 0.8 cm.

Press `Q` or Escape to finish. Use `--headless --duration SECONDS` for a timed
non-GUI trial. The JSONL includes valid and marker-rejected decoded RGB frames,
plus the stability diagnostics, so the detection rate can be audited.

For the configured 62 mm cube and the most restrictive intrinsics in the
captured iPhone stream, the centered ideal-pinhole crop limits are about 9.2 cm
from camera optical center to cube center for a frontal cube and 11.9 cm to
contain a centered cube at any orientation. Those are geometric crop limits,
not usable working-distance guarantees: autofocus, blur, glare, fingers,
marker quiet-zone visibility, lens distortion, and physical cube tolerances are
not represented.

Start around **18–20 cm from camera optical center to cube center** (roughly
15–17 cm to a frontal surface), hold still for 3–5 seconds, and move inward in
1 cm steps. A ruler measured from the phone's camera cover approximates the
optical-center distance but can differ by a few millimetres. Use the closest
stationary value printed by the tracker, verify it once with a ruler, and then
operate at least `max(2 cm, 10%)` farther away.

The adapter uses every frame's intrinsics because the iPhone focal values can
change and rejects a portrait/auto-rotated stream whose aspect ratio does not
match asMagic's 1920x1440 intrinsics reference. asMagic does not provide
distortion coefficients, so the adapter uses zeros and the cube should remain
near image center. The reported cube pose is in
the OpenCV color optical frame (`+X` right, `+Y` down, `+Z` forward); it is not
yet composed with asMagic's AR world pose. Depth is not used because
depth-to-color registration is not documented.

## Offline verification

```bash
../.venv/bin/python -m unittest -v \
  test_aruco_cube.py test_track_cube_faces_asmagic.py
```

## Occlusion limits

Six markers provide face redundancy, not X-ray vision. Making a tag smaller
reduces its overlap with a finger, but it also reduces the number of camera
pixels available to decode it. A partially covered tag generally cannot provide
a precision pose. The tracker works while at least one complete marker is
visible. If every marker is covered, prediction or a second camera must bridge
that interval.
