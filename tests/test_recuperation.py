#!/usr/bin/env python3
"""Test : fabrique une image disque contenant des fichiers entiers ET fragmentés,
lance Mosaïk en mode texte et vérifie que les fichiers sont identiques."""
import hashlib, io, os, random, subprocess, sys, tempfile, zipfile, shutil

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

random.seed(42)
CS = 4096
HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)

def jpg(w, h, seed):
    from PIL import Image
    r = random.Random(seed)
    im = Image.new("RGB", (w, h))
    im.putdata([(r.randrange(256), (x * 3) % 256, (x // w) % 256) for x in range(w * h)])
    b = io.BytesIO(); im.save(b, "JPEG", quality=92); return b.getvalue()

def png(w, h, seed):
    from PIL import Image
    r = random.Random(seed)
    im = Image.frombytes("RGB", (w, h), bytes(r.randrange(256) for _ in range(w * h * 3)))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()

def docx(seed):
    r = random.Random(seed)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", " ".join(str(r.random()) for _ in range(20000)))
    return b.getvalue()

pdf = b"%PDF-1.4\n" + os.urandom(30000) + b"\n%%EOF\n"

files = {
    "photo_entiere.jpg": jpg(300, 200, 1),
    "image_entiere.png": png(120, 90, 2),
    "document.pdf": pdf,
    "photo_fragmentee.jpg": jpg(400, 300, 3),
    "image_fragmentee.png": png(160, 120, 4),
    "rapport_fragmente.docx": docx(5),
}

disk = bytearray(os.urandom(CS * 900))   # « bruit » : anciens fichiers effacés
for i in range(0, len(disk), CS * 7):
    disk[i:i + CS] = bytes(CS)            # quelques zones vides

def put(data, pos):
    disk[pos:pos + len(data)] = data

def clusters(n): return (n + CS - 1) // CS

# entiers
put(files["photo_entiere.jpg"], CS * 10)
put(files["image_entiere.png"], CS * 60)
put(files["document.pdf"], CS * 100)
# fragmentés : 2 morceaux séparés par 13 à 40 clusters d'autres données
def frag(name, start, cut_clusters, gap):
    d = files[name]; cut = cut_clusters * CS
    put(d[:cut], start)
    put(b"\x00" * 0 + os.urandom(gap * CS), start + cut)
    put(d[cut:], start + cut + gap * CS)
frag("image_fragmentee.png", CS * 200, 3, 17)
frag("rapport_fragmente.docx", CS * 400, 5, 40)
# JPEG : le morceau intermédiaire est le début d'un autre fichier (cas réel)
d = files["photo_fragmentee.jpg"]; cut = 4 * CS
put(d[:cut], CS * 600)
put(b"%PDF-1.3\n" + os.urandom(CS * 13 - 9), CS * 600 + cut)
put(d[cut:], CS * 600 + cut + 13 * CS)

tmp = tempfile.mkdtemp()
img = os.path.join(tmp, "disque.img"); open(img, "wb").write(disk)
out = os.path.join(tmp, "sortie")
cmd = os.environ.get("MOSAIK_CMD")   # ex. chemin de Mosaik.exe (test de l'exécutable Windows)
cmd = [cmd] if cmd else [sys.executable, "-X", "faulthandler", os.path.join(ROOT, "mosaik.py")]
r = subprocess.run(cmd + ["--cli", img, "--sortie", out],
                   capture_output=True, text=True, timeout=600)
print(r.stdout[-1500:], r.stderr[-1500:])

found = {}
for root, _, fs in os.walk(out):
    for f in fs:
        found[hashlib.sha1(open(os.path.join(root, f), "rb").read()).hexdigest()] = f
ok = True
for name, data in files.items():
    h = hashlib.sha1(data).hexdigest()
    res = found.get(h)
    print(("✔" if res else "✘"), name, "→", res or "NON RETROUVÉ À L'IDENTIQUE")
    ok &= bool(res)
shutil.rmtree(tmp)
sys.exit(0 if ok else 1)
