"""Generate six course canvases and two schematic figures using genuine MiSans.

All diagrams are schematic: this program runs no robot, simulation or training.
See ../FIGURE-CODE.md for input/output mapping and isolated-environment commands.
"""
import argparse, hashlib, json, subprocess, textwrap
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.colors import HexColor, white
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.graphics import renderPDF, renderSVG
from PIL import Image, ImageOps

MEDIA=Path(__file__).resolve().parents[1]
BLUE='#245C8A'; TEAL='#007C78'; INK='#17252D'; PALE='#F0F5F7'; GRAY='#566770'
REG='MiSans-Regular'; BOLD='MiSans-Semibold'
AUDIT=[]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def setup_fonts(regular,semibold):
 for name,p in [(REG,regular),(BOLD,semibold)]:
  f=TTFont(name,str(p));family=f.face.familyName.decode('utf-8','replace');style=f.face.styleName.decode('utf-8','replace')
  if 'MiSans' not in family:raise ValueError(f'Refusing font substitution: {family}')
  expected='regular' if name==REG else 'semibold'
  if style.lower()!=expected:raise ValueError(f'Required MiSans {expected}, received {style}')
  pdfmetrics.registerFont(f)
  AUDIT.append({'font':name,'family':family,'style':style,'filename':p.name,'sha256':sha(p)})
 # Eliminate the graphics renderer's Times default, including unused PDF resources.
 from reportlab.graphics import shapes
 shapes.STATE_DEFAULTS['fontName']=REG
 shapes.STATE_DEFAULTS['fontSize']=7

def line(c,x,y,s,size=10,bold=False,color=INK):
 name=BOLD if bold else REG
 chars=pdfmetrics.getFont(name).face.charWidths
 missing=[a for a in s if not a.isspace() and ord(a) not in chars]
 if missing:raise ValueError(f'Missing MiSans glyphs: {missing}')
 c.setFillColor(HexColor(color));c.setFont(name,size);c.drawString(x,y,s)

def wrap(s,width,size,font=REG):
 lines=[];current=''
 for word in s.split():
  candidate=(current+' '+word).strip()
  if pdfmetrics.stringWidth(candidate,font,size)>width and current:
   lines.append(current);current=word
  else:current=candidate
 if current:lines.append(current)
 return lines

def paragraph(c,x,y,s,width,size=10,leading=14,bold=False):
 for t in wrap(s,width,size,BOLD if bold else REG):
  line(c,x,y,t,size,bold);y-=leading
 return y

def rect(c,x,y,w,h,fill=False):
 c.setStrokeColor(HexColor('#BCCAD0'));c.setLineWidth(.6)
 c.setFillColor(HexColor(PALE) if fill else white);c.rect(x,y,w,h,stroke=1,fill=1)

def arrow(c,x1,y1,x2,y2):
 c.setStrokeColor(HexColor(BLUE));c.setLineWidth(.8);c.line(x1,y1,x2,y2)
 import math
 a=math.atan2(y2-y1,x2-x1)
 for d in (-.55,.55):c.line(x2,y2,x2-5*math.cos(a+d),y2-5*math.sin(a+d))

def header(c,w,h,title,question,page):
 line(c,26,h-33,title,21,True,BLUE)
 paragraph(c,26,h-54,question,w-52,11,15)
 line(c,26,h-82,'Mode: Source analysis / Project development   Claim: __________   Source/configuration freeze: __________   Date: __________',9)
 c.setStrokeColor(HexColor(BLUE));c.line(26,h-94,w-26,h-94)
 line(c,26,18,'Record source + origin + context; separate support and access limits. Use this class reading for support/context rules.',8.5,color=GRAY)
 line(c,w-70,18,f'v1.2 / {page}',8.5,color=GRAY)

def box(c,x,y,w,h,title,help):
 rect(c,x,y,w,h)
 line(c,x+12,y+h-22,title,11,True)
 yy=paragraph(c,x+12,y+h-40,help,w-24,9.5,13)
 if yy<y+40:raise ValueError('Instruction text leaves insufficient writing room: '+title)
 c.setStrokeColor(HexColor('#D8E1E5'));c.setLineWidth(.4)
 for ly in [y+24,y+46]:c.line(x+12,ly,x+w-12,ly)

