"""Build the student advance-reading guide and linked handwritten submission pack.

Sources: the Markdown guide, worksheet-content.json, existing blank canvases and
existing documented schematic PNGs. Runs no experiment, model training or web call.
"""
from pathlib import Path
import argparse,hashlib,html,io,json,re,importlib.util,subprocess
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,XPreformatted,KeepTogether,PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor,white
from reportlab.lib.pagesizes import A4,landscape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from pypdf import PdfReader,PdfWriter
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('layout',ROOT/'worksheet-source/generate_workbook.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
REG=m.REG;BOLD=m.BOLD;WIDTH=A4[0]-80

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def inline(text):
 text=html.escape(text.replace('–','-').replace('—','-'))
 text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<link href="\2" color="#245C8A">\1</link>',text)
 text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
 text=re.sub(r'`([^`]+)`',r'<font name="MiSans-Regular">\1</font>',text)
 return text
class MiSansCanvas(canvas.Canvas):
 def __init__(self,*a,**kw):kw['initialFontName']=REG;super().__init__(*a,**kw)
def footer(c,doc):
 c.saveState();c.setStrokeColor(HexColor('#BCCAD0'));c.setLineWidth(.5);c.line(40,39,A4[0]-40,39)
 m.line(c,40,25,'ROB7103/8103 | Student team advance guide | v1.1',8,color=m.GRAY);m.line(c,A4[0]-78,25,str(doc.page),8,color=m.GRAY);c.restoreState()

def review_page(ws):
 buf=io.BytesIO();w,h=landscape(A4);c=canvas.Canvas(buf,pagesize=(w,h),initialFontName=REG);c.setTitle('Worksheet '+str(ws['number'])+' - evidence and team review');c.setAuthor('ROB7103/8103 teaching team')
 m.line(c,26,h-34,f"Worksheet {ws['number']} / {ws['name']} - evidence and team review",20,True,m.BLUE)
 m.line(c,26,h-57,f"Class {ws['class']} | Due {ws['date']} before {ws['time'].split('–')[-1]} | Include every canvas and review page",9.3,color=m.GRAY)
 m.line(c,26,h-82,'Team / project: ______________________________  Claim ID: __________  Worksheet revision: __________',10)
 m.line(c,26,h-105,'Date: ______________  Mode: Project development (label source analysis separately)   Pages / IDs: ______________',9.5)
 m.line(c,26,h-127,'Configuration / evidence version (an earlier commit or artifact ID): _____________________________________________',9.5)
 top=h-147;xs=[26,94,374,w-26];m.line(c,26,top,'Evidence ID',9,True);m.line(c,94,top,'Repo-relative path + evidence ID',9,True);m.line(c,374,top,'Origin; what it supports; limitation / access gap',9,True)
 c.setStrokeColor(HexColor('#BCCAD0'));c.setLineWidth(.5)
 for k in range(1,4):
  y=top-9-k*29;c.line(26,y,w-26,y)
 m.line(c,26,333,'Missing evidence or next action / owner / verification:',9.5,True);c.line(26,312,w-26,312)
 m.paragraph(c,26,292,'Each member signs after reviewing the reasoning, evidence labels, limitations and next action. Signatures apply to all identified pages; they do not certify success or readiness. Do not sign for another member.',w-52,9,12)
 gap=16;bw=(w-52-gap)/2;top=250;bh=47
 for k in range(8):
  x=26+(k%2)*(bw+gap);y=top-(k//2+1)*bh
  m.line(c,x,y+29,f'{k+1}. Name / student ID: ___________________________________',9)
  m.line(c,x,y+8,'Signature: _______________________  Date: ______________',9)
 m.paragraph(c,26,45,f"Push one legible complete PDF to {ws['submission_path']} in your assigned private team repository by the deadline. TA collects this file; no physical hand-in. Include identified continuations; keep later revisions separate.",w-52,8,10)
 m.line(c,26,17,'ROB7103/8103 | Handwritten checkpoint submission | Guide v1.1 / worksheet definitions v1.2',8,color=m.GRAY);c.showPage();c.save();return PdfReader(buf).pages[0]

def build_submission(path,data):
 reader=PdfReader(ROOT/'Project-Worksheets.pdf');writer=PdfWriter()
 for i,ws in enumerate(data['worksheets']):
  if i<5:writer.add_page(reader.pages[i])
  else:writer.add_page(reader.pages[5]);writer.add_page(reader.pages[6])
  writer.add_page(review_page(ws))
 writer.add_metadata({'/Title':'Six handwritten worksheet submissions with team evidence and signatures','/Author':'ROB7103/8103 teaching team'});writer.write(path)
 # Per-class downloads retain every page and the original A4/A3 sizes.
 for i,ws in enumerate(data['worksheets']):
  start=2*i; stop=start+(3 if i==5 else 2); part=PdfWriter()
  for page in writer.pages[start:stop]:part.add_page(page)
  part.add_metadata({'/Title':f"Class {ws['class']} - {ws['name']} submission worksheet",'/Author':'ROB7103/8103 teaching team'})
  part.write(path.parent/f"Class{ws['class']}-{ws['name']}.pdf")

