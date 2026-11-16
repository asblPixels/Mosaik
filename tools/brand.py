#!/usr/bin/env python3
"""Génère le logo, l'icône et l'aperçu social de Mosaïk aux couleurs de Pixel's ASBL.
Texte converti en tracés (Poppins) : les SVG s'affichent partout, sans police installée."""
import math, os
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

TURQ, WHITE, BLACK = "#26EFC5", "#FFFFFF", "#000000"
FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts") + os.sep
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def text_path(txt, font, size, x, y, track=0):
    """Renvoie (chemin SVG, largeur) du texte à la position (x, y=ligne de base)."""
    f = TTFont(FONTS + font)
    gs, cmap, hm = f.getGlyphSet(), f.getBestCmap(), f["hmtx"]
    upm = f["head"].unitsPerEm
    s = size / upm
    pen = SVGPathPen(gs)
    cx = 0
    for ch in txt:
        g = cmap[ord(ch)]
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x + cx, y)))
        cx += hm[g][0] * s + track
    return pen.getCommands(), cx - track


def icon_body(R=170, n=9):
    """Disque en mosaïque : tuiles turquoise de différentes intensités + une tuile blanche qui revient."""
    cx = cy = 256
    cell, pad = 2 * R / n, 6
    tiles, hole = [], None
    for i in range(n):
        for j in range(n):
            x, y = cx - R + i * cell, cy - R + j * cell
            d = math.hypot(x + cell / 2 - cx, y + cell / 2 - cy)
            if d > R - 2 or d < cell * 0.75:
                continue
            if (i, j) == (6, 2):
                hole = (x, y)
                tiles.append(f'<rect x="{x+pad/2:.1f}" y="{y+pad/2:.1f}" width="{cell-pad:.1f}" height="{cell-pad:.1f}" rx="7" fill="none" stroke="{WHITE}" stroke-width="3" stroke-dasharray="6 5" stroke-opacity=".8"/>')
                continue
            op = (0.28, 0.45, 0.65, 0.85, 1.0)[(i * 7 + j * 11) % 5]
            tiles.append(f'<rect x="{x+pad/2:.1f}" y="{y+pad/2:.1f}" width="{cell-pad:.1f}" height="{cell-pad:.1f}" rx="7" fill="{TURQ}" fill-opacity="{op}"/>')
    hx, hy = hole
    fx, fy = hx + 64, hy - 94
    body = "\n  ".join(tiles)
    return f'''<circle cx="256" cy="256" r="{R+16}" fill="none" stroke="{TURQ}" stroke-opacity=".25" stroke-width="3"/>
  {body}
  <circle cx="256" cy="256" r="{cell*0.42:.1f}" fill="{BLACK}" stroke="{TURQ}" stroke-width="6"/>
  <path d="M{fx+cell/2-6:.1f} {fy+cell+10:.1f} Q {hx+cell+30:.1f} {hy-10:.1f} {hx+cell/2+12:.1f} {hy+10:.1f}" fill="none" stroke="{WHITE}" stroke-width="5" stroke-linecap="round" stroke-dasharray="2 11"/>
  <rect x="{fx:.1f}" y="{fy:.1f}" width="{cell-pad:.1f}" height="{cell-pad:.1f}" rx="7" fill="{TURQ}" filter="url(#glow)" opacity=".9"/>
  <rect x="{fx:.1f}" y="{fy:.1f}" width="{cell-pad:.1f}" height="{cell-pad:.1f}" rx="7" fill="{WHITE}"/>'''


DEFS = '''<defs>
    <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="9"/></filter>
    <filter id="neon" x="-20%" y="-40%" width="140%" height="180%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>'''


def icon():
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  {DEFS}
  <rect width="512" height="512" rx="112" fill="{BLACK}"/>
  {icon_body()}
</svg>'''


def wordmark(x, y, size):
    """« Mosa » en blanc + « ïk » en turquoise néon. Renvoie (svg, largeur)."""
    p1, w1 = text_path("Mosa", "Poppins-Bold.woff2", size, x, y, track=-size * 0.01)
    p2, w2 = text_path("ïk", "Poppins-Bold.woff2", size, x + w1 + size * 0.005, y, track=-size * 0.01)
    svg = (f'<path d="{p1}" fill="{WHITE}"/>'
           f'<path d="{p2}" fill="{TURQ}" filter="url(#neon)"/>')
    return svg, w1 + w2


def logo():
    W, H = 1200, 360
    mark, w = wordmark(400, 200, 140)
    tag, _ = text_path("Récupérez vos fichiers, même en morceaux.", "Poppins-Light.woff2", 34, 404, 262)
    sub, _ = text_path("PIXEL'S ASBL  ·  LOGICIEL LIBRE  ·  LINUX", "Poppins-Medium.woff2", 21, 406, 314, track=2.2)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  {DEFS}
  <rect width="{W}" height="{H}" rx="40" fill="{BLACK}"/>
  <g transform="translate(40,24) scale(0.61)">{icon_body()}</g>
  {mark}
  <path d="{tag}" fill="{WHITE}" fill-opacity=".85"/>
  <path d="{sub}" fill="{TURQ}"/>
</svg>'''


def social():
    W, H = 1280, 640
    grid = "".join(f'<rect x="{x}" y="{y}" width="34" height="34" rx="7" fill="{TURQ}"/>'
                   for x in range(0, W, 44) for y in range(0, H, 44) if (x * 7 + y * 3) % 5 == 0)
    mark, _ = wordmark(520, 290, 150)
    tag, _ = text_path("Récupérez vos fichiers, même en morceaux.", "Poppins-Light.woff2", 31, 527, 356)
    l1, _ = text_path("Recollage des fragments  ·  The Sleuth Kit  ·  Disques abîmés", "Poppins-Regular.woff2", 23, 527, 430)
    l2, _ = text_path("Toutes distributions Linux  ·  Logiciel libre", "Poppins-Regular.woff2", 23, 527, 468)
    l3, _ = text_path("PIXEL'S ASBL", "Poppins-Medium.woff2", 22, 527, 548, track=3)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  {DEFS}
  <rect width="{W}" height="{H}" fill="{BLACK}"/>
  <g opacity=".06">{grid}</g>
  <g transform="translate(70,130) scale(0.74)"><rect width="512" height="512" rx="112" fill="#060c0b"/>{icon_body()}</g>
  {mark}
  <path d="{tag}" fill="{WHITE}" fill-opacity=".85"/>
  <path d="{l1}" fill="{TURQ}"/>
  <path d="{l2}" fill="{TURQ}"/>
  <path d="{l3}" fill="{WHITE}" fill-opacity=".55"/>
</svg>'''


if __name__ == "__main__":
    for name, svg in (("mosaik-icon.svg", icon()), ("mosaik-logo.svg", logo()), ("social-preview.svg", social())):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(svg)
    print("SVG générés dans", OUT)