def schematic_band(c,w,y,kind):
 if kind=='Learning':
  # Both methods enter the same evaluation; the candidate is not downstream of the baseline.
  bw=(w-80)/3
  for title,xx,yy in [('Baseline',26,y+22),('Frozen candidate',26,y-4),('Same held-out evaluation',42+bw,y+4),('Failures / decision',58+2*bw,y+4)]:
   rect(c,xx,yy,bw,24,True);line(c,xx+8,yy+8,title,9,True)
  arrow(c,26+bw,y+34,42+bw,y+20);arrow(c,26+bw,y+8,42+bw,y+16)
  arrow(c,42+2*bw,y+16,58+2*bw,y+16)
  return y-34
 if kind=='Experience':
  labels=['Objective','Start','Input','Action','Response','Outcome','Record / reuse']
 elif kind=='System':labels=['World / body','Observe','Compute / decide','Admit / action','World response']
 else:labels=['Baseline','Frozen candidate','Held-out trials','Failures / decision']
 gap=14;n=len(labels);bw=(w-52-gap*(n-1))/n
 for i,label in enumerate(labels):
  x=26+i*(bw+gap);rect(c,x,y,bw,42,True)
  paragraph(c,x+8,y+27,label,bw-16,9,11,True)
  if i<n-1:arrow(c,x+bw,y+21,x+bw+gap,y+21)
 if kind=='System':
  arrow(c,w-26,y-8,26,y-8)
  line(c,26,y-24,'Feedback, operator enable/stop/recovery and evidence recording cross the loop.',9)
 return y-34

