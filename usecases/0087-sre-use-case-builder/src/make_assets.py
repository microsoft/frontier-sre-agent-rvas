"""Build src/kit_6_assets.py: subset OFL fonts (woff2, Latin-1) embedded in the kit as report font presets.

Only needed to change the presets. Put the source TTFs in src/fonts (or pass a folder):
  IBMPlexSans-var.ttf  (github.com/IBM/plex, IBM Plex Sans variable)  -> renamed "Report Sans" (Reserved Font Name "Plex")
  NunitoSans-var.ttf   (github.com/googlefonts/NunitoSans)
  FiraSans-Regular/SemiBold/Bold.ttf (github.com/mozilla/Fira)
Then: python src/make_assets.py [fonts-folder] && python src/build_kit.py
"""
import base64
import io
import json
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

sys.stdout.reconfigure(encoding="utf-8")
FONTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "fonts"
OUT = Path(__file__).resolve().parent / "kit_6_assets.py"
TEXT = "".join(chr(c) for c in list(range(0x20, 0x7F)) + list(range(0xA0, 0x100))) + "–—‘’‚“”„•…‹›€™−≤≥×→←↑↓▲▼↗·"

PRESETS = {
    "plex": {"family": "Report Sans", "rename": "ReportSans",
             "style": "technical, neutral corporate (default; IBM Plex Sans renamed per its Reserved Font Name)", "display": 700,
             "src": {400: ("IBMPlexSans-var.ttf", {"wght": 400, "wdth": 100}), 600: ("IBMPlexSans-var.ttf", {"wght": 600, "wdth": 100}),
                     700: ("IBMPlexSans-var.ttf", {"wght": 700, "wdth": 100})}},
    "nunito": {"family": "Nunito Sans", "style": "rounded, friendly geometric (Avenir, Montserrat, Gotham, Poppins...)", "display": 900,
               "src": {400: ("NunitoSans-var.ttf", {"wght": 400, "wdth": 100, "opsz": 12, "YTLC": 500}),
                       700: ("NunitoSans-var.ttf", {"wght": 700, "wdth": 100, "opsz": 12, "YTLC": 500}),
                       900: ("NunitoSans-var.ttf", {"wght": 900, "wdth": 100, "opsz": 12, "YTLC": 500})}},
    "fira": {"family": "Fira Sans", "style": "humanist (Lato, Source Sans, Frutiger, Open Sans, Calibri...)", "display": 600,
             "src": {400: ("FiraSans-Regular.ttf", None), 600: ("FiraSans-SemiBold.ttf", None), 700: ("FiraSans-Bold.ttf", None)}},
}


def woff2(path, axes, rename=None, family=None, weight=400):
    font = TTFont(FONTS / path)
    if axes:
        font = instancer.instantiateVariableFont(font, axes)
    if rename:
        # Modified Version of a font with a Reserved Font Name (OFL 1.1, condition 3): it must not keep that name.
        style = {400: "Regular", 600: "SemiBold", 700: "Bold"}[weight]
        table = font["name"]
        for rec in list(table.names):
            if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25):
                table.removeNames(nameID=rec.nameID)
        for nid, text in {1: family if weight == 400 else f"{family} {style}", 2: "Regular" if weight in (400, 600) else "Bold",
                          3: f"{rename}-{style};sre-usecase-builder", 4: f"{family} {style}", 6: f"{rename}-{style}",
                          16: family, 17: style}.items():
            table.setName(text, nid, 3, 1, 0x409)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "tnum", "lnum", "case"]
    opts.notdef_outline = True
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17]
    sub = subset.Subsetter(opts)
    sub.populate(text=TEXT)
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    return buf.getvalue()


assets = {}
total = 0
for key, p in PRESETS.items():
    faces = {}
    for weight, (path, axes) in p["src"].items():
        data = woff2(path, axes, p.get("rename"), p["family"], weight)
        faces[weight] = base64.b64encode(data).decode()
        total += len(faces[weight])
        print(key, weight, len(data))
    assets[key] = {"family": p["family"], "style": p["style"], "display": p["display"], "faces": faces,
                   "license": "SIL Open Font License 1.1"}
lines = ['', '', '# ----------------------------------------------------------------------------- report font presets',
         '# Subsets (Latin-1) of SIL OFL 1.1 fonts (license texts: src/fonts-OFL.txt): Report Sans = IBM Plex Sans (IBM Corp.) renamed',
         '# because "Plex" is a Reserved Font Name; Nunito Sans (The Nunito Sans Project Authors: Vernon Adams, Jacques Le Bailly,',
         '# Manvel Shmavonyan, Alexei Vanyashin), Fira Sans (Mozilla/Telefonica). Embedded in reports so they render offline.',
         'FONT_PRESETS = {']
for key, a in assets.items():
    lines.append(f'    {key!r}: {{"family": {a["family"]!r}, "style": {a["style"]!r}, "display": {a["display"]}, "faces": {{')
    for weight, b64 in a["faces"].items():
        chunks = [b64[i:i + 110] for i in range(0, len(b64), 110)]
        lines.append(f'        {weight}: (')
        lines += [f'            "{c}"' for c in chunks]
        lines.append('        ),')
    lines.append('    }},')
lines.append('}')
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("presets b64 total", total, "file", OUT.stat().st_size)
