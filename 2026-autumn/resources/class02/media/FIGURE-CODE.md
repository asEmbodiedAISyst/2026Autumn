# Class 02 figures and generation code

All authored labels use local MiSans. Existing outputs are supplied; no generation is required during class. Use an isolated environment for regeneration, following [RUN.md](../RUN.md).

## Hardware identity

Website Figure 1; `code/lesson_figures_v08.py`, function `hardware_identity`. Input: `media/hardware-source/xc330_photo_and_model_matched.png`. Two photo/CAD panels; only white gutters/margins removed. Geometry alone does not validate motion.

## Telemetry motion

Website Figure 2; function `telemetry_motion`. Complete `data/xc330-hardware-demo/telemetry_events.csv`: 2,601 rows, position `(raw - 2048) * 360 / 4096`, host receive-end time. Full episode and fixed 1.1–2.1 s window; original row 400 marked. No filtering or synthetic samples.

## Communication parts

Website Figure 3; function `communication_parts`. Inputs: Xc330.jpg, 3pin_cable.jpg, u2d2.jpg and powerhub.jpg under `media/hardware-source`. Crops remove table surroundings and preserve both cable ends. Exact pixel crops are documented in the function. No object retouching.

## Connection inspection

Website Figure 4; function `connection_inspection`. Full `media/hardware-source/sc330_connection.jpg`. USB lead and external power are absent; this is component inspection rather than a complete energized circuit.

## Telemetry electrical

Optional reading; function `telemetry_electrical`. Complete CSV, signed current raw × 1 mA and PWM raw × 0.113%. No torque conversion.

## Telemetry environment

Optional reading; function `telemetry_environment`. Complete CSV, voltage raw × 0.1 V and temperature already Celsius. Expanded axes are explicit. No thermal qualification claim.

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