def first_five(c,ws):
 w,h=landscape(A4);c.setPageSize((w,h))
 header(c,w,h,f"{ws['number']:02d} / {ws['name']}",ws['question'],ws['number'])
 top=h-115
 if ws['name'] in ['Experience','System','Learning']:
  top=schematic_band(c,w,top-42,ws['name'])
 elif ws['name']=='Claim':
  rect(c,26,top-52,w-52,52,True)
  paragraph(c,38,top-20,ws['prompt'],w-76,11,15)
  top-=68
 else:
  columns=['Prediction / representation','Matched reference','Difference / ambiguity','Conclusion / scope limit']
  bw=(w-52)/4
  for i,label in enumerate(columns):
   x=26+i*bw;rect(c,x,top-58,bw,58,True)
   line(c,x+8,top-18,label,9,True)
   c.setStrokeColor(HexColor('#BCCAD0'));c.line(x+8,top-42,x+bw-8,top-42)
  top-=74
 bottom=82;gap=12;bw=(w-52-gap)/2;bh=(top-bottom-gap)/2
 for i,(title,help) in enumerate(ws['fields']):
  x=26+(i%2)*(bw+gap);y=top-(i//2+1)*bh-(i//2)*gap
  box(c,x,y,bw,bh,title,help)
 paragraph(c,26,61,'Review: '+ws['challenge'],w-52,9,12)
 c.showPage()

def decision_front(c,data):
 w,h=landscape(A3);c.setPageSize((w,h))
 header(c,w,h,'06 / Decision - full 1-3-9-27 screen','What bounded conclusion or next action does the evidence justify?',6)
 line(c,26,h-117,'Mode / claim or next action: ________________________  Source/configuration freeze: __________________  Scope: __________________',10)
 gap=16;bw=(w-52-2*gap)/3;top=h-148;bh=155
 for col,(branch,title) in enumerate([('G','Generate grounded experience'),('U','Use experience for claims'),('M','Manage evidence through lifecycle')]):
  x=26+col*(bw+gap);line(c,x,top,title,13,True,BLUE)
  for row,g in enumerate(data['gates'][col*3:col*3+3]):
   y=top-18-(row+1)*bh-row*10;rect(c,x,y,bw,bh)
   line(c,x+10,y+bh-21,g['id']+' / '+g['name'],11,True)
   yy=y+bh-40
   for cid,label,q in g['checks']:
    yy=paragraph(c,x+10,yy,cid+' '+label+': '+q,bw-20,9.5,12.5)-7
   if yy<y+5:raise ValueError('Decision hierarchy overflow '+g['id'])
 line(c,26,144,'Support (strength for the bounded question)',10,True)
 paragraph(c,26,127,'0 contradicted; 1 weak; 2 partial; 3 adequate within scope; 4 convergent. NR not reported in inspected scope; NE not examined; NA not applicable with a reason.',w-52,9.5,13)
 line(c,26,91,'Evidence context (separate from origin, support and access)',10,True)
 paragraph(c,26,74,'E1 reasoning/design/plan; E2 executed analysis/simulation/digital artifact; E3 physical/integrated experiments, including externally reported results; E4 specified physical coverage/auditability; E5 independent reproduction/sustained operation within scope. Not a universal quality ladder. NR/NE/NA: context normally a dash.',w-52,9.5,13)
 c.showPage()

def decision_back(c,data):
 w,h=landscape(A3);c.setPageSize((w,h))
 header(c,w,h,'06 / Decision - evidence and action record','Cite source evidence; state findings and limits. Apply action gates only to project development.',7)
 line(c,26,h-116,'Mode / claim or next action / source scope: ______________________________________________________________________________',10)
 gap=16;bw=(w-52-2*gap)/3;top=h-132;bh=144
 for i,g in enumerate(data['gates']):
  x=26+(i%3)*(bw+gap);y=top-(i//3+1)*bh-(i//3)*10
  rect(c,x,y,bw,bh);line(c,x+9,y+bh-18,g['id']+' / '+g['name'],10.5,True)
  yy=y+bh-38
  line(c,x+9,yy,'Check',9,True);line(c,x+65,yy,'Evidence ID + basis',9,True)
  line(c,x+bw-104,yy,'Support',9,True);line(c,x+bw-48,yy,'Context',9,True)
  for cid,_,_ in g['checks']:
   yy-=22;line(c,x+9,yy,cid,9)
   c.setStrokeColor(HexColor('#BCCAD0'));c.setLineWidth(.4);c.line(x+65,yy-3,x+bw-8,yy-3)
  for xx in [x+55,x+bw-111,x+bw-54]:c.line(xx,y+43,xx,y+bh-43)
  line(c,x+9,y+21,'State: __________  Gap/NA rationale: __________________',9)
  line(c,x+9,y+7,'Action / owner / verification: _________________________',9)
 y=221
 line(c,26,y,'Choose the conclusion for the declared mode',11,True,BLUE)
 y=paragraph(c,26,y-18,'Source analysis: summarize supported contributions, partial support, contradictions and unresolved questions by claim family. Distinguish claim-critical checks from extension inquiries. Reporting gaps do not automatically invalidate the contribution. No whole-paper average or readiness award.',w-52,9.5,13)
 y=paragraph(c,26,y-10,'Project development only: identify critical checks and requirements for the next action. Green: adequate support, no blocking unknown. Amber: manageable condition. Red: essential condition absent or contradicted. NR/NE cannot satisfy a dependent critical requirement.',w-52,9.5,13)
 line(c,26,y-12,'Bounded conclusion / unsupported uses: ___________________________________________________________________________________',10)
 line(c,26,y-36,'Follow-up inquiry or conditions / owner / verification: ______________________________________________________________________',10)
 line(c,26,y-60,'Reassessment trigger / invalidated evidence / version: _____________________________________________________________________',10)
 line(c,26,39,'Retain all 27 checks, evidence bases and limitations. Do not turn missing reporting into contradiction or a favorable mean into approval.',9)
 c.showPage()

def drawing_text(d,x,y,s,size=7,bold=False):
 name=BOLD if bold else REG
 missing=[a for a in s if not a.isspace() and ord(a) not in pdfmetrics.getFont(name).face.charWidths]
 if missing:raise ValueError(f'Missing schematic glyphs: {missing}')
 d.add(String(x,y,s,fontName=BOLD if bold else REG,fontSize=size,fillColor=HexColor(INK)))

def drawing_arrow(d,x1,y1,x2,y2):
 d.add(Line(x1,y1,x2,y2,strokeColor=HexColor(BLUE),strokeWidth=.8))
 d.add(Polygon([x2,y2,x2-4,y2+2,x2-4,y2-2],fillColor=HexColor(BLUE),strokeColor=HexColor(BLUE)))

def project_progression():
 d=Drawing(182/25.4*72,175);width=d.width
 names=['Claim','Experience','System','Grounding','Learning','Decision']
 verbs=['Define a test','Record an episode','Verify an interface','Compare evidence','Evaluate a method','Bound the conclusion']
 margin=6;gap=8;bw=(width-2*margin-5*gap)/6
 for i,(name,verb) in enumerate(zip(names,verbs)):
  x=margin+i*(bw+gap)
  d.add(Rect(x,90,bw,62,fillColor=HexColor(PALE),strokeColor=HexColor(BLUE),strokeWidth=.6))
  drawing_text(d,x+6,135,str(i+12),7,bold=True)
  drawing_text(d,x+6,118,name,7,bold=True)
  for j,t in enumerate(wrap(verb,bw-12,7)):drawing_text(d,x+6,104-j*9,t,7)
  if i<5:drawing_arrow(d,x+bw,121,x+bw+gap,121)
 d.add(Line(width-15,78,15,78,strokeColor=HexColor(TEAL),strokeWidth=.8))
 d.add(Polygon([15,78,19,80,19,76],fillColor=HexColor(TEAL),strokeColor=HexColor(TEAL)))
 drawing_text(d,100,62,'Later evidence can revise any earlier view',7)
 drawing_text(d,6,35,'One project record + configuration + evidence index + milestone commits',7,bold=True)
 drawing_text(d,6,19,'Schematic review sequence; no experiment results or guaranteed progression.',7)
 return d

def evidence_handoff():
 d=Drawing(182/25.4*72,175)
 names=['Interaction','Record','Interpretation','Comparison','Next action']
 sub=['What happened?','What was retained?','What could it mean?','What supports it?','What should change?']
 gap=12;bw=(d.width-12-4*gap)/5
 for i,(name,small) in enumerate(zip(names,sub)):
  x=6+i*(bw+gap);d.add(Rect(x,85,bw,60,fillColor=HexColor(PALE),strokeColor=HexColor(BLUE),strokeWidth=.6))
  drawing_text(d,x+5,127,name,7,bold=True)
  for j,t in enumerate(wrap(small,bw-10,7)):drawing_text(d,x+5,110-j*9,t,7)
  if i<4:drawing_arrow(d,x+bw,115,x+bw+gap,115)
 drawing_text(d,6,61,'Source and configuration IDs connect every view; support must be assessed separately.',7)
 drawing_text(d,6,40,'Keep planned, simulated, physically measured and externally reported origins explicit.',7)
 drawing_text(d,6,20,'Schematic relationships; a clear record does not establish a demonstrated capability.',7)
 return d

def figure_export(d,name):
 target=MEDIA/'figures';target.mkdir(parents=True,exist_ok=True)
 path=target/(name+'.pdf');c=canvas.Canvas(str(path),pagesize=(d.width,d.height),initialFontName=REG)
 renderPDF.draw(d,c,0,0);c.showPage();c.save()
 renderSVG.drawToFile(d,str(target/(name+'.svg')))
 # reportlab internal font registration names are not public SVG family names.
 svg=target/(name+'.svg');s=svg.read_text().replace('font-family: MiSans-Regular','font-family: MiSans; font-weight: 400').replace('font-family: MiSans-Semibold','font-family: MiSans; font-weight: 600')
 svg.write_text(s)
 subprocess.run(['pdftoppm','-singlefile','-r','450','-png',str(path),str(target/name)],check=True,capture_output=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('--regular',type=Path,required=True);p.add_argument('--semibold',type=Path,required=True)
 a=p.parse_args();setup_fonts(a.regular,a.semibold)
 data=json.loads((MEDIA/'source/worksheet-content.json').read_text())
 target=MEDIA.parent/'worksheets';target.mkdir(parents=True,exist_ok=True)
 pdf=target/'Project-Worksheets.pdf';c=canvas.Canvas(str(pdf),pagesize=landscape(A4),initialFontName=REG)
 c.setTitle('Embodied AI Systems - six project worksheets');c.setAuthor('ROB7103/8103 teaching team')
 for ws in data['worksheets'][:5]:first_five(c,ws)
 decision_front(c,data);decision_back(c,data);c.save()
 for name,fn in [('project-progression',project_progression),('evidence-handoff',evidence_handoff)]:figure_export(fn(),name)
 preview=MEDIA/'previews';preview.mkdir(exist_ok=True)
 subprocess.run(['pdftoppm','-r','110','-png',str(pdf),str(preview/'worksheet')],check=True,capture_output=True)
 imgs=[]
 for i,png in enumerate([preview/f'worksheet-{k}.png' for k in range(1,8)],1):
  im=Image.open(png).convert('RGB');im=ImageOps.contain(im,(1000,730));imgs.append(im)
 sheet=Image.new('RGB',(2020,4*750),'#E6ECEF')
 for i,im in enumerate(imgs):sheet.paste(im,((i%2)*1010+(1000-im.width)//2,(i//2)*750+(730-im.height)//2))
 sheet.save(preview/'worksheet-overview.png')
 outputs=[pdf]+list((MEDIA/'figures').glob('*'))
 receipt={'version':data['version'],'reportlab':__import__('reportlab').Version,'fonts':AUDIT,'content_sha256':sha(MEDIA/'source/worksheet-content.json'),'source_sha256':sha(Path(__file__)),'kind':'newly authored blank canvases and schematic diagrams; no empirical data','outputs':{str(x.relative_to(MEDIA.parent)):sha(x) for x in outputs}}
 (MEDIA/'generation-provenance.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print('Generated seven mixed-size worksheet pages and two schematic PNG/PDF/SVG sets using MiSans.')

if __name__=='__main__':main()
