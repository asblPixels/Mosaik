# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- English and French READMEs, screenshots, social preview image (`assets/social-preview.png`, 1280×640).
- One-line installer for all distributions (`scripts/install-linux.sh`).
- CI (syntax, lint, shellcheck, recovery test), issue templates, contributing guide.

### Changed
- New visual identity in Pixel's ASBL colours (black, white, turquoise #26EFC5) with Poppins typography; text outlined in SVGs (`tools/brand.py`).
- Poppins font bundled (WOFF2, SIL OFL 1.1) and served locally, so the interface title matches the logo even when Poppins is not installed.
- Vendor IDs such as `0x1af4` are no longer shown as disk names.
- After a scan, reopening the interface shows the results instead of the setup screen.

## [1.0.0] - 2026-11-16

### Added
- **Signature carving** with sector-aligned scanning: JPEG, PNG, GIF, BMP, WEBP, HEIC, PDF, DOCX/XLSX/PPTX, ODT/ODS/ODP, EPUB, ZIP/JAR/APK, MP3, WAV, M4A, MP4, MOV, AVI, 3GP, SQLite.
- **Fragmented file re-assembly** (gap carving): PNG (chunk CRC), ZIP/Office (per-entry CRC with saved decompressor state), JPEG (entropy-data validation and restart markers). Partial JPEGs are closed with an end marker so they display.
- **The Sleuth Kit integration** (optional): partitions (`mmls`), file systems (`fsstat`), deleted files with original names and folders (`fls` + `icat -r`), NTFS alternate data streams, CSV timeline, E01/VHD/VMDK/AFF images (`img_cat`).
- **Failing drive mode**: ddrescue-style imaging (fast pass skipping bad areas, then sector-by-sector retry).
- **MD5 and SHA-256** for every recovered file; optional hash database (NSRL, HashKeeper, md5sum).
- **Visual web interface**: live disk mosaic, progress, photo previews, filters (by type, re-assembled, partial, known).
- **Text mode** (`--cli`) for servers and live USB systems.
- **Safety**: read-only source, refusal to write onto the scanned disk (including LVM/RAID/LUKS), localhost-only server with random token and DNS-rebinding protection, browser opened as the regular user, path-traversal protection.
- Per-user installer, desktop entry, icons (SVG + PNG 16→512), logo.
- Recovery test with fragmented JPEG, PNG and DOCX files (byte-for-byte check).
