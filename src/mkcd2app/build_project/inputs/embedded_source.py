"""
Extract the MakeCode project from a downloaded file: a PNG ("shareable image") or
UF2 from the editor, or a ZIP of the project's repo (GitHub's "Download ZIP").

The PNG and UF2 decoders mirror pxt's:
  PNG: pxtlib/util.ts  decodeBlobAsync  -> webapp/src/app.tsx importProjectCoreAsync
  UF2: pxtlib/cpp.ts   unpackSourceFromHexAsync / extractSourceFromBin
"""

import json
import lzma
import stat
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_MAGIC = 0x59347A7D
PNG_HEADER_SIZE = 36  # 9 x u32 LE: magic, blob_len, added_lines, 6 x reserved

UF2_MAGIC0 = 0x0A324655
UF2_MAGIC1 = 0x9E5D5157
UF2_FLAG_NOT_MAIN_FLASH = 0x00000001
SOURCE_MAGIC = bytes([0x41, 0x14, 0x0E, 0x2F, 0xB8, 0x2F, 0xA2, 0xBB])

ZIP_MAGIC = b"PK\x03\x04"
# Limits against zip bombs; a big MakeCode repo is a few MB uncompressed
ZIP_MAX_TOTAL_SIZE = 512 * 1024 * 1024
ZIP_MAX_ENTRIES = 10_000


class EmbeddedSourceError(ValueError):
    """The file has no embedded MakeCode project, or it could not be decoded."""


def _parse_files(text: str | bytes) -> dict[str, str]:
    files = json.loads(text)
    if not isinstance(files, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in files.items()
    ):
        raise EmbeddedSourceError("Embedded project is not a {filename: text} map")
    return files


def _lzma_decompress(buf: bytes) -> str:
    # pxt uses LZMA-JS, which writes the legacy ".lzma" (LZMA_Alone) container.
    return lzma.decompress(buf, format=lzma.FORMAT_ALONE).decode("utf-8")


# ---------------------------------------------------------------- PNG ---------


def _png_blob(path: Path) -> bytes:
    img = Image.open(path).convert("RGBA")
    width, height = img.size
    d = img.tobytes()  # flat R,G,B,A,R,G,B,A,... like canvas getImageData

    bpp = (d[0] & 1) | ((d[1] & 1) << 1) | ((d[2] & 1) << 2)
    if bpp == 0 or bpp > 5:
        raise EmbeddedSourceError("PNG does not contain an embedded MakeCode project")

    def decode(ptr: int, bits: int, length: int) -> tuple[bytes, int]:
        out = bytearray()
        shift = acc = 0
        mask = (1 << bits) - 1
        while len(out) < length:
            acc |= (d[ptr] & mask) << shift
            ptr += 1
            if ptr & 3 == 3:  # skip alpha
                ptr += 1
            shift += bits
            if shift >= 8:
                out.append(acc & 0xFF)
                acc >>= 8
                shift -= 8
        return bytes(out), ptr

    header, ptr = decode(4, bpp, PNG_HEADER_SIZE)
    magic, blob_len, added_lines = struct.unpack_from("<3I", header)
    if magic != PNG_MAGIC:
        raise EmbeddedSourceError("Invalid magic in encoded PNG")

    if added_lines == 0:
        blob, _ = decode(ptr, bpp, blob_len)
        return blob

    # Image was too small: the first chunk lives in the LSBs of the original
    # pixels, the rest is stored as full bytes in extra rows appended at the end.
    orig_pixels = (height - added_lines) * width
    img_cap = ((orig_pixels - 1) * 3 * bpp) >> 3
    first, _ = decode(ptr, bpp, img_cap - PNG_HEADER_SIZE)
    rest, _ = decode(orig_pixels * 4, 8, blob_len - len(first))
    return first + rest


def files_from_png(path: Path) -> dict[str, str]:
    project = json.loads(_lzma_decompress(_png_blob(path)))
    # {"meta": {...name, cloudId, targetVersions, editor}, "source": "<json of files>"}
    if not isinstance(project, dict) or not isinstance(project.get("source"), str):
        raise EmbeddedSourceError("Embedded PNG project has no source")
    return _parse_files(project["source"])


# ---------------------------------------------------------------- UF2 ---------


def _uf2_to_bin(data: bytes) -> bytes:
    chunks: dict[int, bytes] = {}
    for off in range(0, len(data) - 511, 512):
        m0, m1, flags, addr, size = struct.unpack_from("<5I", data, off)
        if m0 != UF2_MAGIC0 or m1 != UF2_MAGIC1 or flags & UF2_FLAG_NOT_MAIN_FLASH:
            continue
        chunks[addr] = data[off + 32 : off + 32 + size]
    if not chunks:
        raise EmbeddedSourceError("Not a UF2 file")
    base = min(chunks)
    end = max(a + len(c) for a, c in chunks.items())
    buf = bytearray(end - base)
    for addr, c in chunks.items():
        buf[addr - base : addr - base + len(c)] = c
    return bytes(buf)


