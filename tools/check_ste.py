#!/usr/bin/env python3
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / 'extension/popup.html', ROOT / 'extension/popup.js', ROOT / 'extension/manifest.json']
BANNED = {'actually', 'quietly', 'secretly'}
STRING_RE = re.compile(r'>([^<>]+)<|["\']([^"\'\\]*(?:\\.[^"\'\\]*)*)["\']')
WORD_RE = re.compile(r"[A-Za-z0-9']+")
failures = []
for path in FILES:
    text = path.read_text(encoding='utf-8')
    if '\u2014' in text:
        failures.append(f'{path}: em dash found')
    if re.search(r'[\U00010000-\U0010ffff]', text):
        failures.append(f'{path}: emoji or non-BMP character found')
    for m in STRING_RE.finditer(text):
        value = (m.group(1) or m.group(2) or '').strip()
        if not value or value.startswith(('http', '#', '.', '/', 'tab:', 'privacybrew:')):
            continue
        low = value.lower()
        for word in BANNED:
            if re.search(rf'\b{word}\b', low):
                failures.append(f'{path}: banned filler word "{word}" in {value!r}')
        for sentence in re.split(r'[.!?]+', value):
            sentence = sentence.strip()
            if not sentence:
                continue
            count = len(WORD_RE.findall(sentence))
            if count > 20:
                failures.append(f'{path}: {count} words in sentence {sentence!r}')
if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('STE check passed')
