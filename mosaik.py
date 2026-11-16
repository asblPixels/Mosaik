#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mosaïk — récupérateur visuel de fichiers pour disques endommagés ou fragmentés.
Pixel's ASBL — https://www.asblpixels.be

Aucune dépendance : uniquement la bibliothèque standard de Python 3 (>= 3.8).
Fonctionne sur toutes les distributions Linux et sur Windows 10/11.
L'interface s'ouvre dans le navigateur web (serveur local accessible uniquement depuis cette machine).

Principe de sécurité : le disque source n'est JAMAIS écrit. Il est ouvert en
lecture seule ; les fichiers retrouvés sont enregistrés ailleurs.
"""

import argparse
import datetime
import json
import os
import re
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "2.2.0"
APP = "Mosaïk"
HERE = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.realpath(__file__))  # exe PyInstaller

SECTOR = 512
WINDOWS = os.name == "nt"
WEB = sys.platform == "emscripten"      # version en ligne (Pyodide, dans le navigateur)


# ═════════════════════════════════════════════════════════════════════════════
#  Couche plateforme : Linux et Windows
# ═════════════════════════════════════════════════════════════════════════════

def is_admin():
    if WINDOWS:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return os.geteuid() == 0


_PREAD_LOCK = threading.Lock()


def pread(fd, n, off):
    """Lecture à une position donnée. Sous Windows, les disques bruts exigent
    des lectures alignées sur le secteur : on aligne puis on découpe."""
    if not WINDOWS and hasattr(os, "pread"):
        return os.pread(fd, n, off)
    if not WINDOWS:
        with _PREAD_LOCK:
            os.lseek(fd, off, os.SEEK_SET)
            return os.read(fd, n)
    a = off - (off % SECTOR)
    end = off + n
    b = end + (-end % SECTOR)
    with _PREAD_LOCK:
        os.lseek(fd, a, os.SEEK_SET)
        data = os.read(fd, b - a)
    return data[off - a:off - a + n]


def device_size(fd, path):
    """Taille d'un disque, d'une partition ou d'une image."""
    if WINDOWS and path.startswith("\\\\.\\"):
        import ctypes
        import msvcrt
        from ctypes import wintypes
        handle = msvcrt.get_osfhandle(fd)
        length = ctypes.c_longlong(0)
        ret = wintypes.DWORD(0)
        IOCTL_DISK_GET_LENGTH_INFO = 0x7405C
        ok = ctypes.windll.kernel32.DeviceIoControl(
            wintypes.HANDLE(handle), IOCTL_DISK_GET_LENGTH_INFO, None, 0,
            ctypes.byref(length), ctypes.sizeof(length), ctypes.byref(ret), None)
        if ok:
            return length.value
    return os.lseek(fd, 0, os.SEEK_END)


def powershell_json(cmd):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            cmd + " | ConvertTo-Json -Compress"],
                           capture_output=True, text=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = json.loads(r.stdout or "[]")
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def list_devices_windows():
    devs = []
    disks = powershell_json("Get-CimInstance Win32_DiskDrive | Select-Object Index,Model,Size,InterfaceType,MediaType")
    parts = powershell_json("Get-Partition | Where-Object DriveLetter | Select-Object DiskNumber,DriveLetter,Size")
    vols = {str(v.get("DriveLetter")): v for v in powershell_json(
        "Get-Volume | Where-Object DriveLetter | Select-Object DriveLetter,FileSystemLabel,FileSystem")}
    sysdrive = (os.environ.get("SystemDrive") or "C:")[0].upper()
    for d in sorted(disks, key=lambda x: x.get("Index", 0)):
        idx = d.get("Index")
        iface = (d.get("InterfaceType") or "").lower()
        devs.append({"path": "\\\\.\\PhysicalDrive%s" % idx, "name": "PhysicalDrive%s" % idx, "type": "disk",
                     "size": int(d.get("Size") or 0), "model": (d.get("Model") or "").strip(),
                     "fs": "", "label": "", "mount": "", "parent": "",
                     "removable": "removable" in (d.get("MediaType") or "").lower() or iface == "usb",
                     "tran": iface})
        for p in parts:
            if p.get("DiskNumber") != idx:
                continue
            letter = str(p.get("DriveLetter"))
            v = vols.get(letter, {})
            devs.append({"path": "\\\\.\\%s:" % letter, "name": letter + ":", "type": "part",
                         "size": int(p.get("Size") or 0), "model": "", "fs": (v.get("FileSystem") or "").lower(),
                         "label": (v.get("FileSystemLabel") or "") or (letter + ":"),
                         "mount": letter + ":\\" + (" (système)" if letter.upper() == sysdrive else ""),
                         "removable": False, "tran": "", "parent": "PhysicalDrive%s" % idx})
    return devs


def windows_disk_of(path):
    """Numéro du disque physique qui porte la lettre de lecteur d'un chemin."""
    drive = os.path.splitdrive(os.path.abspath(path))[0].rstrip(":\\")[-1:]
    if not drive:
        return None
    r = powershell_json("Get-Partition -DriveLetter %s | Select-Object DiskNumber" % drive)
    return r[0].get("DiskNumber") if r else None
MAP_CELLS = 2400            # nombre de cases de la mosaïque
READ_CHUNK = 4 * 1024 * 1024
SCAN_CHUNK = 16 * 1024 * 1024    # lecture séquentielle par gros blocs (débit maximal)

# États des cases de la mosaïque (priorité croissante)
C_UNREAD, C_EMPTY, C_DATA = "0", "1", "2"
C_IMAGE, C_DOC, C_AUDIO, C_VIDEO, C_ARCH = "4", "5", "6", "7", "8"
C_FRAG, C_BAD = "9", "3"
PRIORITY = {C_UNREAD: 0, C_EMPTY: 1, C_DATA: 2, C_IMAGE: 5, C_DOC: 5, C_AUDIO: 5,
            C_VIDEO: 5, C_ARCH: 5, C_FRAG: 8, C_BAD: 9}

CATEGORY = {
    "jpg": ("Images", C_IMAGE), "png": ("Images", C_IMAGE), "gif": ("Images", C_IMAGE),
    "bmp": ("Images", C_IMAGE), "webp": ("Images", C_IMAGE), "heic": ("Images", C_IMAGE),
    "pdf": ("Documents", C_DOC), "docx": ("Documents", C_DOC), "xlsx": ("Documents", C_DOC),
    "pptx": ("Documents", C_DOC), "odt": ("Documents", C_DOC), "ods": ("Documents", C_DOC),
    "odp": ("Documents", C_DOC), "epub": ("Documents", C_DOC), "sqlite": ("Documents", C_DOC),
    "mp3": ("Audio", C_AUDIO), "wav": ("Audio", C_AUDIO), "m4a": ("Audio", C_AUDIO),
    "mp4": ("Vidéos", C_VIDEO), "mov": ("Vidéos", C_VIDEO), "avi": ("Vidéos", C_VIDEO),
    "3gp": ("Vidéos", C_VIDEO), "zip": ("Archives", C_ARCH), "jar": ("Archives", C_ARCH),
    "apk": ("Archives", C_ARCH),
}

# Familles proposées à l'utilisateur -> carveurs
FAMILIES = {
    "jpg": "Photos JPEG", "png": "Images PNG", "gif": "Images GIF", "bmp": "Images BMP",
    "pdf": "PDF", "zip": "Office / LibreOffice / ZIP", "riff": "WAV / AVI / WEBP",
    "mp4": "Vidéos MP4 / MOV / M4A / HEIC", "mp3": "Musique MP3", "sqlite": "Bases SQLite",
}


# ═════════════════════════════════════════════════════════════════════════════
#  Lecture de la source (lecture seule, tolérante aux secteurs illisibles)
# ═════════════════════════════════════════════════════════════════════════════

