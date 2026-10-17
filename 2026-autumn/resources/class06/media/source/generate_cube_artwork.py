"""Generate distributable cube-face artwork in MiSans, without bundling font software."""
import argparse,hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
MEDIA=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--font',type=Path,required=True);args=p.parse_args()
 font=ImageFont.truetype(str(args.font),164)
 if font.getname()[0]!='MiSans':raise RuntimeError('MiSans required')
 out=MEDIA.parent/'code/assets/letters';out.mkdir(parents=True,exist_ok=True)
 colors={'M':'#dbeafe','B':'#fde68a','Z':'#d1fae5','U':'#fbcfe8','A':'#fed7aa','I':'#ddd6fe'}
 for letter,color in colors.items():
  im=Image.new('RGB',(256,256),color);draw=ImageDraw.Draw(im);draw.rectangle((4,4,251,251),outline='#172033',width=8);draw.text((128,128),letter,anchor='mm',font=font,fill='#172033');im.save(out/f'{letter}.png')
 (MEDIA/'data/cube-artwork.json').write_text(json.dumps({'generator':'source/generate_cube_artwork.py','font_file':args.font.name,'font_sha256':hashlib.sha256(args.font.read_bytes()).hexdigest(),'size':[256,256],'font_size_px':164,'outputs':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.glob('*.png'))}},indent=2)+'\n')
if __name__=='__main__':main()
