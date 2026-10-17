"""Generate the one-page Class 02 practice record with embedded MiSans.

Run from the class package: python source/generate_activity_v09.py
Authoring dependency: ReportLab. No data acquisition or hardware control.
"""
from pathlib import Path
from functools import partial
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

ROOT=Path(__file__).resolve().parents[1]
for name,filename in [("MiSans","MiSans-Regular.ttf"),("MiSans-Semibold","MiSans-Semibold.ttf")]:
    pdfmetrics.registerFont(TTFont(name,str(ROOT/"source/fonts"/filename)))
pdfmetrics.registerFontFamily("MiSans",normal="MiSans",bold="MiSans-Semibold",italic="MiSans",boldItalic="MiSans-Semibold")
BODY=ParagraphStyle("Body",fontName="MiSans",fontSize=10,leading=14,textColor=colors.HexColor("#20252b"),spaceAfter=4)
HEAD=ParagraphStyle("Head",parent=BODY,fontName="MiSans-Semibold",fontSize=11,leading=15,spaceBefore=11,spaceAfter=5)
TITLE=ParagraphStyle("Title",parent=HEAD,fontSize=20,leading=25,spaceBefore=0,spaceAfter=6)
SMALL=ParagraphStyle("Small",parent=BODY,fontSize=8.5,leading=12,textColor=colors.HexColor("#535e69"))


def p(text,style=BODY):return Paragraph(text,style)


def rule_table(rows,widths):
    table=Table([[p(str(c),BODY) for c in row] for row in rows],colWidths=widths,hAlign="LEFT")
    table.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),"MiSans"),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("BOTTOMPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),6),
        ("LINEBELOW",(0,0),(-1,-1),.4,colors.HexColor("#c9d1d9"))]))
    return table


def footer(c,doc):
    c.setFont("MiSans",8);c.setFillColor(colors.HexColor("#535e69"))
    c.drawString(17*mm,13*mm,"ROB7103/8103 | Class 02 | Practice record | Revision 0.9")
    c.drawRightString(A4[0]-17*mm,13*mm,str(doc.page))


def main():
    doc=SimpleDocTemplate(str(ROOT/"Student-Activity.pdf"),pagesize=A4,
        leftMargin=17*mm,rightMargin=17*mm,topMargin=16*mm,bottomMargin=20*mm)
    story=[p("Class 02 activity",TITLE),p("Inspect an actuator and compare exact models",HEAD),
           p("21 October 2026 | Team: ____________________",BODY),
           p("Each student inspects an unpowered XC330 and returns it. Teams use the official model documents or the lesson's attributed extract. Keep power disconnected; do not disassemble the unit or force its output.",SMALL),
           p("1. Inspect and identify",HEAD),
           p("Exact model: __________________________________________________"),
           p("Label the output, fixed mounting and two bus ports in a small sketch."),
           Spacer(1,20*mm),
           p("Which part moves relative to the housing? __________________________"),
           p("Available feedback, checked in the documentation: ___________________"),
           p("_______________________________________________________________"),
           p("2. Compare XC330-M288-T and XL330-M288-T",HEAD),
           p("Include units and conditions for numerical values. Identify the source."),
           rule_table([["Comparison","Your evidence"],
                       ["One shared property","________________________________________"],
                       ["Construction or mass","________________________________________"],
                       ["Torque or speed","________________________________________"],
                       ["Source / section","________________________________________"]],[48*mm,128*mm]),
           p("An intended use and the property that matters: ______________________"),
           p("_______________________________________________________________"),
           p("Can stall torque and no-load speed occur together? Why? _____________"),
           p("_______________________________________________________________"),
           p("Does encoder resolution establish accuracy? Explain. _________________"),
           p("_______________________________________________________________"),
           p("3. Record and return",HEAD),
           p("All units returned: __________  Team comparison and labels recorded: ______"),
           Spacer(1,4*mm),
           p("No powered student operation, software installation or telemetry calculation is required. Optional follow-up: locate three research examples using XC330/XL330; record the exact model and role, or mark the exact model unverified.",SMALL)]
    doc.build(story,onFirstPage=footer,onLaterPages=footer,
              canvasmaker=partial(canvas.Canvas,initialFontName="MiSans"))
    print("Generated outline-aligned Student-Activity.pdf with MiSans")

if __name__=="__main__":main()
