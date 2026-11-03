"""
Extract the MakeCode project embedded in a downloaded PNG ("shareable image") or
UF2 file. Mirrors pxt's decoders:
  PNG: pxtlib/util.ts  decodeBlobAsync  -> webapp/src/app.tsx importProjectCoreAsync
  UF2: pxtlib/cpp.ts   unpackSourceFromHexAsync / extractSourceFromBin
"""

import json
import lzma
import struct
from pathlib import Path

from PIL import Image, UnidentifiedImageError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_MAGIC = 0x59347A7D
PNG_HEADER_SIZE = 36  # 9 x u32 LE: magic, blob_len, added_lines, 6 x reserved

UF2_MAGIC0 = 0x0A324655
UF2_MAGIC1 = 0x9E5D5157
UF2_FLAG_NOT_MAIN_FLASH = 0x00000001
SOURCE_MAGIC = bytes([0x41, 0x14, 0x0E, 0x2F, 0xB8, 0x2F, 0xA2, 0xBB])


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


# ------------------------------------------------------------- public --------


def read_embedded_files(src: Path) -> dict[str, str]:
    """Return the embedded project as {filename: content}, detecting PNG vs UF2."""
    with src.open("rb") as f:
        head = f.read(len(PNG_SIGNATURE))
    if head.startswith(PNG_SIGNATURE):
        decoder = files_from_png
    elif len(head) >= 4 and struct.unpack_from("<I", head)[0] == UF2_MAGIC0:
        decoder = files_from_uf2
    else:
        raise EmbeddedSourceError(f"{src} is neither a PNG nor a UF2")
    try:
        return decoder(src)
    except EmbeddedSourceError as e:
        raise EmbeddedSourceError(f"{src}: {e}") from e
    except (
        IndexError,  # ran off the end of the pixel data
        struct.error,  # truncated UF2 source header
        lzma.LZMAError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        UnidentifiedImageError,
    ) as e:
        raise EmbeddedSourceError(
            f"{src}: embedded MakeCode project is corrupt ({e})"
        ) from e


def extract_project(src: Path, dest: Path) -> list[str]:
    """Write the embedded project's files (pxt.json, main.ts, ...) to dest."""
    files = read_embedded_files(src)
    root = dest.resolve()
    targets: dict[Path, str] = {}
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
        out.write_bytes(content.encode("utf-8"))
    return sorted(files)
