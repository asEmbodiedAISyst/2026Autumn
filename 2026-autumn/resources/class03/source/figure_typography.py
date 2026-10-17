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
    for weight in ('normal', 'semibold'):
        prop = fm.FontProperties(family=['MiSans'], weight=weight)
        try:
            path = Path(fm.findfont(prop, fallback_to_default=False))
        except ValueError as exc:
            raise RuntimeError('MiSans is unavailable. Register licensed native MiSans font files before rendering.') from exc
        actual_family = fm.get_font(str(path)).family_name
        if actual_family != 'MiSans':
            raise RuntimeError(f'Refusing font substitution: requested MiSans, resolved {actual_family!r}.')
        receipt[weight] = {'filename': path.name, 'family': actual_family,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if receipt['normal']['sha256'] == receipt['semibold']['sha256']:
        # A variable MiSans font can supply both weights; separate static files
        # must not be silently treated as a complete family.
        from fontTools.ttLib import TTFont
        with TTFont(fm.findfont(fm.FontProperties(family=['MiSans']))) as font:
            if 'fvar' not in font:
                raise RuntimeError('Register a genuine MiSans Semibold face; only one static face was resolved.')
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
