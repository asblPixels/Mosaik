#!/usr/bin/env python3
"""Construit la version en ligne de Mosaïk dans docs/ (publiée par GitHub Pages).

Le même moteur (mosaik.py) et la même interface (ui.html) que la version installée,
exécutés dans le navigateur grâce à Pyodide (Python compilé en WebAssembly).
Pyodide est copié dans le site : aucun CDN, aucun envoi de données.

Usage : python3 tools/build_web.py [dossier_pyodide]
  dossier_pyodide : dossier du paquet npm « pyodide » (sinon téléchargé avec npm).
"""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs")
PYODIDE_VERSION = "314.0.8"
PYODIDE_FILES = ("pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")

sys.path.insert(0, ROOT)
import mosaik  # noqa: E402


def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as fh:
        return fh.read()


def write(p, text):
    p = os.path.join(SITE, p)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def pyodide_dir(arg):
    if arg:
        return arg
    if all(os.path.exists(os.path.join(SITE, "pyodide", f)) for f in PYODIDE_FILES):
        return None
    tmp = tempfile.mkdtemp()
    subprocess.run(["npm", "pack", "pyodide@" + PYODIDE_VERSION], cwd=tmp, check=True, capture_output=True)
    tgz = [f for f in os.listdir(tmp) if f.endswith(".tgz")][0]
    subprocess.run(["tar", "-xzf", tgz], cwd=tmp, check=True)
    return os.path.join(tmp, "package")


def main():
    html = read("ui.html").replace("__TOKEN__", "").replace("__VERSION__", mosaik.VERSION)
    marker = '<script>\nconst TOKEN'
    assert marker in html
    html = html.replace(marker, '<script src="app/web.js"></script>\n' + marker, 1)
    html = html.replace("<title>Mosaïk — récupération de fichiers</title>",
                        "<title>Mosaïk en ligne — récupération de fichiers</title>\n"
                        '<meta name="description" content="Mosaïk : récupérez vos fichiers depuis une image disque, '
                        'directement dans le navigateur. Recollage des fichiers fragmentés. Rien n\'est envoyé sur internet.">')
    write("index.html", html)
    web = read("web/web.js").replace("__FAMILIES__", json.dumps(mosaik.FAMILIES, ensure_ascii=False)) \
                            .replace("__VERSION__", mosaik.VERSION)
    write("app/web.js", web)
    write("app/worker.mjs", read("web/worker.mjs"))
    write("app/mosaik.py", read("mosaik.py"))
    icon = read("assets/mosaik-icon.svg")
    write("logo.svg", icon)
    write("favicon.svg", icon)
    os.makedirs(os.path.join(SITE, "fonts"), exist_ok=True)
    for f in os.listdir(os.path.join(ROOT, "assets", "fonts")):
        shutil.copy(os.path.join(ROOT, "assets", "fonts", f), os.path.join(SITE, "fonts", f))
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    src = pyodide_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    if src:
        os.makedirs(os.path.join(SITE, "pyodide"), exist_ok=True)
        for f in PYODIDE_FILES:
            shutil.copy(os.path.join(src, f), os.path.join(SITE, "pyodide", f))
    print("Site construit dans", SITE)


if __name__ == "__main__":
    main()
