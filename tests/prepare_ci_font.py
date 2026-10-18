"""Explicit CI setup: fetch a checksum-pinned Noto font and its OFL notice.

Not called by application scripts or npm test. Does not install a system font.
"""
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'output' / 'ci-fonts'
FONT_URL = 'https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/OTF/SimplifiedChinese/NotoSerifCJKsc-Regular.otf'
LICENSE_URL = 'https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/LICENSE'
FONT_SHA256 = '2a2eae2628df83556c54018c41e20fa532c1b862c5256ae8b3f23feb918d12ca'


def main():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    font = DIRECTORY / 'NotoSerifCJKsc-Regular.otf'
    if not font.exists() or hashlib.sha256(font.read_bytes()).hexdigest() != FONT_SHA256:
        with urllib.request.urlopen(FONT_URL, timeout=60) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != FONT_SHA256:
            raise RuntimeError('Font checksum mismatch; review the upstream change before updating the pin.')
        font.write_bytes(content)
    with urllib.request.urlopen(LICENSE_URL, timeout=30) as response:
        (DIRECTORY / 'LICENSE').write_bytes(response.read())
    print(font)


if __name__ == '__main__':
    main()
