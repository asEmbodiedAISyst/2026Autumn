# Rebuild blank printable worksheets

Install requirements.txt in an isolated Python environment. Provide genuine MiSans Regular and MiSans Semibold font files, then run from the project-workbook resource folder:

```sh
python worksheet-source/build_worksheets.py --regular /path/to/MiSans-Regular.ttf --semibold /path/to/MiSans-Semibold.ttf
```

This creates Project-Worksheets.pdf (seven blank canvas pages), Submission-Worksheets.pdf (all 13 required pages) and the six ClassXX-Name.pdf downloads in this resource folder. The build has no network calls and produces no student responses. Definitions 1.2 retain the original 27 Decision questions. The layout module checks genuine font family/style and missing glyphs; no font substitution is allowed. Generation uses ReportLab and pypdf. The legacy module filename generate_team_guide.py now supplies only the evidence/review pages and pack assembly in this public bundle; no private instructor guide is needed.
