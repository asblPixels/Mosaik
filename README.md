<div align="center">

<img src="assets/mosaik-256.png" width="180" alt="Mosaïk logo">

# 🧩 Mosaïk

### Get your files back — even in pieces.

**A simple, visual, open-source data recovery tool for every Linux distribution**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20(any%20distro)-blue.svg)](#️-supported-systems)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#️-supported-systems)
[![GUI](https://img.shields.io/badge/GUI-web%20browser-teal.svg)](#-usage)
[![The Sleuth Kit](https://img.shields.io/badge/forensics-The%20Sleuth%20Kit-orange.svg)](https://www.sleuthkit.org/)
[![CI](https://github.com/asblPixels/Mosaik/actions/workflows/ci.yml/badge.svg)](https://github.com/asblPixels/Mosaik/actions/workflows/ci.yml)

<br>

[🇬🇧 English](README.md) · [🇫🇷 Français](README.fr.md)

<br>

<img src="docs/screenshot-analyse.png" width="900" alt="Mosaïk scanning: the disk mosaic and recovered files">

</div>

---

## 📖 About

**Mosaïk** is a free, open-source file recovery tool for Linux. It brings back deleted or lost photos, documents, music and videos from hard drives, SSDs, USB sticks and memory cards — **even when they are scattered in several pieces** across the disk.

While scanning, the disk is drawn as a **mosaic** that lights up as it goes: you can see where the images, documents, empty areas, damaged sectors and re-assembled files are. Recovered files appear live, with photo previews.

> **Origin**: This project is created and maintained by **[asblPixels](https://github.com/asblPixels)** as part of its open-source software initiative. It is released under the MIT License and is free to use, modify and distribute.

### ✨ Why Mosaïk?

Existing recovery tools are either **command-line only** (PhotoRec, foremost, scalpel, The Sleuth Kit) or **paid and Windows-only**. None of them show what is happening, and most give up on **fragmented** files.

Mosaïk aims to be **the simplest possible tool**:

- 🖱️ **Three questions, one button**: which disk? what to look for? where to save? → *Start recovery*.
- 👀 **See everything**: the disk mosaic, the progress, photos coming back one by one.
- 🧩 **Pieces are put back together** — and the result is verified.
- 🐧 **Runs everywhere**: Fedora, Ubuntu, Debian, Mint, Arch, Manjaro, openSUSE, Gentoo, Void… Python 3 is all it needs.

### 🆘 Who is it for?

```
  🗑️ Deleted files   💾 Formatted stick   📷 Unreadable SD card   🔊 Clicking drive
                 ╲              │                  │                   ╱
                  ╰─────────────┴──► 🧩 Mosaïk ◄───┴──────────────────╯
                                         │
                      📁 Photos · Documents · Music · Videos recovered
```

- 👨‍👩‍👧 **Families** who lost their photos.
- 🛠️ **Repair shops and repair cafés** helping the public.
- 🏫 **Schools and trainers** teaching data recovery visually.
- 🔎 **Technicians** who want The Sleuth Kit with a simple interface.

## 🎯 Features

### 🧩 Signature carving and fragment re-assembly

- 🔍 **Signature search**: finds files even when the file system is gone (formatted disk, deleted partition, corrupted partition table).
- 🧩 **Fragmented file re-assembly** ("gap carving"): when a file is cut, Mosaïk looks for its continuation further on the disk and **verifies** the result:
  - **PNG**: CRC check of every chunk → **certain** re-assembly;
  - **Word, Excel, PowerPoint, LibreOffice, ZIP, EPUB**: CRC check of every inner file → **certain** re-assembly;
  - **JPEG**: structure and restart-marker analysis → **likely** re-assembly, check by opening the photo.
- 🖼️ **Usable partial photos**: a photo missing its end is closed properly so it displays up to the lost area.
- ⚡ **Fast**: sector-aligned scanning, pure Python, no external library.

### 🏷️ The Sleuth Kit integration (original names)

When [The Sleuth Kit](https://www.sleuthkit.org/sleuthkit/desc.php) is installed, Mosaïk uses it automatically:

- 🗂️ **Deleted files with their original name and folder** (`Photos/Holidays 2023/beach.jpg` instead of `jpg_0001a000.jpg`), with their **original dates**.
- 💽 **Partitions**: DOS/MBR, GPT, BSD, Mac and Sun tables.
- 📂 **File systems**: NTFS, FAT12/16/32, exFAT, ext2/ext3/ext4, HFS+, APFS, ISO 9660, UFS 1/2, YAFFS2.
- 🕵️ **NTFS Alternate Data Streams** (data hidden inside a file).
- 🕒 **Timeline** of all file activity (`chronologie.csv`, open it in any spreadsheet).
- 🧱 **Forensic images**: E01 (EnCase), VHD, VMDK and AFF, on top of raw `.img` / `.dd` images.

### 🩺 Failing drives

- 💿 **"Copy first" mode**: the disk is read **only once** into an image; unreadable areas are skipped, then retried sector by sector (ddrescue method). A tired drive is stressed as little as possible.
- 🟥 **Bad sectors** are shown in red on the mosaic.

### 🔐 Hashes and hash databases

- #️⃣ **MD5** and **SHA-256** of every recovered file (in `rapport.csv`).
- 📚 Optional **hash database** (NIST NSRL, HashKeeper, `md5sum` / `sha256sum` output): known files (system files, software) are flagged so you can set them aside.

### 🛡️ Safety

- 🔒 The source disk is opened **read-only** — nothing is ever written to it.
- 🚫 Mosaïk **refuses to save onto the disk being scanned**, even behind LVM, RAID or LUKS.
- 🏠 The interface is reachable **only from the computer itself** (`127.0.0.1`), protected by a random token and against DNS rebinding.
- 👤 The browser opens under **your own account**, never as root; recovered files belong to you.
- 🧯 Malicious file names (`../../etc/passwd`) are neutralised.

## 📋 Formats found by signature

| Family | Formats | Fragment re-assembly |
|---|---|---|
| 📷 Images | JPEG, PNG, GIF, BMP, WEBP, HEIC | ✅ PNG (certain) · ✅ JPEG (likely) |
| 📄 Documents | PDF, DOCX, XLSX, PPTX, ODT, ODS, ODP, EPUB | ✅ Office / LibreOffice formats (certain) |
| 🗜️ Archives | ZIP, JAR, APK | ✅ (certain) |
| 🎵 Audio | MP3 (ID3), WAV, M4A | — |
| 🎬 Video | MP4, MOV, AVI, 3GP | — |
| 🗃️ Databases | SQLite (browser history, messaging apps, contacts) | — |

With The Sleuth Kit, **every type of deleted file** is recovered with its name, whatever its format.

## 🖼️ Screenshots

| Setup | Scan |
|---|---|
| <img src="docs/screenshot-setup.png" width="440" alt="Choosing the disk, file types and destination"> | <img src="docs/screenshot-analyse.png" width="440" alt="Disk mosaic and recovered files"> |

The interface is in French; English is planned.

## 🖥️ Supported systems

| Component | Requirement |
|---|---|
| **OS** | Any Linux distribution (Fedora, RHEL, Ubuntu, Debian, Mint, Arch, Manjaro, openSUSE, Gentoo, Void, NixOS, Alpine…) |
| **Python** | 3.8 or newer (already installed on nearly every distribution) |
| **Libraries** | **None** — Python standard library only |
| **Interface** | Any web browser (Firefox, Chromium, Chrome, Epiphany…); text mode for headless systems |
| **Desktop** | GNOME, KDE Plasma, Xfce, Cinnamon, MATE, LXQt… X11 and Wayland |
| **Architecture** | x86_64, ARM (Raspberry Pi), etc. |
| **Privileges** | Admin password to read a disk (pkexec, sudo or doas); none to scan an image file |
| **Optional** | `sleuthkit` for original names, partitions, timeline and E01/VHD/VMDK images |
| **Disk space** | Room for the recovered files; "failing drive" mode: plus the size of the disk |

## 🚀 Installation

### ⚡ One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/asblPixels/Mosaik/main/scripts/install-linux.sh | bash
```

The script:
1. detects your distribution;
2. checks Python 3 and offers to install **The Sleuth Kit**;
3. downloads Mosaïk;
4. adds **Mosaïk** to the applications menu.

> ℹ️ While the repository is **private**, this command needs GitHub authentication — use the manual install below.

### Step 1 — Download

```bash
git clone https://github.com/asblPixels/Mosaik.git
cd Mosaik
```

> No `git`? Download the ZIP (**Code → Download ZIP**) and extract it.

### Step 2 — (Optional, recommended) Install The Sleuth Kit

| Distribution | Command |
|---|---|
| Fedora / RHEL / CentOS | `sudo dnf install sleuthkit` |
| Debian / Ubuntu / Mint | `sudo apt install sleuthkit` |
| Arch / Manjaro / EndeavourOS | `sudo pacman -S sleuthkit` |
| openSUSE | `sudo zypper install sleuthkit` |
| Gentoo | `sudo emerge app-forensics/sleuthkit` |
| Void | `sudo xbps-install sleuthkit` |
| NixOS | `nix-env -iA nixpkgs.sleuthkit` |

### Step 3 — Install

```bash
./install.sh
```

No admin rights needed: Mosaïk installs into your home folder (`~/.local`), with its icon in the applications menu.

### Step 4 — Launch

Search for **Mosaïk** in the applications menu, or type:

```bash
mosaik
```

Without installing, from the downloaded folder: `python3 mosaik.py`.

### Check that everything works

```bash
python3 --version                       # 3.8 or newer
command -v fls icat mmls && echo "The Sleuth Kit OK"
mosaik --version
```

### Uninstall

```bash
./uninstall.sh
```

Files you already recovered are kept.

## 🎬 Usage

1. **Launch Mosaïk.** Your admin password is requested (required to read a disk), then the browser opens.
2. **Which disk?** Click the disk or partition. Pick the **whole disk** if the partition was deleted or reformatted. Disks in use are flagged in orange.
3. **What are you looking for?** Everything is selected by default; shortcuts *Photos only* / *Documents* / *All*.
4. **Where to save?** On **another disk** (USB stick, external drive…). Tick *The disk is damaged* if it makes noise or shows errors.
5. Click **Start recovery** and watch the mosaic fill up. Hover a photo: its position lights up on the mosaic.

### Mosaic colours

| Colour | Meaning |
|---|---|
| ⬛ Dark grey | Not read yet |
| 🟦 Blue grey | Empty / data without a recognised file |
| 🔵 Blue | Images |
| 🟡 Yellow | Documents |
| 🟢 Green | Audio |
| 🩷 Pink | Video |
| 🟣 Purple | Archives |
| 🟠 Orange | Re-assembled fragmented file |
| 🔴 Red | Unreadable area (bad sectors) |

### What you get

Files are saved in `~/Mosaik-recuperation/mosaik-YYYYMMDD-HHMMSS/`:

```
mosaik-20261116-220315/
├── Noms d'origine/        deleted files with original name and folder (The Sleuth Kit)
│   └── partition1_NTFS/Users/Marie/Photos/holidays.jpg
├── Images/                photos and pictures found by signature
├── Documents/             PDF, Word, Excel, LibreOffice, SQLite…
├── Audio/  Vidéos/  Archives/
├── rapport.csv            full list: status, fragments, offset, MD5, SHA-256
├── chronologie.csv        file activity timeline (created, modified, accessed)
├── partitions.txt         detected partitions and file systems
└── LISEZMOI.txt           how to read the results
```

| Status | Meaning |
|---|---|
| **complet** | Found in one piece |
| **reconstruit** | Fragmented file, pieces re-assembled and verified |
| **partiel** | Part is missing; the beginning is often usable |

### Advanced settings

| Setting | Default | Purpose |
|---|---|---|
| Deep search | off | Also search between sectors (slower; old memory cards) |
| Cluster size | 4096 bytes | Granularity of fragment search |
| Max distance between fragments | 1024 clusters (4 MB) | How far to look for the rest of a cut file |
| Minimum size | 2048 bytes | Skips thumbnails and crumbs |
| Hash database | — | NSRL / md5sum file to flag known files |

### Text mode (servers, live USB, headless)

```bash
sudo mosaik --cli /dev/sdb --sortie /media/external/recovery
sudo mosaik --cli /dev/sdb --cloner --sortie /media/external/recovery   # failing drive
mosaik --cli disk.E01 --types jpg,png,pdf --hachages NSRLFile.txt       # forensic image
```

| Option | Purpose |
|---|---|
| `--cli SOURCE` | Disk, partition or image to scan |
| `--sortie FOLDER` | Where to save files |
| `--types LIST` | `jpg,png,gif,bmp,pdf,zip,riff,mp4,mp3,sqlite` |
| `--cloner` | Copy the failing drive to an image first |
| `--profond` | Search outside sector boundaries |
| `--sans-tsk` | Don't use The Sleuth Kit |
| `--sans-signatures` | Original names only (The Sleuth Kit) |
| `--hachages FILE` | Hash database (NSRL, md5sum…) |
| `--sans-root` | Don't ask for admin rights (to scan an image) |
| `--version` | Show version |

## 💡 Tips to maximise your chances

- 🛑 **Stop using the affected disk** as soon as you notice the loss: every new write can overwrite your files. Don't install Mosaïk on it.
- 💾 **Always recover to another disk** (Mosaïk refuses otherwise anyway).
- 🔊 Clicking, slow or error-prone drive: tick **"The disk is damaged"** so it is read only once.
- ⚡ **SSDs**: TRIM often wipes deleted data for good. Act fast, unplug the SSD if you can.
- 🧊 Drive that doesn't spin or isn't detected at all: mechanical or electronic failure — no software can help. Don't open it.

## 🗂️ Project structure

```
Mosaik/
├── mosaik.py                 # Engine + local web server + text mode
├── ui.html                   # Interface (HTML/CSS/JS, no dependency)
├── install.sh / uninstall.sh # Per-user install
├── scripts/
│   └── install-linux.sh      # One-line installer (all distributions)
├── packaging/
│   └── mosaik.desktop        # Applications menu entry
├── assets/                   # Logo, icons (SVG + PNG 16→512), social preview
├── assets/fonts/             # Bundled Poppins font (SIL OFL 1.1)
├── tools/brand.py            # Generates logo and icons (Pixel's colours, Poppins)
├── docs/                     # Screenshots
├── tests/
│   └── test_recuperation.py  # Test disk image with fragmented files
├── .github/                  # CI, issue templates
├── CHANGELOG.md · CONTRIBUTING.md · LICENSE
└── README.md · README.fr.md
```

## 🧪 Tests

```bash
pip install pillow
python3 tests/test_recuperation.py
```

The test builds a disk image containing photos, a PDF and a Word document — **three of them fragmented** (JPEG, PNG, DOCX) among junk data — runs Mosaïk and checks that every file is recovered **byte-for-byte identical**.

## 🐛 Troubleshooting

### "Lecture impossible de /dev/sdX" (cannot read)
Mosaïk has no admin rights. Start it from the menu (the password is requested) or with `sudo mosaik`.

### The browser doesn't open
Copy the `http://127.0.0.1:…/?t=…` link printed in the terminal into your browser.

### The disk is not listed
Click **↻ Actualiser** (refresh). Check it is detected: `lsblk`. If not, the problem is hardware (cable, power, USB adapter).

### "The output folder is on the disk being recovered"
That's a safety feature: choose a folder on another disk.

### The Sleuth Kit shows as "absent"
Install your distribution's `sleuthkit` package (see step 2), then restart Mosaïk.

### A "reconstruit" photo shows a grey or shifted band
JPEG re-assembly is likely, not certain. Keep the photo: the top part is almost always right. Also try increasing the *max distance between fragments*.

### Scanning is slow
Speed mostly depends on the disk (a USB 2.0 stick reads ~20 MB/s). A failing drive can be very slow: use the "damaged disk" mode.

## 🤝 Need a hand?

Mosaïk is made by **Pixel's ASBL**, a nonprofit digital-inclusion workshop.
Rather not do it yourself, or the disk no longer responds? Contact us: we recover your data or guide you step by step.

📞 +32 456 96 03 28 · ✉️ info@asblpixels.be · 🌐 [asblpixels.be](https://www.asblpixels.be) · [Facebook](https://www.facebook.com/asblpixels)

⭐ **Like the project? Star the repo** — it's the easiest way to help other people find it.

## 🙏 Acknowledgements

This project builds on the remarkable work of:

- **[The Sleuth Kit](https://www.sleuthkit.org/)** (Brian Carrier and contributors) — partition and file system analysis.
- **[PhotoRec / TestDisk](https://www.cgsecurity.org/)** (Christophe Grenier) — the reference for signature carving and an inspiration.
- **[GNU ddrescue](https://www.gnu.org/software/ddrescue/)** — the method for imaging failing drives.
- **[NIST NSRL](https://www.nist.gov/itl/ssd/software-quality-group/national-software-reference-library-nsrl)** — the reference hash database.
- Research on **fragmented file carving** (Garfinkel; Pal & Memon; DFRWS).
- **[Python](https://www.python.org/)** and the whole open-source community.

## 📚 Sources & references

- The Sleuth Kit — description and tools: https://www.sleuthkit.org/sleuthkit/desc.php
- The Sleuth Kit — documentation: https://wiki.sleuthkit.org/
- PNG specification (W3C): https://www.w3.org/TR/png/
- JPEG (ITU-T T.81): https://www.w3.org/Graphics/JPEG/itu-t81.pdf
- ZIP format (PKWARE APPNOTE): https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
- SQLite file format: https://www.sqlite.org/fileformat.html
- ISO base media file format (MP4/MOV/HEIC): ISO/IEC 14496-12
- Simson Garfinkel, *Carving contiguous and fragmented files with fast object validation*, DFRWS 2007
- A. Pal, N. Memon, *The evolution of file carving*, IEEE Signal Processing Magazine, 2009

## 👨‍💻 Creators

**Mosaïk** is created and maintained by **[asblPixels](https://github.com/asblPixels)** as part of its open-source software initiative.

Contributions, bug reports and feature requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## 📜 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE). The Sleuth Kit is a separate project (IBM Public License / CPL / GPL depending on modules), used only if installed. The [Poppins](https://github.com/itfoundry/Poppins) font is bundled under the SIL Open Font License 1.1 ([assets/fonts/OFL.txt](assets/fonts/OFL.txt)).

## ⚠️ Legal note

Mosaïk is intended to recover **your own data**, or data belonging to someone who **gave you permission**.

- ✅ Your own disks, sticks and memory cards, or those of a relative / customer with their consent.
- ⚠️ Recovering data from a device you don't own without permission is illegal (privacy, GDPR).
- ⚠️ No software can guarantee recovery: overwritten or TRIM-erased data is gone for good.
- ❌ Mosaïk is not a certified forensic tool; for legal proceedings, hire a certified expert.

---

<div align="center">

Made with ❤️ by [asblPixels](https://github.com/asblPixels) · Open Source · MIT License

</div>
