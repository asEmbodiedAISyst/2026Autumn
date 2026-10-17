# Class 03 figure reproduction

## Full notes teaching schematics

Source: [class03_figures.py](../../resources/class03/code/class03_figures.py). The shared functions generate both paper and classroom variants from deterministic declared geometry; no source photographs, datasets or simulation outputs enter these four schematics. No filtering, random sampling or manual vector edits are applied.

| Output stem | Function | Purpose and assumptions |
|---|---|---|
| body-tree | body_tree | Fixed housing, one hinge and rigidly attached payload groups; conceptual structure rather than an exact CAD projection |
| validation-chain | evidence_chain | Shared declared input/settings, physical/model outputs and implementation/physical/behavioral checks; no measured trajectories |
| geometry-roles | geometry_roles | Distinguish visual surfaces, candidate contact simplification and inertial properties; not an enabled collision model |
| printed-interface | printed_interface | Nominal bore versus an exaggerated possible as-built difference; no measured dimensions/tolerances or printing result |

Run from `2026-autumn/resources/class03` in the downloaded repository:

```sh
MPLCONFIGDIR=/tmp/class03-mpl python code/class03_figures.py --font-dir /path/to/licensed/MiSans --output-dir ../../media/class03
```

Use Matplotlib3.10.3 and NumPy2.2.6; `source/figure_typography.py` and `source/publication.mplstyle` accompany the script. Supply genuine MiSans-Regular.ttf and MiSans-Semibold.ttf; the preflight rejects substitution. Font software is not added to the public resource package. `figure-font-check.json` records the exact font hashes and resolved families.

For each stem, outputs are `-paper.png/.pdf/.svg` and `-classroom.png/.pdf/.svg`. Paper width182mm with7pt labels; classroom width11.5in with12pt labels; PNG450/180dpi respectively. PDFs embed TrueType fonts and SVGs retain editable text. Figures contain no mathematical font substitution. Expected checks: readable labels, no clipping/overlap, fixed versus moving groups consistent with one joint, declared schematic captions, and separate comparison outputs.

Generation succeeded locally. All four classroom images were visually inspected. Font preflight passed for genuine MiSans Regular/Semibold; exported font and text checks are recorded with the full-notes verification. These diagrams do not establish hardware correspondence.


## Retained source images

The six earlier PNGs remain unchanged: physical_cad_mjcf_comparison, configuration_mass_positions, digitization_workflow, fusion_acdc_workflow, frame-transform-classroom and RS06_outline_and_mounting_dimensions. Their figure-by-figure meaning and original generating source are identified on the Class03 lesson page. The original photo/screenshot composition inputs are not all bundled in this compact student package; a complete rerun of the original submission generator is not claimed.


## Model based frame and units figure

Generator: code/class03_frame_figure.py, using code/class03_frames.py and bundled consolidation/additional_material/models/1DOF-B2.xml. Run from the class folder with `python code/class03_frame_figure.py --font-dir /path/to/MiSans --model consolidation/additional_material/models/1DOF-B2.xml --output-dir media`. Requires MuJoCo3.3.7, NumPy2.2.6 and Matplotlib3.10.3. Genuine MiSans Regular/Semibold preflight uses source/figure_typography.py and source/publication.mplstyle. Fonts remain local dependencies.

Output frames-and-units-paper/classroom in PNG/PDF/SVG. Paper182mm/7pt/450dpi; classroom11.5in/12pt/180dpi; TrueTypePDF fonts and editableSVGtext. Model-derived positions at0and30degrees are projected into world x-z displacements from the joint; the table contains absolute world coordinates. No simulation trajectory, hardware measurement, image editing, filtering or random sampling. The raw 7mm axialoffset is declared. MuJoCo forward positions match Rodrigues-rotation calculations at−30,0,30,60degrees.

Visual/export/font review passed. frame-figure-check.json records model coordinates and font hashes. Source screenshots fusion-01 through fusion-07 are copied unchanged from the15October captures; source blob hashes are retained in evidence/standalone-revision.json.