def files_from_uf2(path: Path) -> dict[str, str]:
    bin_ = _uf2_to_bin(path.read_bytes())
    p = 0
    while True:
        p = bin_.find(SOURCE_MAGIC, p)
        if p < 0:
            raise EmbeddedSourceError(
                "This UF2 doesn't contain source (binary-only build?)"
            )
        if p % 16 == 0:  # pxt only looks at 16-byte aligned positions
            break
        p += 1
    meta_len, text_len = struct.unpack_from("<HI", bin_, p + 8)
    p += 16
    meta = json.loads(bin_[p : p + meta_len].decode("utf-8"))
    if not isinstance(meta, dict):
        raise EmbeddedSourceError("UF2 source metadata is not a JSON object")
    text = bin_[p + meta_len : p + meta_len + text_len]

    if meta.get("compression") == "LZMA":
        raw = _lzma_decompress(text)
        header_size = meta.get("headerSize") or meta.get("metaSize") or 0
        return _parse_files(raw[header_size:])  # header JSON, then files JSON
    if meta.get("compression"):
        raise EmbeddedSourceError(f"Unsupported compression {meta['compression']}")
    return _parse_files(text.decode("utf-8"))


# ---------------------------------------------------------------- ZIP ---------


def _zip_project_root(names: list[str]) -> PurePosixPath:
    """
    Find the folder holding pxt.json: the archive root, or the single top-level
    folder that GitHub's "Download ZIP" wraps everything in (<repo>-<branch>/).
    """
    paths = [PurePosixPath(n) for n in names]
    if PurePosixPath("pxt.json") in paths:
        return PurePosixPath()
    tops = {p.parts[0] for p in paths if p.parts}
    if len(tops) == 1:
        (top,) = tops
        if PurePosixPath(top, "pxt.json") in paths:
            return PurePosixPath(top)
    raise EmbeddedSourceError(
        "ZIP has no pxt.json at its root or inside a single top-level folder"
    )


def files_from_zip(path: Path) -> dict[str, bytes]:
    """Return the project's files as {relative path: bytes}, any wrapper removed."""
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if len(infos) > ZIP_MAX_ENTRIES:
            raise EmbeddedSourceError(f"ZIP has more than {ZIP_MAX_ENTRIES} entries")
        # Directories and symlinks (stored as small files with a link mode) are
        # skipped; a MakeCode project has neither
        members = [
            i
            for i in infos
            if not i.is_dir() and not stat.S_ISLNK(i.external_attr >> 16)
        ]
        # file_size is enforced while reading, so the header total is a real bound
        if sum(i.file_size for i in members) > ZIP_MAX_TOTAL_SIZE:
            raise EmbeddedSourceError(
                f"ZIP is over {ZIP_MAX_TOTAL_SIZE // 2**20} MB uncompressed"
            )
        root = _zip_project_root([i.filename for i in members])
        files: dict[str, bytes] = {}
        for info in members:
            rel = PurePosixPath(info.filename)
            if root.parts:
                if rel.parts[: len(root.parts)] != root.parts:
                    continue
                rel = PurePosixPath(*rel.parts[len(root.parts) :])
            files[str(rel)] = zf.read(info)
    return files


# ------------------------------------------------------------- public --------


def _detect(src: Path) -> str:
    """Tell PNG, UF2 and ZIP apart by their magic bytes, not the extension."""
    with src.open("rb") as f:
        head = f.read(len(PNG_SIGNATURE))
    if head.startswith(PNG_SIGNATURE):
        return "png"
    if len(head) >= 4 and struct.unpack_from("<I", head)[0] == UF2_MAGIC0:
        return "uf2"
    if head.startswith(ZIP_MAGIC):
        return "zip"
    raise EmbeddedSourceError(f"{src} is not a PNG, UF2 or ZIP")


def _wrap_errors[T](src: Path, decode: Callable[[Path], T]) -> T:
    """Run a decoder, turning low-level failures into EmbeddedSourceError."""
    try:
        return decode(src)
    except EmbeddedSourceError as e:
        raise EmbeddedSourceError(f"{src}: {e}") from e
    except (
        IndexError,  # ran off the end of the pixel data
        struct.error,  # truncated UF2 source header
        lzma.LZMAError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        UnidentifiedImageError,
        zipfile.BadZipFile,
        NotImplementedError,  # ZIP compression method zipfile can't read
        RuntimeError,  # encrypted ZIP entry
    ) as e:
        raise EmbeddedSourceError(
            f"{src}: embedded MakeCode project is corrupt ({e})"
        ) from e


def read_embedded_files(src: Path) -> dict[str, str]:
    """Return the project in a PNG or UF2 as {filename: text}."""
    match _detect(src):
        case "png":
            return _wrap_errors(src, files_from_png)
        case "uf2":
            return _wrap_errors(src, files_from_uf2)
        case _:
            raise EmbeddedSourceError(f"{src} is not a PNG or UF2")


def read_project_files(src: Path) -> dict[str, bytes]:
    """Return the project in a PNG, UF2 or ZIP as {relative path: bytes}."""
    if _detect(src) == "zip":
        return _wrap_errors(src, files_from_zip)
    return {k: v.encode("utf-8") for k, v in read_embedded_files(src).items()}


def extract_project(src: Path, dest: Path) -> list[str]:
    """Write the project's files (pxt.json, main.ts, ...) from src to dest."""
    files = read_project_files(src)
    root = dest.resolve()
    targets: dict[Path, bytes] = {}
    # Check every name before writing anything, since they come from an untrusted file
    for name, content in files.items():
        out = (root / name).resolve()
        if root not in out.parents:
            raise EmbeddedSourceError(f"Refusing to write outside {dest}: {name}")
        targets[out] = content
    dest.mkdir(parents=True, exist_ok=True)
    for out, content in targets.items():
        out.parent.mkdir(parents=True, exist_ok=True)
        # write_bytes so line endings are kept exactly as embedded on every OS
        out.write_bytes(content)
    return sorted(files)
