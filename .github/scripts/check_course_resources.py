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

def check_textbook(paths, documents):
    page = ROOT + 'textbook-working-draft.md'
    pdf = ROOT + 'resources/textbook/Experience-Generating-Physical-Systems-Working-Draft-2026-10-26.pdf'
    errors = [f'{p}: required published textbook artifact is missing' for p in (page, pdf) if p not in paths]
    if '  * [Textbook — Working Draft](textbook-working-draft.md)' not in documents.get(ROOT + 'SUMMARY.md', ''):
        errors.append('SUMMARY.md: restore the textbook navigation under the course home')
    if '(textbook-working-draft.md)' not in documents.get(ROOT + 'student.md', ''):
        errors.append('student.md: restore the textbook link on the course home')
    if pdf.rsplit('/', 1)[1] not in documents.get(page, ''):
        errors.append('textbook-working-draft.md: preserve the published PDF download link')
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
        textbook = ROOT + 'textbook-working-draft.md'
        textbook_pdf = ROOT + 'resources/textbook/Experience-Generating-Physical-Systems-Working-Draft-2026-10-26.pdf'
        textbook_docs = {ROOT + 'SUMMARY.md': '  * [Textbook — Working Draft](textbook-working-draft.md)', ROOT + 'student.md': '[Textbook](textbook-working-draft.md)', textbook: textbook_pdf}
        assert not check_textbook({textbook, textbook_pdf}, textbook_docs)
        assert check_textbook({textbook}, textbook_docs)
        assert check_textbook({textbook, textbook_pdf}, dict(textbook_docs, **{ROOT + 'SUMMARY.md': ''}))
        assert check_textbook({textbook, textbook_pdf}, dict(textbook_docs, **{textbook: ''}))
        print('PASS: media rules, PDF worksheets and textbook disappearance regressions')
        return
    repo = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=repo).decode().split('\0')
    paths = set(filter(None, tracked))
    docs = {p: (repo / p).read_text() for p in paths if p.startswith(ROOT) and p.endswith('.md')}
    errors = check(paths, docs) + check_textbook(paths, docs)
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(docs)} Markdown files; no duplicate asset tree; canonical media targets exist')

if __name__ == '__main__':
    main()
