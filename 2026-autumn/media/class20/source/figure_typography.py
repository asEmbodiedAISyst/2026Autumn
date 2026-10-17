"""Require genuine MiSans fonts before generating course figures.

Use apply_publication_style([regular_ttf, semibold_ttf]) at script startup.
Font files are local licensed dependencies; they are not bundled by this helper.
"""
from pathlib import Path
import hashlib

def apply_publication_style(font_paths=(), style_path=None):
    import matplotlib.style as mpl_style
    from matplotlib import font_manager as fm
    for path in font_paths:
        path = Path(path).resolve(strict=True)
        if path.suffix.lower() not in {'.ttf', '.otf', '.ttc'}:
            raise ValueError('Native figure generation requires MiSans TTF/OTF/TTC files.')
        fm.fontManager.addfont(str(path))
    receipt = {}
    if len(font_paths) != 2:
        raise RuntimeError('Supply exact native MiSans Regular and Semibold files.')
    for weight, supplied in zip(('normal', 'semibold'), font_paths):
        path = Path(supplied).resolve(strict=True)
        font = fm.get_font(str(path))
        expected_style = 'Regular' if weight == 'normal' else 'Semibold'
        if font.family_name != 'MiSans' or font.style_name != expected_style:
            raise RuntimeError(f'Refusing font substitution: expected MiSans {expected_style}, got {font.family_name} {font.style_name}.')
        receipt[weight] = {'filename': path.name, 'family': font.family_name,
                           'style': font.style_name,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    path = Path(style_path) if style_path else Path(__file__).with_name('publication.mplstyle')
    mpl_style.use(str(path))
    return receipt

if __name__ == '__main__':
    import argparse, json
    import matplotlib.pyplot  # exposes matplotlib.style
    parser = argparse.ArgumentParser(description='Preflight required MiSans figure fonts.')
    parser.add_argument('--font', type=Path, action='append', default=[])
    args = parser.parse_args()
    print(json.dumps(apply_publication_style(args.font), indent=2))
