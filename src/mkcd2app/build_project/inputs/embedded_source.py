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
UF2_BLOCK_SIZE = 512
UF2_MAX_PAYLOAD = 476  # 512 - 32 byte header - 4 byte end magic
# Blocks further apart than this start a new run instead of being zero-padded
# (pxt's UF2.toBin skips blocks after a gap over 1 MB)
UF2_MAX_GAP = 1024 * 1024
# The flash images we read are a few MB; bounds the memory a crafted file can ask for
UF2_MAX_IMAGE_SIZE = 64 * 1024 * 1024
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


def _cesu8_to_utf16(buf: bytes) -> bytes:
    """
    Decode text written by LZMA-JS's string encoder to UTF-16-LE code units.

    LZMA-JS encodes each UTF-16 code unit on its own (CESU-8): characters outside
    the BMP, like emoji, become two 3-byte surrogates that strict UTF-8 rejects, and
    U+0000 becomes C0 80. Plain UTF-8 (including 4-byte sequences) decodes the same.
    Returning code units keeps JavaScript string offsets (e.g. UF2 ``headerSize``)
    valid as ``2 * offset``.
    """
    # C0 is never valid UTF-8, so this can't touch anything else
    text = buf.replace(b"\xc0\x80", b"\x00").decode("utf-8", "surrogatepass")
    return text.encode("utf-16-le", "surrogatepass")


def _utf16_to_str(units: bytes) -> str:
    """
    Turn UTF-16-LE code units into a str, joining surrogate pairs.

    :raises UnicodeDecodeError: On a lone surrogate, which can't be written as UTF-8.
    """
    return units.decode("utf-16-le")


def _lzma_decompress(buf: bytes) -> bytes:
    """Decompress an LZMA-JS payload to its text, as UTF-16-LE code units."""
    # pxt uses LZMA-JS, which writes the legacy ".lzma" (LZMA_Alone) container.
    return _cesu8_to_utf16(lzma.decompress(buf, format=lzma.FORMAT_ALONE))


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
    project = json.loads(_utf16_to_str(_lzma_decompress(_png_blob(path))))
    # {"meta": {...name, cloudId, targetVersions, editor}, "source": "<json of files>"}
    if not isinstance(project, dict) or not isinstance(project.get("source"), str):
        raise EmbeddedSourceError("Embedded PNG project has no source")
    return _parse_files(project["source"])


# ---------------------------------------------------------------- UF2 ---------


def _uf2_runs(data: bytes) -> list[tuple[int, bytes]]:
    """
    Reassemble a UF2's main-flash blocks into contiguous runs of memory.

    Blocks with small gaps between them are zero-padded into one run, like pxt's
    ``UF2.toBin``; a bigger gap starts a new run, so far-apart addresses never turn
    into one huge buffer. Everything is validated before anything is allocated.

    :return: (offset from the lowest address, bytes) for each run, in address order.
    :raises EmbeddedSourceError: If there are no blocks, a block's payload doesn't fit
     in it, or the runs add up to more than ``UF2_MAX_IMAGE_SIZE``.
    """
    chunks: dict[int, bytes] = {}
    for off in range(0, len(data) - UF2_BLOCK_SIZE + 1, UF2_BLOCK_SIZE):
        m0, m1, flags, addr, size = struct.unpack_from("<5I", data, off)
        if m0 != UF2_MAGIC0 or m1 != UF2_MAGIC1 or flags & UF2_FLAG_NOT_MAIN_FLASH:
            continue
        if size > UF2_MAX_PAYLOAD:
            raise EmbeddedSourceError(
                f"UF2 block at offset {off} declares a {size} byte payload, "
                f"over the {UF2_MAX_PAYLOAD} bytes a block can hold"
            )
        chunks[addr] = data[off + 32 : off + 32 + size]
    if not chunks:
        raise EmbeddedSourceError("Not a UF2 file")

    # Lay out the runs as (start, end, [(addr, chunk)]) before allocating
    spans: list[tuple[int, int, list[tuple[int, bytes]]]] = []
    for addr in sorted(chunks):
        chunk = chunks[addr]
        if spans and addr - spans[-1][1] <= UF2_MAX_GAP:
            start, end, members = spans[-1]
            members.append((addr, chunk))
            spans[-1] = (start, max(end, addr + len(chunk)), members)
        else:
            spans.append((addr, addr + len(chunk), [(addr, chunk)]))
    total = sum(end - start for start, end, _ in spans)
    if total > UF2_MAX_IMAGE_SIZE:
        raise EmbeddedSourceError(
            f"UF2 covers {total} bytes of memory, "
            f"over the {UF2_MAX_IMAGE_SIZE // 2**20} MB limit"
        )

    base = spans[0][0]
    runs: list[tuple[int, bytes]] = []
    for start, end, members in spans:
        buf = bytearray(end - start)
        for addr, chunk in members:
            buf[addr - start : addr - start + len(chunk)] = chunk
        runs.append((start - base, bytes(buf)))
    return runs


def _find_source(runs: list[tuple[int, bytes]]) -> tuple[bytes, int]:
    """
    Find the 16-byte aligned source magic (alignment counted from the lowest
    address, like pxt's search over the whole image).

    :return: The run holding it and the magic's position in that run.
    """
    for run_offset, run in runs:
        p = 0
        while (p := run.find(SOURCE_MAGIC, p)) >= 0:
            if (run_offset + p) % 16 == 0:
                return run, p
            p += 1
    raise EmbeddedSourceError("This UF2 doesn't contain source (binary-only build?)")


def files_from_uf2(path: Path) -> dict[str, str]:
    bin_, p = _find_source(_uf2_runs(path.read_bytes()))
    meta_len, text_len = struct.unpack_from("<HI", bin_, p + 8)
    p += 16
    meta = json.loads(_utf16_to_str(_cesu8_to_utf16(bin_[p : p + meta_len])))
    if not isinstance(meta, dict):
        raise EmbeddedSourceError("UF2 source metadata is not a JSON object")
    text = bin_[p + meta_len : p + meta_len + text_len]

    if meta.get("compression") == "LZMA":
        units = _lzma_decompress(text)
        # headerSize is a JavaScript string length, i.e. in UTF-16 code units
        header_size = meta.get("headerSize") or meta.get("metaSize") or 0
        if not isinstance(header_size, int) or not 0 <= 2 * header_size <= len(units):
            raise EmbeddedSourceError(f"Invalid UF2 source headerSize {header_size!r}")
        # header JSON, then files JSON
        return _parse_files(_utf16_to_str(units[2 * header_size :]))
    if meta.get("compression"):
        raise EmbeddedSourceError(f"Unsupported compression {meta['compression']}")
    return _parse_files(_utf16_to_str(_cesu8_to_utf16(text)))


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