class Source:
    """Disque, partition ou image, ouvert en lecture seule."""

    BLOCK = 1024 * 1024

    def __init__(self, path, on_bad=None):
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | getattr(os, "O_LARGEFILE", 0) | getattr(os, "O_BINARY", 0))
        self.size = device_size(self.fd, path)
        if self.size <= 0:
            raise ValueError("Source vide ou taille inconnue : " + path)
        self.on_bad = on_bad
        self._cache = {}
        self._order = []
        self._lock = threading.Lock()
        self.bad_sectors = 0
        self.bad_units = set()
        self.consec_bad = 0
        self.skip_left = 0

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass

    BAD_UNIT = 64 * 1024

    def _mark_bad(self, k):
        u = self.BAD_UNIT
        self.bad_units.add(k)
        self.bad_sectors += u // SECTOR
        if self.on_bad:
            self.on_bad(k * u, u)

    def _is_bad(self, off, n):
        u = self.BAD_UNIT
        return any(k in self.bad_units for k in range(off // u, (off + n - 1) // u + 1))

    def _raw(self, off, n):
        """Lit n octets. Zone illisible : remplie de zéros et mémorisée, sans
        relire secteur par secteur (sur un disque abîmé, chaque secteur
        défectueux peut bloquer plusieurs secondes)."""
        if not self.bad_units or not self._is_bad(off, n):
            try:
                b = pread(self.fd, n, off)
                return b if len(b) == n else b + bytes(n - len(b))
            except OSError:
                pass
        u = self.BAD_UNIT
        out = bytearray()
        pos, end = off, off + n
        while pos < end:
            k = pos // u
            step = min((k + 1) * u, end) - pos
            b = None
            if k not in self.bad_units:
                if self.skip_left > 0:
                    # échecs en série : on saute sans lire (méthode ddrescue)
                    self.skip_left -= 1
                    self._mark_bad(k)
                else:
                    try:
                        b = pread(self.fd, step, pos)
                        self.consec_bad = 0
                    except OSError:
                        self._mark_bad(k)
                        self.consec_bad += 1
                        if self.consec_bad >= 3:
                            self.skip_left = min(2 ** (self.consec_bad - 2), 1024)
            if not b:
                b = bytes(step)
            elif len(b) < step:
                b = b + bytes(step - len(b))
            out += b
            pos += step
        return bytes(out)

    def _block(self, idx):
        with self._lock:
            b = self._cache.get(idx)
            if b is not None:
                return b
        b = self._raw(idx * self.BLOCK, min(self.BLOCK, max(0, self.size - idx * self.BLOCK)))
        with self._lock:
            self._cache[idx] = b
            self._order.append(idx)
            if len(self._order) > 48:
                self._cache.pop(self._order.pop(0), None)
        return b

    def read(self, off, n):
        if off < 0 or n <= 0 or off >= self.size:
            return b""
        n = min(n, self.size - off)
        if n > 8 * self.BLOCK:
            return self._raw(off, n)
        out = []
        while n > 0:
            idx, rel = divmod(off, self.BLOCK)
            blk = self._block(idx)
            piece = blk[rel:rel + n]
            if not piece:
                break
            out.append(piece)
            off += len(piece)
            n -= len(piece)
        return b"".join(out)


class Layout:
    """Fichier vu comme une suite de fragments physiques (le dernier est ouvert)."""

    def __init__(self, src, start, limit):
        self.src = src
        self.frags = [[start, None]]
        self.limit = limit          # taille logique maximale

    def copy(self):
        lay = Layout(self.src, 0, self.limit)
        lay.frags = [f[:] for f in self.frags]
        return lay

    def _locate(self, lo):
        base = 0
        for i, (ps, ln) in enumerate(self.frags):
            if ln is None or lo < base + ln:
                return i, ps + (lo - base), base
            base += ln
        return None, None, None

    def phys(self, lo):
        return self._locate(lo)[1]

    def read(self, lo, n):
        out = []
        while n > 0:
            i, p, base = self._locate(lo)
            if i is None:
                break
            ln = self.frags[i][1]
            take = n if ln is None else min(n, base + ln - lo)
            b = self.src.read(p, take)
            if not b:
                break
            out.append(b)
            lo += len(b)
            n -= len(b)
            if len(b) < take:
                break
        return b"".join(out)

    def split(self, cut_phys, resume_phys):
        """Ferme le dernier fragment en cut_phys et reprend en resume_phys."""
        last = self.frags[-1]
        last[1] = cut_phys - last[0]
        self.frags.append([resume_phys, None])

    def finish(self, logical_size):
        base = sum(f[1] for f in self.frags[:-1])
        self.frags[-1][1] = max(0, logical_size - base)
        return [(a, b) for a, b in self.frags if b > 0]

    def open_start(self):
        return self.frags[-1][0]

    def logical_of_phys_in_last(self, p):
        base = sum(f[1] for f in self.frags[:-1])
        return base + (p - self.frags[-1][0])


class Carved:
    def __init__(self, ext, frags, status, note=""):
        self.ext = ext
        self.frags = frags          # [(offset, longueur), ...]
        self.status = status        # "complet" | "reconstruit" | "partiel"
        self.note = note
        self.tail = b""            # octets ajoutés en fin (ex. FFD9 pour un JPEG partiel)

    @property
    def size(self):
        return sum(l for _, l in self.frags) + len(self.tail)


# ═════════════════════════════════════════════════════════════════════════════
#  Recherche de fragments (gap carving)
# ═════════════════════════════════════════════════════════════════════════════

class GapSearch:
    """Quand un fichier « casse » (CRC faux, structure invalide), on suppose
    qu'il continue plus loin sur le disque, à une frontière de cluster.
    On essaie chaque point de coupure possible et chaque saut possible ;
    une vérification forte (CRC, décompression, structure) valide le recollage."""

    def __init__(self, cluster=4096, max_gap_clusters=1024, max_frags=8, budget=2.0):
        self.cs = cluster
        self.max_gap = max_gap_clusters
        self.max_frags = max_frags
        self.budget = budget        # secondes maximum par recherche

    def boundaries(self, lay, p_from, p_to):
        start = lay.open_start()
        c = ((max(p_from, start + 1) + self.cs - 1) // self.cs) * self.cs
        out = []
        while c <= p_to and len(out) < 64:
            if c > start:
                out.append(c)
            c += self.cs
        return out

    def search(self, lay, p_from, p_to, check, stop=None):
        """check(layout_essai) -> bool. Renvoie la layout recollée ou None."""
        if len(lay.frags) >= self.max_frags:
            return None
        deadline = time.monotonic() + self.budget
        for c in reversed(self.boundaries(lay, p_from, p_to)):
            for g in range(1, self.max_gap + 1):
                if (stop and stop()) or (g & 31 == 0 and time.monotonic() > deadline):
                    return None
                resume = c + g * self.cs
                if resume >= lay.src.size:
                    break
                trial = lay.copy()
                trial.split(c, resume)
                try:
                    if check(trial):
                        return trial
                except Exception:
                    pass
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  Carveurs (un par format)
# ═════════════════════════════════════════════════════════════════════════════

def u16be(b, o=0): return struct.unpack_from(">H", b, o)[0]
def u32be(b, o=0): return struct.unpack_from(">I", b, o)[0]
def u16le(b, o=0): return struct.unpack_from("<H", b, o)[0]
def u32le(b, o=0): return struct.unpack_from("<I", b, o)[0]


HEADER_SIGS = [b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"%PDF-",
               b"PK\x03\x04", b"RIFF", b"ID3", b"SQLite format 3\x00"]


def looks_like_header(b):
    if len(b) >= 8 and b[4:8] == b"ftyp":
        return True
    return any(b.startswith(s) for s in HEADER_SIGS)


class Carvers:
    def __init__(self, src, gaps, stop=None):
        self.src = src
        self.gaps = gaps
        self.stop = stop

    # ── PNG : chaque bloc a un CRC → reconstruction fiable ──────────────────
    def png(self, off):
        lay = Layout(self.src, off, 256 * 1024 * 1024)
        if lay.read(0, 8) != b"\x89PNG\r\n\x1a\n":
            return None
        lo, rebuilt, first = 8, False, True

        def chunk_ok(l, at):
            h = l.read(at, 8)
            if len(h) < 8:
                return None
            n, t = u32be(h), h[4:8]
            if n > 64 * 1024 * 1024 or not t.isalpha():
                return None
            body = l.read(at + 4, n + 8)
            if len(body) < n + 8:
                return None
            if zlib.crc32(body[:-4]) & 0xffffffff != u32be(body, n + 4):
                return None
            return n, t

        while lo < lay.limit:
            r = chunk_ok(lay, lo)
            if r is None:
                if first:
                    return None     # IHDR invalide : faux positif
                p0 = lay.phys(lo)
                h = lay.read(lo, 8)
                n = u32be(h) if len(h) == 8 and u32be(h) < 64 * 1024 * 1024 else 0
                at = lo
                new = self.gaps.search(lay, p0, p0 + 12 + n,
                                       lambda t: chunk_ok(t, at) is not None, self.stop)
                if new is None:
                    return Carved("png", lay.finish(lo), "partiel", "fragment manquant") if lo > 64 else None
                lay, rebuilt = new, True
                continue
            n, t = r
            if first and t != b"IHDR":
                return None
            first = False
            lo += 12 + n
            if t == b"IEND":
                return Carved("png", lay.finish(lo), "reconstruit" if rebuilt else "complet")
        return None

    # ── JPEG : pas de CRC → validation structurelle + marqueurs RST ─────────
    @staticmethod
    def _entropy_valid(data, expect_rst):
        """Vérifie qu'un bloc ressemble à des données JPEG compressées."""
        if not data or data.count(0) > len(data) * 0.6 or looks_like_header(data[:16]):
            return False
        i = data.find(b"\xff")
        rst = expect_rst
        while i != -1 and i + 1 < len(data):
            m = data[i + 1]
            if m in (0x00, 0xff):
                pass
            elif 0xd0 <= m <= 0xd7:
                if rst is not None and m != rst:
                    return False
                rst = 0xd0 + ((m - 0xd0 + 1) % 8)
            elif m == 0xd9:
                return i > 256      # fin d'image plausible
            else:
                return False        # marqueur impossible dans des données compressées
            i = data.find(b"\xff", i + 2)
        return True

    def jpg(self, off):
        lay = Layout(self.src, off, 128 * 1024 * 1024)
        if lay.read(0, 3) != b"\xff\xd8\xff":
            return None
        lo, rebuilt, uses_rst, next_rst, seen_sos = 2, False, False, None, False
        cs = self.gaps.cs
        while lo < lay.limit:
            if self.stop and self.stop():
                return None
            h = lay.read(lo, 4)
            if len(h) < 2 or h[0] != 0xff:
                return None if not seen_sos else Carved("jpg", lay.finish(lo), "partiel")
            m = h[1]
            if m == 0xff:
                lo += 1
                continue
            if m == 0xd9:
                return Carved("jpg", lay.finish(lo + 2), "reconstruit" if rebuilt else "complet")
            if 0xd0 <= m <= 0xd7 or m == 0x01:
                lo += 2
                continue
            if len(h) < 4:
                return None
            seglen = u16be(h, 2)
            if seglen < 2 or not (0xc0 <= m <= 0xfe):
                return None if not seen_sos else Carved("jpg", lay.finish(lo), "partiel")
            if m == 0xdd:
                uses_rst = True
            lo += 2 + seglen
            if m != 0xda:
                continue
            seen_sos = True
            next_rst = 0xd0 if uses_rst else None
            # ── données compressées : on avance par blocs ──
            while True:
                if self.stop and self.stop():
                    return None
                p = lay.phys(lo)
                block = lay.read(lo, 64 * 1024)
                if len(block) < 2:
                    return Carved("jpg", lay.finish(lo), "partiel")
                brk, i, end_marker = None, 0, None
                # cluster commençant par un autre en-tête → cassure
                c = ((p + cs - 1) // cs) * cs
                while c < p + len(block):
                    rel = c - p
                    cl = block[rel:rel + cs]
                    if looks_like_header(cl[:16]) or (len(cl) == cs and cl.count(0) == cs):
                        brk = rel
                        break
                    c += cs
                scan_end = brk if brk is not None else len(block) - 1
                i = block.find(b"\xff", 0, scan_end)
                while i != -1 and i < scan_end:
                    mk = block[i + 1]
                    if mk in (0x00, 0xff):
                        pass
                    elif 0xd0 <= mk <= 0xd7:
                        if next_rst is not None:
                            if mk != next_rst:
                                brk = i
                                break
                            next_rst = 0xd0 + ((mk - 0xd0 + 1) % 8)
                    elif mk == 0xd9 or mk in (0xc4, 0xda, 0xdd, 0xdb, 0xfe) or 0xe0 <= mk <= 0xef:
                        end_marker = i
                        break
                    else:
                        brk = i
                        break
                    i = block.find(b"\xff", i + 2, scan_end)
                if end_marker is not None:
                    lo += end_marker
                    break
                if brk is None:
                    lo += max(1, scan_end)
                    continue
                # cassure détectée → recherche du fragment suivant
                pbrk = p + brk
                exp = next_rst

                def check(t, cut_lo=None):
                    resume = t.frags[-1][0]
                    data = self.src.read(resume, 2 * cs)
                    return self._entropy_valid(data, exp if uses_rst else None)

                fc = (pbrk // cs) * cs
                new = self.gaps.search(lay, fc, fc, check, self.stop) if fc > lay.open_start() else None
                if new is None:
                    cut = (pbrk // cs) * cs if pbrk // cs * cs > lay.open_start() else pbrk
                    res = Carved("jpg", lay.finish(lay.logical_of_phys_in_last(cut)), "partiel",
                                 "fin manquante, image complétée")
                    res.tail = b"\xff\xd9"
                    return res
                lay, rebuilt = new, True
                lo = lay.logical_of_phys_in_last(lay.frags[-1][0])
        return None

    # ── GIF ─────────────────────────────────────────────────────────────────
    def gif(self, off):
        s = self.src
        h = s.read(off, 13)
        if len(h) < 13 or h[:6] not in (b"GIF87a", b"GIF89a"):
            return None
        w, hh = u16le(h, 6), u16le(h, 8)
        if not w or not hh:
            return None
        p = off + 13
        if h[10] & 0x80:
            p += 3 * (2 << (h[10] & 7))
        limit = off + 64 * 1024 * 1024
        while p < limit:
            b = s.read(p, 1)
            if not b:
                return None
            t = b[0]
            if t == 0x3b:
                return Carved("gif", [(off, p + 1 - off)], "complet")
            if t == 0x21:
                p += 2
            elif t == 0x2c:
                d = s.read(p, 10)
                if len(d) < 10:
                    return None
                p += 10
                if d[9] & 0x80:
                    p += 3 * (2 << (d[9] & 7))
                p += 1  # taille de code LZW
            else:
                return Carved("gif", [(off, p - off)], "partiel") if p - off > 1024 else None
            while True:  # sous-blocs
                n = s.read(p, 1)
                if not n:
                    return None
                p += 1 + n[0]
                if n[0] == 0:
                    break
        return None

    # ── BMP ─────────────────────────────────────────────────────────────────
    def bmp(self, off):
        h = self.src.read(off, 30)
        if len(h) < 30 or h[:2] != b"BM":
            return None
        size, res, data_off, dib = u32le(h, 2), u32le(h, 6), u32le(h, 10), u32le(h, 14)
        if res != 0 or dib not in (12, 40, 52, 56, 108, 124) or not (54 <= size <= 300 * 1024 * 1024):
            return None
        if not (14 + dib <= data_off < size):
            return None
        bpp = u16le(h, 28)
        if bpp not in (1, 4, 8, 16, 24, 32):
            return None
        return Carved("bmp", [(off, size)], "complet")

    # ── PDF ─────────────────────────────────────────────────────────────────
    def pdf(self, off):
        s = self.src
        if s.read(off, 5) != b"%PDF-":
            return None
        p, limit, end = off, off + 96 * 1024 * 1024, None
        while p < limit:
            blk = s.read(p, 1024 * 1024)
            if not blk:
                break
            i = blk.find(b"%%EOF")
            if i != -1:
                end = p + i + 5
                # mise à jour incrémentale juste après ?
                nxt = s.read(end, 4096)
                j = nxt.find(b"%%EOF")
                if j != -1 and (b"xref" in nxt[:j] or b" obj" in nxt[:j]):
                    p = end
                    continue
                tail = s.read(end, 2)
                end += len(tail) - len(tail.lstrip(b"\r\n"))
                return Carved("pdf", [(off, end - off)], "complet")
            if (b"%PDF-" in blk[8:] and p > off) or len(blk) < 1024 * 1024:
                break
            p += len(blk) - 8
        if end:
            return Carved("pdf", [(off, end - off)], "complet")
        return None

    # ── ZIP / DOCX / XLSX / ODT… : CRC par entrée → reconstruction fiable ───
    def zip(self, off):
        lay = Layout(self.src, off, 2 * 1024 * 1024 * 1024)
        lo, names, rebuilt, n_entries = 0, [], False, 0

        def entry(l, at):
            h = l.read(at, 30)
            if len(h) < 30 or h[:4] != b"PK\x03\x04":
                return None
            flags, method = u16le(h, 6), u16le(h, 8)
            crc, csize, usize = u32le(h, 14), u32le(h, 18), u32le(h, 22)
            nlen, xlen = u16le(h, 26), u16le(h, 28)
            if nlen > 1024 or (flags & 8 and csize == 0):
                return None
            name = l.read(at + 30, nlen)
            data_at = at + 30 + nlen + xlen
            return flags, method, crc, csize, usize, name, data_at

        def data_ok(l, e):
            flags, method, crc, csize, usize, name, data_at = e
            if csize > 512 * 1024 * 1024:
                return False
            if method == 0:
                d = l.read(data_at, csize)
                return len(d) == csize and zlib.crc32(d) & 0xffffffff == crc
            if method == 8:
                dec, c, pos, got = zlib.decompressobj(-15), 0, 0, 0
                while pos < csize:
                    piece = l.read(data_at + pos, min(65536, csize - pos))
                    if not piece:
                        return False
                    try:
                        out = dec.decompress(piece)
                    except zlib.error:
                        return False
                    c = zlib.crc32(out, c)
                    got += len(out)
                    pos += len(piece)
                out = dec.flush()
                c = zlib.crc32(out, c)
                got += len(out)
                return (c & 0xffffffff) == crc and got == usize
            return True  # méthode inconnue : pas de vérification

        while True:
            if self.stop and self.stop():
                return None
            sig = lay.read(lo, 4)
            if sig == b"PK\x03\x04":
                e = entry(lay, lo)
                if e is None:
                    break
                if not data_ok(lay, e):
                    if n_entries == 0 and len(lay.frags) == 1 and e[3] > 64 * 1024 * 1024:
                        return None
                    new = self._zip_gap(lay, e)
                    if new is None:
                        if n_entries == 0:
                            return None
                        return Carved(self._zip_ext(names), lay.finish(lo), "partiel", "archive incomplète")
                    lay, rebuilt = new, True
                    continue
                names.append(e[5])
                n_entries += 1
                lo = e[6] + e[3]
                if e[0] & 8:  # descripteur de données
                    d = lay.read(lo, 4)
                    lo += 16 if d == b"PK\x07\x08" else 12
            elif sig == b"PK\x01\x02":
                h = lay.read(lo, 46)
                if len(h) < 46:
                    break
                lo += 46 + u16le(h, 28) + u16le(h, 30) + u16le(h, 32)
            elif sig == b"PK\x05\x06":
                h = lay.read(lo, 22)
                lo += 22 + (u16le(h, 20) if len(h) == 22 else 0)
                return Carved(self._zip_ext(names), lay.finish(lo), "reconstruit" if rebuilt else "complet")
            else:
                if n_entries == 0:
                    return None
                at = lo
                new = self.gaps.search(lay, lay.phys(at), lay.phys(at) + 4,
                                       lambda t: t.read(at, 4) in (b"PK\x01\x02", b"PK\x05\x06", b"PK\x03\x04"),
                                       self.stop)
                if new is None:
                    return Carved(self._zip_ext(names), lay.finish(lo), "partiel", "archive incomplète")
                lay, rebuilt = new, True
        return None

    def _zip_gap(self, lay, e):
        """Recolle une entrée ZIP fragmentée : on garde l'état du décompresseur
        à la coupure, puis on essaie chaque suite possible (échec rapide)."""
        flags, method, crc, csize, usize, name, data_at = e
        if method not in (0, 8) or len(lay.frags) >= self.gaps.max_frags:
            return None
        cs = self.gaps.cs
        # 1) où la décompression échoue-t-elle ?
        err_lo, pos = data_at + csize, 0
        if method == 8:
            d = zlib.decompressobj(-15)
            while pos < csize:
                piece = lay.read(data_at + pos, min(4096, csize - pos))
                if not piece:
                    break
                try:
                    d.decompress(piece)
                except zlib.error:
                    err_lo = data_at + pos + len(piece)
                    break
                pos += len(piece)
                if d.eof and pos < csize:      # fin de flux prématurée = données étrangères
                    err_lo = data_at + pos
                    break
        p_err = lay.phys(min(err_lo, data_at + csize))
        deadline = time.monotonic() + self.gaps.budget
        p_start = lay.phys(data_at)
        for c in reversed(self.gaps.boundaries(lay, max(p_start + 1, p_err - 64 * cs), p_err)):
            lc = lay.logical_of_phys_in_last(c)
            first = lay.read(data_at, lc - data_at)
            dec = zlib.decompressobj(-15) if method == 8 else None
            try:
                out = dec.decompress(first) if dec else first
            except zlib.error:
                continue
            c0, got0 = zlib.crc32(out), len(out)
            rest = csize - (lc - data_at)
            for g in range(1, self.gaps.max_gap + 1):
                if (self.stop and self.stop()) or (g & 31 == 0 and time.monotonic() > deadline):
                    return None
                resume = c + g * cs
                if resume + rest > self.src.size:
                    break
                d2 = dec.copy() if dec else None
                c1, got, p, ok = c0, got0, 0, True
                while p < rest:
                    piece = self.src.read(resume + p, min(4096, rest - p))
                    try:
                        o = d2.decompress(piece) if d2 else piece
                    except zlib.error:
                        ok = False
                        break
                    c1 = zlib.crc32(o, c1)
                    got += len(o)
                    p += len(piece)
                if not ok:
                    continue
                if d2:
                    o = d2.flush()
                    c1, got = zlib.crc32(o, c1), got + len(o)
                if (c1 & 0xffffffff) == crc and got == usize:
                    t = lay.copy()
                    t.split(c, resume)
                    return t
        return None

    @staticmethod
    def _zip_ext(names):
        joined = b"\n".join(names)
        if b"word/" in joined: return "docx"
        if b"xl/" in joined: return "xlsx"
        if b"ppt/" in joined: return "pptx"
        if b"AndroidManifest.xml" in joined: return "apk"
        if b"META-INF/MANIFEST.MF" in joined: return "jar"
        if names and names[0] == b"mimetype":
            if b"content.xml" in joined:
                return "odt"
            return "epub"
        return "zip"

    # ── RIFF : WAV / AVI / WEBP ─────────────────────────────────────────────
    def riff(self, off):
        h = self.src.read(off, 12)
        if len(h) < 12 or h[:4] != b"RIFF":
            return None
        size, kind = u32le(h, 4) + 8, h[8:12]
        ext = {b"WAVE": "wav", b"AVI ": "avi", b"WEBP": "webp"}.get(kind)
        if not ext or size < 44:
            return None
        sub = self.src.read(off + 12, 4)
        if not sub.isalnum() and sub not in (b"fmt ", b"LIST", b"VP8 ", b"VP8L", b"VP8X", b"JUNK"):
            return None
        return Carved(ext, [(off, size)], "complet")

    # ── MP4 / MOV / M4A / HEIC / 3GP : structure en « boîtes » ──────────────
    BOXES = {b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"uuid", b"pdin", b"moof",
             b"mfra", b"meta", b"styp", b"sidx", b"pnot", b"udta", b"junk", b"iinf", b"iloc"}

    def mp4(self, off):
        s = self.src
        h = s.read(off, 12)
        if len(h) < 12 or h[4:8] != b"ftyp":
            return None
        brand = h[8:12]
        ext = "mp4"
        if brand == b"qt  ": ext = "mov"
        elif brand in (b"M4A ", b"M4B "): ext = "m4a"
        elif brand in (b"heic", b"heix", b"mif1", b"msf1"): ext = "heic"
        elif brand.startswith(b"3g"): ext = "3gp"
        p, seen = off, set()
        while True:
            b = s.read(p, 16)
            if len(b) < 8:
                break
            size, t = u32be(b), b[4:8]
            if t not in self.BOXES:
                break
            if size == 1:
                if len(b) < 16:
                    break
                size = struct.unpack_from(">Q", b, 8)[0]
            elif size == 0:
                size = s.size - p
            if size < 8 or p + size > s.size:
                return Carved(ext, [(off, s.size - off)], "partiel") if b"mdat" in seen else None
            seen.add(t)
            p += size
        if b"moov" in seen or b"mdat" in seen or ext == "heic":
            st = "complet" if (b"moov" in seen and b"mdat" in seen) or ext == "heic" else "partiel"
            return Carved(ext, [(off, p - off)], st)
        return None

    # ── MP3 avec étiquette ID3 ──────────────────────────────────────────────
    BR = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
          2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
    SR = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}

    def mp3(self, off):
        s = self.src
        h = s.read(off, 10)
        if len(h) < 10 or h[:3] != b"ID3" or h[3] > 4 or any(x & 0x80 for x in h[6:10]):
            return None
        tag = (h[6] << 21) | (h[7] << 14) | (h[8] << 7) | h[9]
        p = off + 10 + tag + (10 if h[5] & 0x10 else 0)
        frames, limit = 0, off + 64 * 1024 * 1024
        while p < limit:
            f = s.read(p, 4)
            if len(f) < 4 or f[0] != 0xff or (f[1] & 0xe0) != 0xe0:
                if f[:1] == b"\x00" and frames:
                    z = s.read(p, 4096).lstrip(b"\x00")   # remplissage éventuel
                    if z[:2] and z[0] == 0xff:
                        p += 4096 - len(z)
                        continue
                break
            ver, layer = (f[1] >> 3) & 3, (f[1] >> 1) & 3
            bri, sri, pad = f[2] >> 4, (f[2] >> 2) & 3, (f[2] >> 1) & 1
            if ver == 1 or layer != 1 or bri in (0, 15) or sri == 3:
                break
            br = self.BR[1 if ver == 3 else 2][bri] * 1000
            sr = self.SR[ver][sri]
            ln = (144 if ver == 3 else 72) * br // sr + pad
            if ln < 24:
                break
            p += ln
            frames += 1
        if frames < 10:
            return None
        if s.read(p, 3) == b"TAG":
            p += 128
        return Carved("mp3", [(off, p - off)], "complet")

    # ── SQLite (historiques, contacts, messageries…) ────────────────────────
    def sqlite(self, off):
        h = self.src.read(off, 100)
        if len(h) < 100 or not h.startswith(b"SQLite format 3\x00"):
            return None
        ps = u16be(h, 16)
        ps = 65536 if ps == 1 else ps
        if ps < 512 or ps & (ps - 1):
            return None
        pages = u32be(h, 28)
        if not pages or u32be(h, 24) != u32be(h, 92) or pages * ps > 4 * 1024 ** 3:
            return None
        return Carved("sqlite", [(off, pages * ps)], "complet")


# Signatures : (préfixe, décalage, famille)
SIGNATURES = [
    (b"\xff\xd8\xff", 0, "jpg"), (b"\x89PNG\r\n\x1a\n", 0, "png"),
    (b"GIF87a", 0, "gif"), (b"GIF89a", 0, "gif"), (b"BM", 0, "bmp"),
    (b"%PDF-", 0, "pdf"), (b"PK\x03\x04", 0, "zip"), (b"RIFF", 0, "riff"),
    (b"ftyp", 4, "mp4"), (b"ID3", 0, "mp3"), (b"SQLite format 3\x00", 0, "sqlite"),
]



# ═════════════════════════════════════════════════════════════════════════════
#  Intégration The Sleuth Kit (facultative) — https://www.sleuthkit.org
#  Partitions, systèmes de fichiers, fichiers supprimés avec leur nom d'origine,
#  flux NTFS, chronologie, images E01 / VHD / VMDK / AFF.
# ═════════════════════════════════════════════════════════════════════════════

CONTAINER_EXT = (".e01", ".ex01", ".s01", ".l01", ".vhd", ".vhdx", ".vmdk", ".aff", ".afd", ".afm")


def tsk_tools():
    return {t: shutil.which(t) for t in ("mmls", "fsstat", "fls", "icat", "img_cat")}


def tsk_available():
    t = tsk_tools()
    return all(t[x] for x in ("mmls", "fsstat", "fls", "icat"))


def tsk_install_hint():
    if WINDOWS:
        return "téléchargez The Sleuth Kit pour Windows (sleuthkit.org) et ajoutez son dossier bin au PATH"
    ids = ""
    try:
        for line in open("/etc/os-release", encoding="utf-8"):
            if line.startswith(("ID=", "ID_LIKE=")):
                ids += " " + line.split("=", 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    for keys, cmd in ((("fedora", "rhel", "centos"), "sudo dnf install sleuthkit"),
                      (("debian", "ubuntu", "mint"), "sudo apt install sleuthkit"),
                      (("arch", "manjaro", "endeavouros"), "sudo pacman -S sleuthkit"),
                      (("suse", "opensuse"), "sudo zypper install sleuthkit"),
                      (("gentoo",), "sudo emerge app-forensics/sleuthkit"),
                      (("void",), "sudo xbps-install sleuthkit"),
                      (("nixos",), "nix-env -iA nixpkgs.sleuthkit")):
        if any(k in ids for k in keys):
            return cmd
    return "installez le paquet « sleuthkit » de votre distribution"


def _run(cmd, timeout=600):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def tsk_partitions(src):
    """Partitions trouvées par mmls (DOS, GPT, BSD, Mac, Sun). [(début_secteur, taille, description)]"""
    rc, out, _ = _run(["mmls", src], 120)
    parts, unit = [], 512
    if rc == 0:
        m = re.search(r"Units are in (\d+)-byte sectors", out)
        if m:
            unit = int(m.group(1))
        for line in out.splitlines():
            m = re.match(r"^\s*\d+:\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.*)$", line)
            if not m or m.group(1) in ("Meta", "-------"):
                continue
            parts.append((int(m.group(2)), int(m.group(4)), m.group(5).strip()))
    return parts, unit, out if rc == 0 else ""


def tsk_fstype(src, sector_off):
    rc, out, _ = _run(["fsstat", "-o", str(sector_off), src], 120)
    if rc != 0:
        return None, ""
    m = re.search(r"File System Type:\s*(.+)", out)
    return (m.group(1).strip() if m else "inconnu"), out


def _safe_rel(path):
    parts = []
    for p in path.replace("\\", "/").split("/"):
        p = p.replace("\x00", "").strip()
        if p in ("", ".", ".."):
            continue
        p = re.sub(r'[<>:"|?*\x01-\x1f]', "_", p)[:200].rstrip(" .") or "_"
        if p.split(".")[0].upper() in ("CON", "PRN", "AUX", "NUL") or re.match(r"^(COM|LPT)\d$", p.split(".")[0].upper()):
            p = "_" + p
        parts.append(p)
    return os.path.join(*parts) if parts else "sans_nom"


def tsk_recover(src, out_root, job, hashdb):
    """Retrouve les fichiers supprimés AVEC leur nom et dossier d'origine."""
    parts, unit, mmls_txt = tsk_partitions(src)
    candidates = [(p[0], p[2]) for p in parts] or [(0, "volume entier")]
    report = ["Mosaïk — analyse des partitions et systèmes de fichiers (The Sleuth Kit)", "", mmls_txt or "(pas de table de partitions : analyse du volume entier)", ""]
    timeline = []
    base = os.path.join(out_root, "Noms d'origine")
    n_ok = 0
    for idx, (start, desc) in enumerate(candidates):
        if job.stop_flag:
            break
        fstype, fsinfo = tsk_fstype(src, start)
        if not fstype:
            continue
        label = "partition%d_%s" % (idx + 1, re.sub(r"\W+", "_", fstype).strip("_"))
        job.say("Partition %d : %s (début secteur %d) — lecture des noms de fichiers…" % (idx + 1, fstype, start))
        report += ["── %s : %s ──" % (label, desc), fsinfo[:4000], ""]
        rc, body, err = _run(["fls", "-r", "-m", "/", "-o", str(start), src], 3600)
        if rc != 0 and not body:
            job.say("  fls a échoué : %s" % err.strip()[:200])
            continue
        deleted = []
        for line in body.splitlines():
            f = line.split("|")
            if len(f) < 11:
                continue
            name = "|".join(f[1:-9])
            inode, mode, size = f[-9], f[-8], f[-5]
            times = f[-4:]   # atime, mtime, ctime, crtime
            is_del = name.endswith(" (deleted)")
            if name.endswith(" (deleted-realloc)"):
                continue
            clean = name[:-10] if is_del else name
            try:
                sz = int(size)
                at, mt, ct, bt = (int(x) for x in times)
            except ValueError:
                continue
            timeline.append((mt, at, ct, bt, sz, is_del, label, clean))
            if is_del and mode.startswith("r/") and sz > 0 and not inode.startswith("0"):
                deleted.append((inode, clean, sz, at, mt))
        job.say("  %d fichier(s) supprimé(s) avec nom retrouvé(s)" % len(deleted))
        for i, (inode, path, sz, at, mt) in enumerate(deleted):
            if job.stop_flag:
                break
            dest = os.path.join(base, label, _safe_rel(path))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.exists(dest):
                root, ext = os.path.splitext(dest)
                dest = "%s_%s%s" % (root, inode.replace("-", "_"), ext)
            try:
                with open(dest, "wb") as fh:
                    subprocess.run(["icat", "-r", "-o", str(start), src, inode],
                                       stdout=fh, stderr=subprocess.DEVNULL, timeout=3600)
            except (OSError, subprocess.TimeoutExpired):
                continue
            got = os.path.getsize(dest)
            if got == 0:
                os.remove(dest)
                continue
            try:
                os.utime(dest, (at or mt, mt or at))
            except OSError:
                pass
            status = "complet" if got >= sz else "partiel"
            ext = os.path.splitext(dest)[1].lower().lstrip(".")
            md5, sha = file_hashes(dest)
            known = bool(hashdb) and (md5 in hashdb or sha in hashdb)
            with job.lock:
                job.counts["Noms d'origine"] = job.counts.get("Noms d'origine", 0) + 1
                job.files.append({"id": len(job.files), "name": os.path.basename(dest), "cat": "Noms d'origine",
                                  "ext": ext, "size": got, "status": status, "frags": 0, "offset": -1,
                                  "note": "%s:%s" % (label, path), "path": dest, "cell": -1,
                                  "md5": md5, "sha256": sha, "known": known, "origin": path})
            n_ok += 1
            job.message = "Extraction %d / %d (%s)" % (i + 1, len(deleted), label)
    job.message = ""
    with open(os.path.join(out_root, "partitions.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report))
    if timeline:
        timeline.sort()
        iso = lambda t: datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S") if t > 0 else ""
        with open(os.path.join(out_root, "chronologie.csv"), "w", encoding="utf-8") as fh:
            fh.write("modifie;acces;change;cree;taille;supprime;partition;chemin\n")
            for mt, at, ct, bt, sz, d, lab, pth in timeline:
                fh.write('%s;%s;%s;%s;%d;%s;%s;"%s"\n' % (iso(mt), iso(at), iso(ct), iso(bt), sz,
                                                          "oui" if d else "non", lab, pth.replace('"', "'")))
        job.say("Chronologie de %d fichiers enregistrée (chronologie.csv)" % len(timeline))
    return n_ok


def file_hashes(path):
    import hashlib
    m, s = hashlib.md5(), hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1024 * 1024), b""):
            m.update(b)
            s.update(b)
    return m.hexdigest(), s.hexdigest()


def load_hashdb(path):
    """Base de hachages : NSRL, HashKeeper, sortie de md5sum/sha256sum… (une empreinte par ligne)."""
    db = set()
    if not path:
        return db
    rx = re.compile(r"\b([0-9a-fA-F]{64}|[0-9a-fA-F]{40}|[0-9a-fA-F]{32})\b")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            for h in rx.findall(line):
                db.add(h.lower())
    return db

# ═════════════════════════════════════════════════════════════════════════════
#  Sécurité : ne jamais écrire sur le disque qu'on analyse
# ═════════════════════════════════════════════════════════════════════════════

def _sys_disks(sysdir):
    """Ensemble des disques physiques sous un périphérique bloc (LVM, RAID, LUKS inclus)."""
    out = set()
    try:
        real = os.path.realpath(sysdir)
    except OSError:
        return out
    out.add(real)
    slaves = os.path.join(real, "slaves")
    if os.path.isdir(slaves):
        for s in os.listdir(slaves):
            out |= _sys_disks(os.path.join(slaves, s))
    parent = os.path.dirname(real)
    if os.path.exists(os.path.join(parent, "dev")) and os.path.basename(os.path.dirname(parent)) == "block":
        out.add(parent)
    return out


def same_physical_device(source_path, out_dir):
    if WINDOWS:
        sp = source_path.upper()
        m = re.match(r"^\\\\\.\\PHYSICALDRIVE(\d+)$", sp)
        if not m and not re.match(r"^\\\\\.\\[A-Z]:$", sp):
            return False                      # image disque : pas de risque
        out_disk = windows_disk_of(out_dir)
        if m:
            return out_disk is not None and int(m.group(1)) == int(out_disk)
        m = re.match(r"^\\\\\.\\([A-Z]):$", sp)
        if m:
            if os.path.splitdrive(os.path.abspath(out_dir))[0].upper().startswith(m.group(1)):
                return True
            src_disk = windows_disk_of(m.group(1) + ":\\")
            return src_disk is not None and src_disk == out_disk
        return False
    try:
        st = os.stat(source_path)
        if not os.path.exists(out_dir):
            out_dir = os.path.dirname(os.path.abspath(out_dir)) or "/"
        od = os.stat(out_dir).st_dev
    except OSError:
        return False
    import stat as _st
    if _st.S_ISBLK(st.st_mode):
        a = _sys_disks("/sys/dev/block/%d:%d" % (os.major(st.st_rdev), os.minor(st.st_rdev)))
    else:  # image disque : interdit seulement d'écrire dans la même partition ? non, autorisé
        return False
    b = _sys_disks("/sys/dev/block/%d:%d" % (os.major(od), os.minor(od)))
    for x in a:
        for y in b:
            if x == y or x.startswith(y + "/") or y.startswith(x + "/"):
                return True
    return False


def list_devices():
    if WINDOWS:
        return list_devices_windows()
    devs = []
    try:
        raw = subprocess.run(["lsblk", "-J", "-b", "-o",
                              "NAME,PATH,SIZE,MODEL,TYPE,FSTYPE,LABEL,MOUNTPOINT,RM,TRAN,VENDOR"],
                             capture_output=True, text=True, timeout=10).stdout
        data = json.loads(raw)

        def walk(nodes, parent=None):
            for n in nodes:
                if n.get("type") in ("disk", "part", "crypt", "lvm", "raid1", "raid0", "raid5", "md"):
                    if not (n.get("name", "").startswith(("loop", "zram", "ram", "sr"))
                            and n.get("type") == "disk" and not n.get("size")):
                        devs.append({
                            "path": n.get("path") or "/dev/" + n["name"],
                            "name": n.get("name"), "type": n.get("type"),
                            "size": int(n.get("size") or 0),
                            "model": " ".join(x for x in ((n.get("vendor") or "").strip(), (n.get("model") or "").strip())
                                              if x and not re.match(r"^0x[0-9a-f]+$", x, re.I))
                                     or (parent or {}).get("model") or "",
                            "fs": n.get("fstype") or "", "label": n.get("label") or "",
                            "mount": n.get("mountpoint") or "",
                            "removable": str(n.get("rm")) in ("1", "True", "true"),
                            "tran": n.get("tran") or (parent or {}).get("tran") or "",
                            "parent": (parent or {}).get("name", ""),
                        })
                walk(n.get("children") or [], n)

        walk(data.get("blockdevices", []))
    except Exception:
        for name in sorted(os.listdir("/sys/block")):
            if name.startswith(("loop", "ram", "zram")):
                continue
            try:
                size = int(open("/sys/block/%s/size" % name).read()) * 512
            except Exception:
                size = 0
            devs.append({"path": "/dev/" + name, "name": name, "type": "disk", "size": size,
                         "model": "", "fs": "", "label": "", "mount": "", "removable": False,
                         "tran": "", "parent": ""})
    return [d for d in devs if d["size"] > 0 and not d["name"].startswith(("zram", "ram"))]


# ═════════════════════════════════════════════════════════════════════════════
#  Moteur : clonage tolérant aux erreurs + analyse + mosaïque
# ═════════════════════════════════════════════════════════════════════════════

class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.running = False
        self.stop_flag = False
        self.phase = "attente"       # attente | clonage | analyse | termine | erreur | arrete
        self.message = ""
        self.source = ""
        self.size = 0
        self.pos = 0
        self.started = 0.0
        self.cells = [C_UNREAD] * MAP_CELLS
        self.files = []
        self.counts = {}
        self.bad = 0
        self.out_dir = ""
        self.log = []
        self.hashdb = set()
        self.on_tick = None       # rappel de progression (version en ligne)
        self.on_file = None       # rappel à chaque fichier récupéré (version en ligne)

    # ── mosaïque ──
    def mark(self, off, length, state):
        if self.size <= 0 or length <= 0:
            return
        a = int(off * MAP_CELLS // self.size)
        b = int(max(off, off + length - 1) * MAP_CELLS // self.size)
        for i in range(max(0, a), min(MAP_CELLS - 1, b) + 1):
            if PRIORITY[state] >= PRIORITY[self.cells[i]]:
                self.cells[i] = state

    def say(self, msg):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.log.append("%s  %s" % (stamp, msg))
            self.log = self.log[-200:]

    def status(self, since=0):
        with self.lock:
            el = time.time() - self.started if self.started else 0
            speed = self.pos / el if el > 1 else 0
            eta = (self.size - self.pos) / speed if speed > 0 else 0
            return {
                "phase": self.phase, "message": self.message, "running": self.running,
                "source": self.source, "size": self.size, "pos": self.pos,
                "speed": speed, "eta": eta, "elapsed": el, "map": "".join(self.cells),
                "files": self.files[since:], "total_files": len(self.files),
                "counts": self.counts, "bad": self.bad, "out": self.out_dir,
                "log": self.log[-12:],
            }


JOB = Job()


def human(n):
    for u in ("o", "Ko", "Mo", "Go", "To"):
        if abs(n) < 1024 or u == "To":
            return ("%.1f %s" % (n, u)).replace(".0 ", " ")
        n /= 1024.0


def chown_tree(path, owner):
    if not owner or not hasattr(os, "chown"):
        return
    uid, gid = owner
    for root, dirs, files in os.walk(path):
        for x in [root] + [os.path.join(root, f) for f in files]:
            try:
                os.chown(x, uid, gid)
            except OSError:
                pass


def clone_image(src_path, img_path, job):
    """Copie le disque vers une image en sautant les zones abîmées (méthode ddrescue)."""
    src = Source(src_path)
    job.size = src.size
    job.say("Clonage de %s (%s) vers %s" % (src_path, human(src.size), img_path))
    bad_zones = []
    chunk, pos = 1024 * 1024, 0
    with open(img_path, "wb") as out:
        out.truncate(src.size)
        # 1er passage : rapide, on saute les zones qui résistent
        skip = chunk
        while pos < src.size and not job.stop_flag:
            n = min(chunk, src.size - pos)
            try:
                b = pread(src.fd, n, pos)
                if len(b) < n:
                    raise OSError("lecture courte")
                out.seek(pos)
                out.write(b)
                job.mark(pos, n, C_EMPTY if not b.strip(b"\0") else C_DATA)
                skip = chunk
                pos += n
            except OSError:
                bad_zones.append((pos, min(skip, src.size - pos)))
                job.mark(pos, min(skip, src.size - pos), C_BAD)
                pos += skip
                skip = min(skip * 2, 64 * 1024 * 1024)
            job.pos = pos
        # 2e passage (« trimming » façon ddrescue) : on grignote chaque zone abîmée
        # par ses deux bords, secteur par secteur, et on abandonne au bout de
        # 8 échecs consécutifs ou du budget de temps. Le cœur des zones mortes
        # n'est jamais relu (c'est ce qui prenait des heures).
        if bad_zones and not job.stop_flag:
            job.say("%d zone(s) abîmée(s) : récupération des bords (max. 5 min)" % len(bad_zones))
            deadline = time.monotonic() + 300
            for a, ln in bad_zones:
                for direction in (1, -1):
                    p = a if direction == 1 else a + ln - SECTOR
                    fails = 0
                    while a <= p < a + ln and fails < 8 and not job.stop_flag and time.monotonic() < deadline:
                        try:
                            b = pread(src.fd, SECTOR, p)
                            out.seek(p)
                            out.write(b)
                            fails = 0
                        except OSError:
                            fails += 1
                            job.bad += 1
                        p += direction * SECTOR
    src.close()
    return bad_zones


def run_scan(cfg, job):
    owner = cfg.get("owner")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = os.path.join(cfg["out"], "mosaik-" + stamp)
    os.makedirs(out_root, exist_ok=True)
    job.out_dir = out_root
    source = cfg["source"]
    hashdb = set()
    try:
        if cfg.get("hashdb"):
            hashdb = load_hashdb(os.path.expanduser(cfg["hashdb"]))
            job.say("Base de hachages chargée : %d empreintes" % len(hashdb))
        job.hashdb = hashdb
        container = source.lower().endswith(CONTAINER_EXT)
        if container:
            if not shutil.which("img_cat"):
                raise RuntimeError("Les images E01 / VHD / VMDK / AFF nécessitent The Sleuth Kit (%s)." % tsk_install_hint())
            cfg["clone"] = False
        if cfg.get("clone"):
            job.phase = "clonage"
            img = os.path.join(out_root, "image-disque.img")
            st = shutil.disk_usage(out_root)
            _s = Source(source)
            src_size = _s.size
            _s.close()
            if st.free < src_size + 64 * 1024 * 1024:
                raise RuntimeError("Pas assez de place pour l'image : il faut %s, il reste %s"
                                   % (human(src_size), human(st.free)))
            job.started = time.time()
            clone_image(source, img, job)
            if job.stop_flag:
                raise KeyboardInterrupt
            job.say("Image créée. Les fichiers seront extraits de l'image (le disque n'est plus sollicité).")
            source = img
            job.cells = [c if c == C_BAD else C_UNREAD for c in job.cells]

        if cfg.get("tsk", True) and tsk_available() and not job.stop_flag:
            job.phase = "noms"
            job.started = time.time()
            job.say("The Sleuth Kit : recherche des fichiers supprimés avec leur nom d'origine")
            n = tsk_recover(source, out_root, job, hashdb)
            job.say("%d fichier(s) récupéré(s) avec leur nom d'origine" % n)
        if container and cfg.get("carve", True) and not job.stop_flag:
            raw = os.path.join(out_root, "image-brute.img")
            job.say("Conversion de l'image %s en image brute pour la recherche par signature…" % os.path.basename(source))
            with open(raw, "wb") as fh:
                subprocess.run(["img_cat", source], stdout=fh, stderr=subprocess.DEVNULL)
            source = raw
        if not cfg.get("carve", True) or job.stop_flag:
            write_report(out_root, job)
            chown_tree(out_root, owner)
            job.phase = "arrete" if job.stop_flag else "termine"
            job.pos = job.size
            return
        job.phase = "analyse"
        src = Source(source, on_bad=lambda o, n: job.mark(o, n, C_BAD))
        job.size, job.pos, job.started = src.size, 0, time.time()
        families = set(cfg.get("types") or FAMILIES.keys())
        gaps = GapSearch(cluster=int(cfg.get("cluster", 4096)),
                         max_gap_clusters=int(cfg.get("max_gap", 1024)))
        carv = Carvers(src, gaps, stop=lambda: job.stop_flag)
        min_size = int(cfg.get("min_size", 2048))
        aligned = cfg.get("aligned", True)
        sigs = [s for s in SIGNATURES if s[2] in families]
        by2 = {}
        for prefix, rel, fam in sigs:
            key = prefix[:2] if rel == 0 else None
            by2.setdefault(key, []).append((prefix, rel, fam))
        job.say("Analyse de %s (%s) — %d formats recherchés" % (source, human(src.size), len(families)))
        skip_until = 0
        pos = 0
        seen = set()
        # Lecture anticipée : le bloc suivant est lu pendant l'analyse du bloc courant
        def fetch(p):
            return src._raw(p, min(SCAN_CHUNK, src.size - p)) if p < src.size else b""

        class _Now:                          # navigateur : pas de fil d'exécution
            def __init__(self, v): self.v = v
            def result(self): return self.v

        if WEB:
            pool = None
            submit = lambda p: _Now(fetch(p))
        else:
            from concurrent.futures import ThreadPoolExecutor
            pool = ThreadPoolExecutor(max_workers=1)
            submit = lambda p: pool.submit(fetch, p)
        fut = submit(0)
        while pos < src.size and not job.stop_flag:
            if job.on_tick:
                job.on_tick()
            cur = fut.result()
            if not cur:
                break
            main = len(cur)
            fut = submit(pos + main)
            if not cur.strip(b"\0"):          # zone vide : rien à chercher
                job.mark(pos, main, C_EMPTY)
                pos += main
                job.pos = pos
                continue
            job.mark(pos, main, C_DATA)
            cands = []
            if aligned:
                blk = cur
                start = (-pos) % SECTOR
                for i in range(start, main, SECTOR):
                    for prefix, rel, fam in by2.get(blk[i:i + 2], ()):
                        if blk.startswith(prefix, i):
                            cands.append((pos + i, fam))
                    for prefix, rel, fam in by2.get(None, ()):
                        if blk.startswith(prefix, i + rel):
                            cands.append((pos + i, fam))
            else:
                blk = cur + src._raw(pos + main, 64) if pos + main < src.size else cur
                for prefix, rel, fam in sigs:
                    i = blk.find(prefix)
                    while i != -1 and i < main + rel:
                        if i - rel >= 0:
                            cands.append((pos + i - rel, fam))
                        i = blk.find(prefix, i + 1)
                cands.sort()
            for off, fam in cands:
                if job.stop_flag:
                    break
                if off < skip_until or off in seen:
                    continue
                seen.add(off)
                try:
                    res = getattr(carv, fam)(off)
                except Exception:
                    res = None
                if not res or res.size < min_size:
                    continue
                save_file(res, off, src, out_root, job)
                f0 = res.frags[0]
                if res.status == "complet" and len(res.frags) == 1:
                    skip_until = max(skip_until, f0[0] + f0[1])
                elif res.status == "reconstruit":
                    skip_until = max(skip_until, f0[0] + f0[1])
            if len(seen) > 100000:
                seen = set(x for x in seen if x >= pos)
            pos += main
            job.pos = pos
        if pool:
            pool.shutdown(wait=True)
        job.bad = max(job.bad, src.bad_sectors)
        src.close()
        write_report(out_root, job)
        chown_tree(out_root, owner)
        if job.stop_flag:
            job.phase = "arrete"
            job.say("Analyse arrêtée. %d fichier(s) déjà récupéré(s)." % len(job.files))
        else:
            job.phase = "termine"
            job.pos = job.size
            job.say("Terminé : %d fichier(s) récupéré(s)%s" % (len(job.files), "" if WEB else " dans " + out_root))
    except KeyboardInterrupt:
        job.phase = "arrete"
        chown_tree(out_root, owner)
    except Exception as e:
        job.phase = "erreur"
        job.message = str(e)
        job.say("Erreur : %s" % e)
        chown_tree(out_root, owner)
    finally:
        job.running = False


def save_file(res, off, src, out_root, job):
    cat, state = CATEGORY.get(res.ext, ("Autres", C_DATA))
    folder = os.path.join(out_root, cat)
    os.makedirs(folder, exist_ok=True)
    suffix = {"complet": "", "reconstruit": "_reconstruit", "partiel": "_partiel"}[res.status]
    name = "%s_%012x%s.%s" % (res.ext, off, suffix, res.ext)
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        for a, ln in res.frags:
            p = a
            while p < a + ln:
                n = min(4 * 1024 * 1024, a + ln - p)
                f.write(src.read(p, n))
                p += n
        if res.tail:
            f.write(res.tail)
    for a, ln in res.frags:
        job.mark(a, ln, C_FRAG if len(res.frags) > 1 else state)
    md5, sha = file_hashes(path)
    known = md5 in job.hashdb or sha in job.hashdb
    with job.lock:
        job.counts[cat] = job.counts.get(cat, 0) + 1
        job.files.append({
            "id": len(job.files), "name": name, "cat": cat, "ext": res.ext,
            "size": res.size, "status": res.status, "frags": len(res.frags),
            "offset": off, "note": res.note, "path": path,
            "cell": int(off * MAP_CELLS // max(1, job.size)),
            "md5": md5, "sha256": sha, "known": known, "origin": "",
        })
    if len(res.frags) > 1:
        job.say("Recollé : %s (%d fragments)" % (name, len(res.frags)))
    if job.on_file:
        job.on_file(job.files[-1])


def write_report(out_root, job):
    with open(os.path.join(out_root, "rapport.csv"), "w", encoding="utf-8") as f:
        f.write("fichier;chemin_origine;type;taille;etat;fragments;position_sur_disque;md5;sha256;connu_base_hachage;dossier\n")
        for x in job.files:
            f.write('"%s";"%s";%s;%d;%s;%d;%d;%s;%s;%s;"%s"\n' % (
                x["name"].replace('"', "'"), x.get("origin", "").replace('"', "'"), x["ext"], x["size"],
                x["status"], x["frags"], x["offset"], x.get("md5", ""), x.get("sha256", ""),
                "oui" if x.get("known") else "non", os.path.dirname(x["path"])))
    with open(os.path.join(out_root, "LISEZMOI.txt"), "w", encoding="utf-8") as f:
        f.write("Récupération réalisée avec %s %s (Pixel's ASBL)\n" % (APP, VERSION))
        f.write("Source : %s\nDate : %s\nFichiers : %d\n\n" % (job.source, datetime.datetime.now(), len(job.files)))
        f.write("États :\n  complet      = fichier retrouvé en un seul morceau, vérifié\n"
                "  reconstruit  = fichier fragmenté, morceaux recollés (à vérifier en l'ouvrant)\n"
                "  partiel      = une partie manque ; le début du fichier est souvent utilisable\n\n"
                "Dossier « Noms d'origine » : fichiers supprimés retrouvés avec leur nom et leur dossier\n"
                "  (via The Sleuth Kit). chronologie.csv : activité des fichiers, à ouvrir dans un tableur.\n"
                "Autres dossiers : fichiers retrouvés par signature ; le nom indique le type et la position.\n"
                "rapport.csv contient les empreintes MD5/SHA-256 de chaque fichier.\n")


# ═════════════════════════════════════════════════════════════════════════════
#  Serveur web local (interface)
# ═════════════════════════════════════════════════════════════════════════════

TOKEN = secrets.token_urlsafe(24)
DEFAULT_OUT = os.path.expanduser("~/Mosaik-recuperation")
OWNER = None


class Handler(BaseHTTPRequestHandler):
    server_version = "Mosaik/" + VERSION

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, q):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False   # protection contre le « DNS rebinding »
        tok = self.headers.get("X-Mosaik-Token") or (q.get("t") or [""])[0]
        return secrets.compare_digest(tok, TOKEN)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/logo.svg", "/favicon.svg"):
            try:
                with open(os.path.join(HERE, "assets", "mosaik-icon.svg"), "rb") as f:
                    return self._send(200, f.read(), "image/svg+xml")
            except OSError:
                return self._send(404, b"")
        m = re.match(r"^/fonts/(Poppins-(?:Light|Regular|Medium|Bold)\.woff2)$", u.path)
        if m:
            try:
                with open(os.path.join(HERE, "assets", "fonts", m.group(1)), "rb") as f:
                    return self._send(200, f.read(), "font/woff2", {"Cache-Control": "max-age=86400"})
            except OSError:
                return self._send(404, b"")
        if not self._authorized(q):
            return self._send(403, "Accès refusé : ouvrez Mosaïk via le lien affiché au démarrage.",
                              "text/plain; charset=utf-8")
        if u.path == "/":
            with open(os.path.join(HERE, "ui.html"), "r", encoding="utf-8") as f:
                html = f.read().replace("__TOKEN__", TOKEN).replace("__VERSION__", VERSION)
            return self._send(200, html, "text/html; charset=utf-8",
                              {"Content-Security-Policy": "default-src 'self'; img-src 'self' blob:; font-src 'self'; "
                               "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"})
        if u.path == "/api/info":
            return self._send(200, {"version": VERSION, "root": is_admin(), "windows": WINDOWS,
                                    "out": DEFAULT_OUT, "families": FAMILIES,
                                    "tsk": tsk_available(), "tsk_hint": tsk_install_hint()})
        if u.path == "/api/devices":
            return self._send(200, list_devices())
        if u.path == "/api/status":
            return self._send(200, JOB.status(int((q.get("since") or ["0"])[0])))
        if u.path == "/api/file":
            try:
                fid = int((q.get("id") or ["-1"])[0])
                rec = JOB.files[fid]
                with open(rec["path"], "rb") as f:
                    data = f.read(30 * 1024 * 1024)
                mime = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "bmp": "image/bmp",
                        "webp": "image/webp"}.get(rec["ext"], "application/octet-stream")
                return self._send(200, data, mime)
            except Exception:
                return self._send(404, b"")
        return self._send(404, {"erreur": "inconnu"})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if not self._authorized({}):
            return self._send(403, {"erreur": "accès refusé"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
        except ValueError:
            return self._send(400, {"erreur": "requête invalide"})
        if u.path == "/api/start":
            return self._send(*start_job(body))
        if u.path == "/api/quit":
            JOB.stop_flag = True
            threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
            return self._send(200, {"ok": True})
        if u.path == "/api/stop":
            JOB.stop_flag = True
            JOB.say("Arrêt demandé…")
            return self._send(200, {"ok": True})
        return self._send(404, {"erreur": "inconnu"})


def start_job(cfg):
    if JOB.running:
        return 409, {"erreur": "Une analyse est déjà en cours."}
    src = (cfg.get("source") or "").strip()
    out = os.path.expanduser((cfg.get("out") or DEFAULT_OUT).strip())
    if not src or not os.path.exists(src):
        return 400, {"erreur": "Source introuvable : %s" % src}
    if not os.access(src, os.R_OK):
        return 400, {"erreur": "Lecture impossible de %s. Relancez Mosaïk avec les droits administrateur." % src}
    try:
        os.makedirs(out, exist_ok=True)
    except OSError as e:
        return 400, {"erreur": "Dossier de sortie impossible : %s" % e}
    if same_physical_device(src, out):
        return 400, {"erreur": "Le dossier de sortie est sur le disque à récupérer ! "
                               "Choisissez un autre disque (clé USB, disque externe…) pour ne rien écraser."}
    if os.path.realpath(out).startswith(os.path.realpath(src) + os.sep):
        return 400, {"erreur": "Dossier de sortie invalide."}
    JOB.reset()
    JOB.running = True
    JOB.source = src
    cfg = dict(cfg, source=src, out=out, owner=OWNER)
    if OWNER and hasattr(os, "chown"):
        try:
            os.chown(out, *OWNER)
        except OSError:
            pass
    threading.Thread(target=run_scan, args=(cfg, JOB), daemon=True).start()
    return 200, {"ok": True}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def open_browser(url):
    """Ouvre le navigateur en tant qu'utilisateur normal (jamais en root)."""
    try:
        if WINDOWS or not is_admin():
            webbrowser.open(url)
            return
    except Exception:
        pass


def serve(args):
    global OWNER, DEFAULT_OUT
    if args.owner:
        uid, gid = (int(x) for x in args.owner.split(":"))
        OWNER = (uid, gid)
    if args.sortie:
        DEFAULT_OUT = args.sortie
    port = args.port or free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/?t=%s" % (port, TOKEN)
    print("MOSAIK_URL " + url, flush=True)
    print("\n  %s %s — Pixel's ASBL" % (APP, VERSION))
    print("  Interface : %s" % url)
    print("  (Ctrl+C pour quitter)\n", flush=True)
    if not args.no_browser:
        open_browser(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    JOB.stop_flag = True


# ═════════════════════════════════════════════════════════════════════════════
#  Mode ligne de commande (serveurs, systèmes sans écran, live USB)
# ═════════════════════════════════════════════════════════════════════════════

def cli(args):
    if same_physical_device(args.cli, args.sortie or DEFAULT_OUT):
        sys.exit("Refusé : le dossier de sortie est sur le disque à récupérer.")
    cfg = {"source": args.cli, "out": args.sortie or DEFAULT_OUT, "clone": args.cloner,
           "types": args.types.split(",") if args.types else None,
           "aligned": not args.profond, "owner": None, "tsk": not args.sans_tsk,
           "carve": not args.sans_signatures, "hashdb": args.hachages}
    JOB.reset()
    JOB.running = True
    JOB.source = args.cli
    t = threading.Thread(target=run_scan, args=(cfg, JOB), daemon=True)
    t.start()
    shown = 0
    try:
        while t.is_alive():
            time.sleep(1)
            s = JOB.status()
            pct = 100.0 * s["pos"] / s["size"] if s["size"] else 0
            sys.stdout.write("\r  [%s] %5.1f %%  %s/s  fichiers : %d   " %
                             (s["phase"], pct, human(s["speed"]), s["total_files"]))
            sys.stdout.flush()
            for line in JOB.log[shown:]:
                sys.stdout.write("\n  " + line)
            shown = len(JOB.log)
    except KeyboardInterrupt:
        JOB.stop_flag = True
        t.join()
    print("\n  Résultat : %s" % JOB.out_dir)


# ═════════════════════════════════════════════════════════════════════════════
#  Lancement : élévation des droits puis ouverture du navigateur en utilisateur
# ═════════════════════════════════════════════════════════════════════════════

def relaunch_as_admin_windows(argv):
    """Windows : redemande Mosaïk avec les droits administrateur (fenêtre UAC)."""
    import ctypes
    me = os.path.realpath(__file__)
    py = sys.executable
    if py.lower().endswith("python.exe") and os.path.exists(py[:-10] + "pythonw.exe"):
        py = py[:-10] + "pythonw.exe"
    params = " ".join('"%s"' % a.replace('"', '') for a in [me] + argv)
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", py, params, None, 1)
    if rc <= 32:
        print("Droits administrateur refusés. Pour analyser une image disque : mosaik --sans-root")
        return 1
    return 0


def relaunch_as_root(argv):
    """L'utilisateur lance Mosaïk normalement ; on demande le mot de passe
    administrateur (pkexec en graphique, sinon sudo), puis on ouvre le
    navigateur avec le compte de l'utilisateur."""
    me = os.path.realpath(__file__)
    home = os.path.expanduser("~")
    extra = ["--owner", "%d:%d" % (os.getuid(), os.getgid()), "--no-browser",
             "--sortie", os.path.join(home, "Mosaik-recuperation")] + argv
    py = sys.executable or "python3"
    graphical = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    cmd = None
    if graphical and shutil.which("pkexec"):
        cmd = ["pkexec", py, me] + extra
    elif shutil.which("sudo"):
        cmd = ["sudo", py, me] + extra
    elif shutil.which("doas"):
        cmd = ["doas", py, me] + extra
    if not cmd:
        print("Impossible d'obtenir les droits administrateur (ni pkexec, ni sudo, ni doas).")
        print("Lancez : su -c '%s %s'" % (py, me))
        return 1
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, bufsize=1)
    opened = False
    try:
        for line in proc.stdout:
            if line.startswith("MOSAIK_URL ") and not opened:
                url = line.split(" ", 1)[1].strip()
                opened = True
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
                continue
            sys.stdout.write(line)
            sys.stdout.flush()
        return proc.wait()
    except KeyboardInterrupt:
        try:
            proc.send_signal(signal.SIGINT)
        except Exception:
            pass
        return 0


def main():
    ap = argparse.ArgumentParser(prog="mosaik", description="%s — récupération visuelle de fichiers" % APP)
    ap.add_argument("--cli", metavar="SOURCE", help="mode texte : disque, partition ou image à analyser")
    ap.add_argument("--sortie", metavar="DOSSIER", help="dossier où enregistrer les fichiers")
    ap.add_argument("--types", help="formats (ex. jpg,png,pdf,zip,mp4,mp3,riff,gif,bmp,sqlite)")
    ap.add_argument("--cloner", action="store_true", help="cloner d'abord le disque abîmé vers une image")
    ap.add_argument("--profond", action="store_true", help="chercher aussi hors des limites de secteur (plus lent)")
    ap.add_argument("--sans-tsk", action="store_true", help="ne pas utiliser The Sleuth Kit")
    ap.add_argument("--sans-signatures", action="store_true", help="ne pas faire la recherche par signature")
    ap.add_argument("--hachages", metavar="FICHIER", help="base de hachages (NSRL, md5sum…) pour repérer les fichiers connus")
    ap.add_argument("--sans-root", action="store_true", help="ne pas demander les droits (pour analyser une image)")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--owner", help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version="%s %s" % (APP, VERSION))
    args = ap.parse_args()

    if sys.stdout is None:                     # Mosaik.exe / pythonw : pas de console → journal
        logdir = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Mosaik")
        try:
            os.makedirs(logdir, exist_ok=True)
            sys.stdout = sys.stderr = open(os.path.join(logdir, "mosaik.log"), "w", encoding="utf-8", buffering=1)
        except OSError:
            sys.stdout = sys.stderr = open(os.devnull, "w")
    elif hasattr(sys.stdout, "reconfigure"):   # console Windows (cp1252) : pas de plantage sur les accents
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    if sys.version_info < (3, 8):
        sys.exit("Python 3.8 ou plus récent est nécessaire.")
    if args.cli:
        return cli(args)
    if not is_admin() and not args.sans_root:
        passthru = [a for a in sys.argv[1:] if a not in ("--sans-root",)]
        if WINDOWS:
            sys.exit(relaunch_as_admin_windows(passthru))
        sys.exit(relaunch_as_root(passthru))
    serve(args)


if __name__ == "__main__":
    main()
