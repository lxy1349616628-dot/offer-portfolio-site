#!/usr/bin/env python3
"""Build a single-file portfolio site from data.json.

Usage:
    python3 build.py path/to/data.json [-o index.html] [--max-width 1200]

Every local file referenced in data.json (profile.photo, work images,
video covers, contact.resume.file) is resolved relative to data.json,
compressed when Pillow is available, and embedded as a data URI, so the
output is ONE html file that opens by double-click and can be dropped
onto any static host. http(s) and data: URLs are left as they are.
"""
import argparse
import base64
import io
import json
import mimetypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, '..', 'assets', 'template.html')

try:
    from PIL import Image, ImageOps
except Exception:  # Pillow is optional
    Image = None

IMG_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def to_data_uri(path, max_width, warnings):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXT and Image is not None and ext != '.gif':
        try:
            im = Image.open(path)
            im = ImageOps.exif_transpose(im)
            has_alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
            if im.width > max_width:
                im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
            buf = io.BytesIO()
            if has_alpha:
                im.save(buf, 'PNG', optimize=True)
                mime = 'image/png'
            else:
                im.convert('RGB').save(buf, 'JPEG', quality=84, optimize=True, progressive=True)
                mime = 'image/jpeg'
            return 'data:%s;base64,%s' % (mime, base64.b64encode(buf.getvalue()).decode())
        except Exception as e:
            warnings.append('could not compress %s (%s); embedding as-is' % (path, e))
    mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    with open(path, 'rb') as f:
        return 'data:%s;base64,%s' % (mime, base64.b64encode(f.read()).decode())


def resolve(value, base, max_width, warnings, missing):
    """Return an embeddable URL for a str or {src: ...} image reference."""
    if isinstance(value, dict):
        out = dict(value)
        if 'src' in out:
            out['src'] = resolve(out['src'], base, max_width, warnings, missing)
        return out
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(('http://', 'https://', 'data:', '#', 'mailto:')):
        return value
    path = value if os.path.isabs(value) else os.path.join(base, value)
    if not os.path.isfile(path):
        missing.append(value)
        return ''
    return to_data_uri(path, max_width, warnings)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data')
    ap.add_argument('-o', '--out', default=None)
    ap.add_argument('--max-width', type=int, default=1200)
    a = ap.parse_args()

    with open(a.data, encoding='utf-8') as f:
        d = json.load(f)
    base = os.path.dirname(os.path.abspath(a.data))
    warnings, missing = [], []
    R = lambda v: resolve(v, base, a.max_width, warnings, missing)

    p = d.get('profile', {})
    if p.get('photo'):
        p['photo'] = R(p['photo'])
    for s in d.get('sections', []):
        for w in s.get('works', []) or []:
            w['images'] = [x for x in (R(i) for i in w.get('images', []) or []) if x]
        for v in s.get('videos', []) or []:
            if v.get('cover'):
                v['cover'] = R(v['cover'])
    c = d.get('contact') or {}
    if (c.get('resume') or {}).get('file'):
        fname = os.path.basename(c['resume']['file'])
        c['resume'].setdefault('filename', fname)
        c['resume']['file'] = R(c['resume']['file'])
        if not c['resume']['file']:
            c['resume'].pop('file')

    with open(TEMPLATE, encoding='utf-8') as f:
        html = f.read()
    payload = json.dumps(d, ensure_ascii=False).replace('</', '<\\/')
    html = html.replace('__SITE_DATA__', payload)

    out = a.out or os.path.join(base, 'index.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)

    size = os.path.getsize(out) / 1024 / 1024
    print('built %s (%.1f MB)' % (out, size))
    for w in warnings:
        print('warning:', w)
    if missing:
        print('missing files (left out):', ', '.join(missing))
    if Image is None:
        print('note: Pillow not installed, images embedded uncompressed (pip install pillow)')
    if size > 15:
        print('warning: file is large; lower --max-width or use fewer images')
    return 0


if __name__ == '__main__':
    sys.exit(main())
