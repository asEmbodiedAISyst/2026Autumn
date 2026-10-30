#!/usr/bin/env python3
"""Read-only check of the course's canonical media paths; stdlib only."""
import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

PREFIX = 'https://raw.githubusercontent.com/asEmbodiedAISyst/2026Autumn/main/'
ROOT = '2026-autumn/'

def check(paths, documents):
    errors = []
    for p in sorted(paths):
        if p.startswith('resources/') or '/.gitbook/assets/' in p:
            errors.append(f'{p}: media belongs under {ROOT}resources/')
    for p, text in documents.items():
        if not p.startswith(ROOT):
            continue
        if '.gitbook/assets/' in text:
            errors.append(f'{p}: GitBook upload reference would recreate an asset copy')
        if not p.startswith(ROOT + 'resources/'):
            images = re.findall(r'!\[[^\]]*\]\(<?([^\s>]+)', text)
            images += re.findall(r'<img\b[^>]*\bsrc=[\"\x27]([^\"\x27]+)', text)
            for image in images:
                if not image.startswith(('https://', 'http://')):
                    errors.append(f'{p}: use a canonical public resources URL for embedded image {image}')
        for target in re.findall(r'https://raw\.githubusercontent\.com/asEmbodiedAISyst/2026Autumn/main/[^\s<>"\)]+', text):
            # Canonical URLs encode spaces and parentheses; only query/fragment are stripped.
            resource = unquote(urlsplit(target).path.split('/main/', 1)[1])
            if not resource.startswith(ROOT + 'resources/') or resource not in paths:
                errors.append(f'{p}: missing or noncanonical resource {resource}')
    return errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        page = ROOT + 'module/example.md'
        image = ROOT + 'resources/class02/figures/image.png'
        assert not check({page, image}, {page: f'![Figure]({PREFIX}{image})'})
        assert check({page, image, ROOT + '.gitbook/assets/image.png'}, {})
        assert check({page}, {page: '![Figure](../.gitbook/assets/image.png)'})
        assert check({page}, {page: f'![Figure]({PREFIX}{image})'})
        assert check({page, image}, {page: '![Figure](../resources/class02/figures/image.png)'})
        assert check({'resources/image.png'}, {})
        pdf = ROOT + 'resources/worksheets/claim.pdf'
        assert not check({page, pdf}, {page: '[Worksheet](../resources/worksheets/claim.pdf)'})
        print('PASS: valid media, duplicate files, upload refs, missing targets, root layout, PDF exception')
        return
    repo = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=repo).decode().split('\0')
    paths = set(filter(None, tracked))
    docs = {p: (repo / p).read_text() for p in paths if p.startswith(ROOT) and p.endswith('.md')}
    errors = check(paths, docs)
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(docs)} Markdown files; no duplicate asset tree; canonical media targets exist')

if __name__ == '__main__':
    main()
