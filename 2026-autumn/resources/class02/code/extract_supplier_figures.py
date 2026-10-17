"""Reproduce source illustrations without changing source labels.
Requires pypdf, Pillow and pdftoppm; reads the supplied original images and PDFs.
Run in a Python environment with source/requirements-source-extraction.txt. This extracts source material, not new authored figures.
"""
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from PIL import Image
import subprocess, hashlib, json, os
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sources',type=Path,required=True,help='Directory containing the original ROBOTIS controller images and LEAP/ALOHA paper PDFs')
parser.add_argument('--output',type=Path,required=True,help='Destination for extracted PNGs and receipt')
parser.add_argument('--fontconfig',type=Path,required=True,help='A valid writable-cache fontconfig configuration for pdftoppm')
args=parser.parse_args()
W=Path(__file__).resolve().parents[1]
S=args.sources.resolve(); O=args.output.resolve()
O.mkdir(parents=True,exist_ok=True)
items=[]
def record(source,output,method):
 items.append({'source':str(source.name), 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(), 'output':str(output.name), 'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'method':method,'typography':'Original source typography retained; no authored replacement labels.'})
for stem in ['robotis-position-controller','robotis-current-position-controller']:
 src=S/(stem+'.webp');dst=O/(stem+'.png')
 Image.open(src).convert('RGB').save(dst)
 record(src,dst,'Lossless PNG export from downloaded original; pixel content unchanged.')
# Rectangles are PDF points: left, top, right, bottom measured from page top.
for srcname,name,rect in [('leap-hand-2023.pdf','leap-hand-figure1',(45,150,570,365)),('aloha-2023.pdf','aloha-figure1',(46,160.5,568,322))]:
 src=S/srcname;page=PdfReader(src).pages[0];h=float(page.mediabox.height)
 l,t,r,b=rect;page.cropbox.lower_left=(l,h-b);page.cropbox.upper_right=(r,h-t)
 writer=PdfWriter();writer.add_page(page);crop=S/(name+'-crop.pdf')
 with crop.open('wb') as f:writer.write(f)
 env=os.environ.copy();env['FONTCONFIG_FILE']=str(args.fontconfig.resolve())
 subprocess.run(['pdftoppm','-cropbox','-scale-to','1800','-png','-singlefile',str(crop),str(O/name)],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 record(src,O/(name+'.png'),{'pdf_page':1,'crop_points_from_top':rect,'renderer':'pdftoppm -cropbox -scale-to 1800 -png -singlefile'})
# Already rendered supplier-document examples; reproduce from the canonical source PDFs.
base=W/'materials/additional_material/manuals'
for fn,page,name in [('RobStride_RS06_User_Manual_260713.pdf',9,'rs06-manual-page09'),('RobStride_RS00_User_Manual_260713.pdf',8,'rs00-manual-page08')]:
 src=base/fn;env=os.environ.copy();env['FONTCONFIG_FILE']=str(args.fontconfig.resolve())
 subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-scale-to','1600','-png','-singlefile',str(src),str(O/name)],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 items.append({'source':'materials/additional_material/manuals/'+fn,'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output':'media/supplier/'+name+'.png','output_sha256':hashlib.sha256((O/(name+'.png')).read_bytes()).hexdigest(),'method':{'pdf_page':page,'renderer':'pdftoppm -scale-to 1600 -png -singlefile'},'typography':'Original manufacturer typography.'})
(O/'source-extraction.json').write_text(json.dumps(items,indent=2)+'\n')
print('Verified source illustrations:',len(items))
