# Class 02 figures and generation code

All authored labels use MiSans. Retained source photographs, CAD and manufacturer graphics remain unmodified; their original typography is source evidence. Existing outputs are supplied; no generation is required during class. Use an isolated environment for regeneration, following [RUN.md](../RUN.md).

## Hardware identity

Website Figure 2; `code/lesson_figures_v08.py`, function `hardware_identity`. Input: `media/hardware-source/xc330_photo_and_model_matched.png`. Two photo/CAD panels; only white gutters/margins removed. Geometry alone does not validate motion.

## Telemetry motion

Website Figure 4; function `telemetry_motion`. Complete `data/xc330-hardware-demo/telemetry_events.csv`: 2,601 rows, position `(raw - 2048) * 360 / 4096`, host receive-end time. Full episode and fixed 1.1–2.1 s window; original row 400 marked. No filtering or synthetic samples.

## Communication parts

Website Figure 6; function `communication_parts`. Inputs: Xc330.jpg, 3pin_cable.jpg, u2d2.jpg and powerhub.jpg under `media/hardware-source`. Crops remove table surroundings and preserve both cable ends. Exact pixel crops are documented in the function. No object retouching.

## Connection inspection

Website Figure 7; function `connection_inspection`. Full `media/hardware-source/sc330_connection.jpg`. USB lead and external power are absent; this is component inspection rather than a complete energized circuit.

## Telemetry electrical

Website Figure 8 and optional reading; function `telemetry_electrical`. Complete CSV, signed current raw × 1 mA and PWM raw × 0.113%. No torque conversion.

## Telemetry environment

Website Figure 9 and optional reading; function `telemetry_environment`. Complete CSV, voltage raw × 0.1 V and temperature already Celsius. Expanded axes are explicit. No thermal qualification claim.

Run `python code/lesson_figures_v08.py classroom` or `paper` from this resource folder. Select one with `--figure telemetry-motion`. Classroom master: 11.5 inches, 17 pt; paper: 182 mm, 7 pt. Exports: PNG, embedded TrueType PDF and editable-text SVG. Fonts are explicitly registered and substitution rejected. Copy reviewed classroom PNGs to the website publication locations under `.gitbook/assets/class02/`.

## Actuator chain

Earlier optional schematic: `code/figures.py`, function `actuator_chain`. No measured values.

## Recorded step

Earlier Mode 3 example: `code/figures.py`, function `recorded_step`; original step CSVs, amplitude 30 degrees, centre 180 degrees. Its device/load differs from Mode 5 M0.

## Campaign splits

Earlier optional study: `code/campaign_figures.py`, function `matrix`; primary episode roles with diagnostics excluded. Source arrays and published results are under data/phyintel.

## Teaching figures

Earlier annotated examples: `code/teaching_figures.py`. Constructed arithmetic/mechanism sketches remain distinct from recordings; selections are specified in each function.

## Visual lessons

Earlier optional examples: `code/visual_lessons.py`. Constructed energy, saturation, sampling and error examples remain separate from measured frequency-response plots. Inputs and selections are specified in the source.

## AsBrain platform

Website Figure 1 reuses `media/hardware-source/TheAsbrainBoxFamily.png`, supplied by Mohamad Halwani. It is a CAD/source image, not a newly reconstructed physical device. No underlying CAD scene/render script was supplied with this image, so the repository preserves the exact source pixels rather than inventing a reconstruction. Publication copy: `.gitbook/assets/class02/05-asbrain-platform.png`.

## Command architecture

Website Figure 3 reuses `media/hardware-source/control_architecture.png`. Original function: `generate_control_architecture()` in `source/assistant/generate_specification_plots.py`, captured from Assistants `students` commit `f7c118edaadc9f33498669736fa9d99160ff629a`. The diagram is a functional schematic; its telemetry arrow does not locate every sensor at the transmission. There is no numerical dataset behind its boxes/arrows.

The portable adaptation is `code/assistant_figures.py`, function `architecture`. Run `python code/assistant_figures.py --figure architecture` after local MiSans setup. It uses the same box coordinates, labels and arrow construction and writes separately to `media/generated-assistant/`; it does not silently replace publication assets. Numerical package dependencies are already in requirements.txt.

## Manufacturer performance curve

Website Figure 5 preserves `media/hardware-source/XC330_preformance_graph.png`. The supplied figure corresponds to the performance graph in the [XC330-M288-T documentation](https://docs.robotis.com/docs/dxl/model_reference/x_series/xc_series/xc330-m288/). No point data or original manufacturer plotting code was supplied. Reuse the source image with attribution; do not fabricate a fitted curve or label approximate readings as new measurements. The surrounding document distinguishes gradually loaded performance testing from stall ratings. The image crop does not state every test condition.

## Raw and engineering telemetry matrix

The download `Class02-raw-and-engineering-telemetry.png` preserves the original six-by-two source image. Original function: `generate_hardware_telemetry_matrix()` in `source/assistant/generate_specification_plots.py`. It plots all 2,601 rows of the supplied Parquet record, with raw values left and engineering values right; no filtering or fitting.

Portable adaptation: `code/assistant_figures.py`, function `telemetry`. Run `python code/assistant_figures.py --figure telemetry`. It reads the audited, complete CSV instead of requiring Pandas, states the host receive-end clock explicitly and registers MiSans for tick labels as well as axis labels. Regenerated files are separate from the original source image. Use Figures 4, 8 and 9 in the lesson for larger panels; the matrix retains the original raw/decoded comparison.


## Current lecture revision 0.11

The current lesson has ten illustrations. See [SUPPLIER-SOURCES.md](SUPPLIER-SOURCES.md) for the numbering, original URLs, source hashes and reproducible extraction commands. Figures 4–9 retain original supplier/paper typography. Course-authored physical/telemetry figures use MiSans. The older figure numbers elsewhere in this historical record describe earlier revisions.
