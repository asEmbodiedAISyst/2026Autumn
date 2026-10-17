"""Rebuild the blank printable worksheets. Requires genuine MiSans Regular/Semibold.
Run: python worksheet-source/build_worksheets.py --regular FONT --semibold FONT
No student answers, interactive fields, experiments or network access.
"""
from pathlib import Path
import argparse,importlib.util,json
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4,landscape
from reportlab.pdfbase import pdfmetrics
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
p=argparse.ArgumentParser();p.add_argument('--regular',type=Path,required=True);p.add_argument('--semibold',type=Path,required=True);a=p.parse_args()
spec=importlib.util.spec_from_file_location('team',HERE/'generate_team_guide.py');t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t);m=t.m
m.setup_fonts(a.regular,a.semibold);pdfmetrics.registerFontFamily(m.REG,normal=m.REG,bold=m.BOLD,italic=m.REG,boldItalic=m.BOLD)
d=json.loads((HERE/'worksheet-content.json').read_text())
c=canvas.Canvas(str(ROOT/'Project-Worksheets.pdf'),pagesize=landscape(A4),initialFontName=m.REG);c.setTitle('Six project worksheets - definitions 1.3');c.setAuthor('ROB7103/8103 teaching team')
for ws in d['worksheets'][:5]:m.first_five(c,ws)
m.decision_front(c,d);m.decision_back(c,d);c.save();t.build_submission(ROOT/'Submission-Worksheets.pdf',d)
print('Rebuilt blank canvases, combined submission pack and six class downloads.')
