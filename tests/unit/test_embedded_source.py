import hashlib
import json
import lzma
import stat
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from mkcd2app.build_project.inputs import embedded_source
from mkcd2app.build_project.inputs.embedded_source import (
    PNG_HEADER_SIZE,
    PNG_MAGIC,
    SOURCE_MAGIC,
    UF2_FLAG_NOT_MAIN_FLASH,
    UF2_MAGIC0,
    UF2_MAGIC1,
    UF2_MAX_GAP,
    UF2_MAX_IMAGE_SIZE,
    UF2_MAX_PAYLOAD,
    ZIP_MAX_TOTAL_SIZE,
    EmbeddedSourceError,
    extract_project,
    read_embedded_files,
    read_project_files,
)
from mkcd2app.config import load_config_from_yaml
from mkcd2app.models.config import FileCodeSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "embedded"
DUCK_UF2 = FIXTURES / "falling-duck.uf2"
DUCK_PNG = FIXTURES / "falling-duck.png"
EMPTY_PNG = FIXTURES / "empty-game.png"
# Made by the real LZMA-JS (see generate.cjs there), which writes emoji as CESU-8
LZMA_JS = FIXTURES / "lzma-js"
RACERS_ZIP = FIXTURES / "Racers-master.zip"  # GitHub "Download ZIP" of Racers
EMPTY_GAME_DIR = Path(__file__).parent.parent / "fixtures" / "empty_game"
DUCK_FILES = {"README.md", "assets.json", "main.blocks", "main.ts", "pxt.json"}
DUCK_MAIN_TS_SHA256 = "2100e5d1f310a31abac094e6173c66b7394c18a67c466baa9a655623feded775"

SAMPLE_FILES = {
    "pxt.json": json.dumps({"name": "sample", "dependencies": {"device": "*"}}),
    "main.ts": "let x = 1\r\ngame.splash('héllo')\n",
    "README.md": " ",
}


# ------------------------------------------------------------ helpers ---------


def _encode(img: bytearray, ptr: int, bpp: int, data: bytes) -> int:
    """Port of pxt's encodeBlobAsync bit packer."""
    shift = dp = 0
    v = data[dp]
    dp += 1
    mask = (1 << bpp) - 1
    keep_going = True
    while keep_going:
        bits = (v >> shift) & mask
        left = 8 - shift
        if left <= bpp:
            if dp >= len(data):
                if left == 0:
                    break
                keep_going = False
            v = data[dp] if dp < len(data) else 0
            dp += 1
            bits |= (v << left) & mask
            shift = bpp - left
        else:
            shift += bpp
        img[ptr] = ((img[ptr] & ~mask) | bits) & 0xFF
        ptr += 1
        if ptr & 3 == 3:
            img[ptr] = 0xFF
            ptr += 1
    return ptr


def make_project_png(w: int, h: int, blob: bytes, path: Path) -> int:
    """
    Write a PNG the way pxt's encodeBlobAsync does.

    :param blob: lzma.compress(json_text, format=lzma.FORMAT_ALONE).
    :return: The number of overflow rows added.
    """
    need = PNG_HEADER_SIZE + len(blob)
    usable = (w * h - 1) * 3
    bpp = 1
    while bpp < 4 and usable * bpp < need * 8:
        bpp += 1
    cap = (usable * bpp) >> 3
    added = max(0, -(-(need - cap) // (w * 3)))
    added_offset = w * h * 4
    img = bytearray(Image.new("RGBA", (w, h + added), (120, 30, 200, 255)).tobytes())
    header = struct.pack("<9I", PNG_MAGIC, len(blob), added, *[0] * 6)
    _encode(img, 0, 1, bytes([bpp]))
    p = _encode(img, 4, bpp, header)
    if added == 0:
        _encode(img, p, bpp, blob)
    else:
        first = cap - PNG_HEADER_SIZE
        _encode(img, p, bpp, blob[:first])
        _encode(img, added_offset, 8, blob[first:])
    Image.frombytes("RGBA", (w, h + added), bytes(img)).save(path)
    return added


def _png_blob_for(files: dict[str, str], padding: str = "") -> bytes:
    project = {
        "meta": {"name": "sample", "editor": "blocksprj", "pad": padding},
        "source": json.dumps(files),
    }
    return lzma.compress(json.dumps(project).encode(), format=lzma.FORMAT_ALONE)


def make_project_uf2(
    path: Path,
    meta: dict[str, object],
    text: bytes,
    pad: int = 1000,
    meta_bytes: bytes | None = None,
) -> None:
    """
    Embed source the way pxt does, then chunk it into 256-byte UF2 blocks.

    :param meta_bytes: The encoded meta JSON, instead of ``json.dumps(meta)``.
    """
    meta_bytes = json.dumps(meta).encode() if meta_bytes is None else meta_bytes
    pre = b"\xaa" * (pad + (-pad % 16))  # source magic must be 16-byte aligned
    binary = (
        pre
        + SOURCE_MAGIC
        + struct.pack("<HI2x", len(meta_bytes), len(text))
        + meta_bytes
        + text
    )
    _write_uf2(path, binary)


def _write_uf2(path: Path, binary: bytes, base: int = 0x2000) -> None:
    chunks = [binary[i : i + 256] for i in range(0, len(binary), 256)]
    out = bytearray()
    for i, chunk in enumerate(chunks):
        block = struct.pack(
            "<8I", UF2_MAGIC0, UF2_MAGIC1, 0, base + i * 256, 256, i, len(chunks), 0
        )
        block += chunk.ljust(476, b"\x00") + struct.pack("<I", 0x0AB16F30)
        out += block
    # A non-main-flash block the decoder must ignore
    junk = struct.pack(
        "<8I", UF2_MAGIC0, UF2_MAGIC1, UF2_FLAG_NOT_MAIN_FLASH, 0, 256, 0, 1, 0
    )
    out += junk + SOURCE_MAGIC.ljust(476, b"\x00") + struct.pack("<I", 0x0AB16F30)
    path.write_bytes(bytes(out))


# ------------------------------------------------------ real fixtures ---------


def _check_duck(files: dict[str, str]) -> None:
    assert set(files) == DUCK_FILES
    main_ts = files["main.ts"]
    assert main_ts.startswith("enum ActionKind {")
    assert len(main_ts.splitlines()) == 539
    assert hashlib.sha256(main_ts.encode()).hexdigest() == DUCK_MAIN_TS_SHA256
    pxt = json.loads(files["pxt.json"])
    assert pxt["name"] == "falling duck"
    assert set(pxt["dependencies"]) == {"device", "animation"}
    assert pxt["targetVersions"]["target"] == "4.1.27"


def test_duck_uf2() -> None:
    _check_duck(read_embedded_files(DUCK_UF2))


def test_duck_png_matches_uf2() -> None:
    # Both were exported from 4.1.27 in the same session, so every file matches
    png = read_embedded_files(DUCK_PNG)
    _check_duck(png)
    assert png == read_embedded_files(DUCK_UF2)


def test_empty_game_png_matches_fixture_dir() -> None:
    # Exported from the 4.0.14 editor; only the project name differs from the
    # checked-in tests/fixtures/empty_game
    files = read_embedded_files(EMPTY_PNG)
    assert set(files) == {p.name for p in EMPTY_GAME_DIR.iterdir()}
    for name, content in files.items():
        expected = (EMPTY_GAME_DIR / name).read_text(encoding="utf-8")
        if name == "pxt.json":
            got_pxt, expected_pxt = json.loads(content), json.loads(expected)
            assert got_pxt.pop("name") == "empty_game"
            expected_pxt.pop("name")
            assert got_pxt == expected_pxt
        else:
            assert content == expected


def test_duck_extract(tmp_path: Path) -> None:
    names = extract_project(DUCK_UF2, tmp_path / "out")
    assert set(names) == DUCK_FILES
    data = (tmp_path / "out" / "main.ts").read_bytes()
    assert hashlib.sha256(data).hexdigest() == DUCK_MAIN_TS_SHA256


# ---------------------------------------------------------- synthetic PNG -----


def test_png_fits_in_image(tmp_path: Path) -> None:
    path = tmp_path / "game.png"
    assert make_project_png(160, 120, _png_blob_for(SAMPLE_FILES), path) == 0
    assert read_embedded_files(path) == SAMPLE_FILES


def test_png_overflow_rows(tmp_path: Path) -> None:
    path = tmp_path / "game.png"
    blob = _png_blob_for(SAMPLE_FILES, padding="".join(map(str, range(200))))
    assert len(blob) > 300
    assert make_project_png(6, 6, blob, path) > 0
    assert read_embedded_files(path) == SAMPLE_FILES


@pytest.mark.parametrize("size", [(20, 20), (40, 30), (64, 64)])
def test_png_various_bpp(tmp_path: Path, size: tuple[int, int]) -> None:
    path = tmp_path / "game.png"
    make_project_png(*size, _png_blob_for(SAMPLE_FILES), path)
    assert read_embedded_files(path) == SAMPLE_FILES


# ---------------------------------------------------------- synthetic UF2 -----


def test_uf2_lzma(tmp_path: Path) -> None:
    header = json.dumps({"name": "sample", "editor": "blocksprj"})
    text = lzma.compress(
        (header + json.dumps(SAMPLE_FILES)).encode(), format=lzma.FORMAT_ALONE
    )
    path = tmp_path / "game.uf2"
    make_project_uf2(path, {"compression": "LZMA", "headerSize": len(header)}, text)
    assert read_embedded_files(path) == SAMPLE_FILES


def test_uf2_uncompressed(tmp_path: Path) -> None:
    path = tmp_path / "game.uf2"
    make_project_uf2(path, {"name": "sample"}, json.dumps(SAMPLE_FILES).encode())
    assert read_embedded_files(path) == SAMPLE_FILES


def test_extract_writes_bytes_exactly(tmp_path: Path) -> None:
    src = tmp_path / "game.uf2"
    make_project_uf2(src, {}, json.dumps(SAMPLE_FILES).encode())
    dest = tmp_path / "out"
    assert extract_project(src, dest) == sorted(SAMPLE_FILES)
    for name, content in SAMPLE_FILES.items():
        assert (dest / name).read_bytes() == content.encode("utf-8")


# ------------------------------------------------- LZMA-JS text encoding ------


def _lzma_js_files() -> dict[str, str]:
    files: dict[str, str] = json.loads((LZMA_JS / "files.json").read_text("utf-8"))
    return files


def test_lzma_js_fixture_is_cesu8() -> None:
    # Guards the fixture itself: strict UTF-8 must reject it, or it tests nothing
    raw = lzma.decompress(
        (LZMA_JS / "png-project.lzma").read_bytes(), format=lzma.FORMAT_ALONE
    )
    assert "😀".encode("utf-16-be").hex().startswith("d83d")
    assert b"\xed\xa0\xbd\xed\xb8\x80" in raw  # 😀 as two surrogates
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")


def test_lzma_js_png_with_emoji(tmp_path: Path) -> None:
    src = tmp_path / "game.png"
    make_project_png(160, 120, (LZMA_JS / "png-project.lzma").read_bytes(), src)
    files = _lzma_js_files()
    assert read_embedded_files(src) == files
    assert 'game.splash("hello 😀")' in files["main.ts"]

    dest = tmp_path / "out"
    extract_project(src, dest)
    for name, content in files.items():
        assert (dest / name).read_bytes() == content.encode("utf-8")


def test_lzma_js_uf2_with_emoji_in_header(tmp_path: Path) -> None:
    header_size = int((LZMA_JS / "uf2-header-size.txt").read_text("utf-8"))
    text = (LZMA_JS / "uf2-source.lzma").read_bytes()
    src = tmp_path / "game.uf2"
    make_project_uf2(src, {"compression": "LZMA", "headerSize": header_size}, text)
    files = _lzma_js_files()

    # The header holds an emoji, so its JS length (UTF-16 code units) is longer than
    #  its Python length: slicing by characters would cut into the files JSON
    header = '{"name":"emoji 😀 game","editor":"tsprj"}'
    assert header_size == len(header.encode("utf-16-le")) // 2 == len(header) + 1
    assert read_embedded_files(src) == files

    dest = tmp_path / "out"
    extract_project(src, dest)
    for name, content in files.items():
        assert (dest / name).read_bytes() == content.encode("utf-8")


def _cesu8(text: str) -> bytes:
    """Encode like LZMA-JS: each UTF-16 code unit on its own, U+0000 as C0 80."""
    units = text.encode("utf-16-le")
    split = "".join(
        chr(int.from_bytes(units[i : i + 2], "little")) for i in range(0, len(units), 2)
    )
    return split.encode("utf-8", "surrogatepass").replace(b"\x00", b"\xc0\x80")


@pytest.mark.parametrize("encode", [str.encode, _cesu8], ids=["utf8", "cesu8"])
def test_uf2_meta_with_emoji(tmp_path: Path, encode: Callable[[str], bytes]) -> None:
    meta: dict[str, object] = {"name": "emoji 😀 game"}
    src = tmp_path / "game.uf2"
    make_project_uf2(
        src,
        meta,
        json.dumps(SAMPLE_FILES).encode(),
        meta_bytes=encode(json.dumps(meta, ensure_ascii=False)),
    )
    assert read_embedded_files(src) == SAMPLE_FILES


@pytest.mark.parametrize("encode", [str.encode, _cesu8], ids=["utf8", "cesu8"])
@pytest.mark.parametrize("text", ["a😀b", "é ✓ 𝄞", "plain"])
def test_uncompressed_uf2_text_encodings(
    tmp_path: Path, encode: Callable[[str], bytes], text: str
) -> None:
    src = tmp_path / "game.uf2"
    make_project_uf2(src, {}, encode(json.dumps({"main.ts": text}, ensure_ascii=False)))
    assert read_embedded_files(src) == {"main.ts": text}


def test_cesu8_nul() -> None:
    # JSON.stringify escapes U+0000, so it never reaches a project, but LZMA-JS
    #  would write it as C0 80
    assert _cesu8("a\x00b") == b"a\xc0\x80b"
    units = embedded_source._cesu8_to_utf16(b"a\xc0\x80b")
    assert embedded_source._utf16_to_str(units) == "a\x00b"


def test_lone_surrogate_is_corrupt(tmp_path: Path) -> None:
    # Can't be written as UTF-8, so it must fail cleanly rather than at write time
    project = '{"meta": {}, "source": "{\\"main.ts\\": \\"x\ud83dy\\"}"}'
    blob = lzma.compress(
        project.encode("utf-8", "surrogatepass"), format=lzma.FORMAT_ALONE
    )
    src = tmp_path / "game.png"
    make_project_png(160, 120, blob, src)
    with pytest.raises(EmbeddedSourceError, match="corrupt"):
        read_embedded_files(src)


@pytest.mark.parametrize("header_size", [-1, 10_000, "5"])
def test_uf2_invalid_header_size(tmp_path: Path, header_size: object) -> None:
    text = lzma.compress(json.dumps(SAMPLE_FILES).encode(), format=lzma.FORMAT_ALONE)
    src = tmp_path / "game.uf2"
    make_project_uf2(src, {"compression": "LZMA", "headerSize": header_size}, text)
    with pytest.raises(EmbeddedSourceError, match="headerSize"):
        read_embedded_files(src)


# ------------------------------------------------------------ UF2 layout ------


def _uf2_block(addr: int, payload: bytes, size: int | None = None) -> bytes:
    header = struct.pack(
        "<8I",
        UF2_MAGIC0,
        UF2_MAGIC1,
        0,
        addr,
        len(payload) if size is None else size,
        0,
        1,
        0,
    )
    return header + payload.ljust(476, b"\x00") + struct.pack("<I", 0x0AB16F30)


def _source_payload() -> bytes:
    text = json.dumps(SAMPLE_FILES).encode()
    meta = b"{}"
    return SOURCE_MAGIC + struct.pack("<HI2x", len(meta), len(text)) + meta + text


@pytest.fixture
def allocations(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record the size of each bytearray the decoder allocates."""
    sizes: list[int] = []

    def spy(size: int = 0) -> bytearray:
        sizes.append(size)
        assert size <= UF2_MAX_IMAGE_SIZE, f"tried to allocate {size} bytes"
        return bytearray(size)

    monkeypatch.setattr(embedded_source, "bytearray", spy, raising=False)
    return sizes


def test_uf2_far_apart_blocks_not_densified(
    tmp_path: Path, allocations: list[int]
) -> None:
    # Regression: addresses 0 and 0xFFFF0000 asked for a ~4 GiB buffer
    payload = _source_payload()
    chunks = [payload[i : i + 256] for i in range(0, len(payload), 256)]
    blocks = _uf2_block(0, b"\xaa" * 256)
    for i, chunk in enumerate(chunks):
        blocks += _uf2_block(0xFFFF0000 + i * 256, chunk)
    src = tmp_path / "game.uf2"
    src.write_bytes(blocks)

    assert read_embedded_files(src) == SAMPLE_FILES
    assert max(allocations) <= len(blocks)


def test_uf2_small_gap_is_padded(tmp_path: Path) -> None:
    # Blocks with a gap (like pxt's toBin pads) still form one image, so the
    #  source's 16-byte alignment is counted from the lowest address
    payload = _source_payload()
    chunks = [payload[i : i + 256] for i in range(0, len(payload), 256)]
    blocks = _uf2_block(0x1000, b"\xaa" * 256)
    for i, chunk in enumerate(chunks):
        blocks += _uf2_block(0x4000 + i * 256, chunk)
    src = tmp_path / "game.uf2"
    src.write_bytes(blocks)
    assert read_embedded_files(src) == SAMPLE_FILES


def test_uf2_too_much_memory(tmp_path: Path, allocations: list[int]) -> None:
    # Each block sits just within the padding gap, so they'd all join one run
    count = UF2_MAX_IMAGE_SIZE // UF2_MAX_GAP + 2
    blocks = b"".join(
        _uf2_block(i * (UF2_MAX_GAP + 256), b"\xaa" * 256) for i in range(count)
    )
    src = tmp_path / "game.uf2"
    src.write_bytes(blocks)
    with pytest.raises(EmbeddedSourceError, match="MB limit"):
        read_embedded_files(src)
    assert allocations == []  # rejected before allocating anything


@pytest.mark.parametrize("size", [UF2_MAX_PAYLOAD + 1, 0xFFFFFFFF])
def test_uf2_oversized_payload(
    tmp_path: Path, allocations: list[int], size: int
) -> None:
    src = tmp_path / "game.uf2"
    src.write_bytes(_uf2_block(0x2000, _source_payload()[:256], size=size))
    with pytest.raises(EmbeddedSourceError, match="payload"):
        read_embedded_files(src)
    assert allocations == []


def test_uf2_max_payload_accepted(tmp_path: Path) -> None:
    payload = _source_payload()
    assert len(payload) <= 2 * UF2_MAX_PAYLOAD
    src = tmp_path / "game.uf2"
    src.write_bytes(
        _uf2_block(0x2000, payload[:UF2_MAX_PAYLOAD])
        + _uf2_block(0x2000 + UF2_MAX_PAYLOAD, payload[UF2_MAX_PAYLOAD:])
    )
    assert read_embedded_files(src) == SAMPLE_FILES


# ----------------------------------------------------------------- errors -----


def test_plain_png_has_no_project(tmp_path: Path) -> None:
    path = tmp_path / "plain.png"
    Image.new("RGBA", (32, 32), (0, 0, 0, 255)).save(path)
    with pytest.raises(EmbeddedSourceError):
        read_embedded_files(path)


def test_noisy_png_has_no_project(tmp_path: Path) -> None:
    path = tmp_path / "noise.png"
    Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(path)  # bpp == 7
    with pytest.raises(EmbeddedSourceError):
        read_embedded_files(path)


def test_uf2_without_source(tmp_path: Path) -> None:
    path = tmp_path / "binary-only.uf2"
    _write_uf2(path, b"\x00" * 4096)
    with pytest.raises(EmbeddedSourceError, match="doesn't contain source"):
        read_embedded_files(path)


def test_neither_format(tmp_path: Path) -> None:
    path = tmp_path / "game.txt"
    path.write_text("hello")
    with pytest.raises(EmbeddedSourceError, match="not a PNG, UF2 or ZIP"):
        read_embedded_files(path)


def test_truncated_png_payload(tmp_path: Path) -> None:
    path = tmp_path / "game.png"
    blob = _png_blob_for(SAMPLE_FILES)
    make_project_png(160, 120, blob[: len(blob) // 2], path)
    with pytest.raises(EmbeddedSourceError, match="corrupt"):
        read_embedded_files(path)


@pytest.mark.parametrize("name", ["../evil.ts", "sub/../../evil.ts", "/abs/evil.ts"])
def test_path_traversal_rejected(tmp_path: Path, name: str) -> None:
    src = tmp_path / "game.uf2"
    make_project_uf2(src, {}, json.dumps({"main.ts": "", name: "x"}).encode())
    dest = tmp_path / "out"
    with pytest.raises(EmbeddedSourceError, match="Refusing to write outside"):
        extract_project(src, dest)
    assert not dest.exists()  # nothing written before the check fails
    assert not (tmp_path / "evil.ts").exists()


# -------------------------------------------------------------------- ZIP -----


def make_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


SAMPLE_BYTES = {k: v.encode() for k, v in SAMPLE_FILES.items()}


def test_racers_github_zip(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    names = extract_project(RACERS_ZIP, dest)
    # The Racers-master/ wrapper is stripped and the whole repo is kept
    assert {"pxt.json", "main.ts", "main.blocks", "test.ts"} <= set(names)
    assert "assets/js/binary.js" in names
    assert ".github/workflows/makecode.yml" in names
    assert not any(n.startswith("Racers-master") for n in names)
    pxt = json.loads((dest / "pxt.json").read_text(encoding="utf-8"))
    assert pxt["name"] == "Racers v1.3.2"
    for name in pxt["files"] + pxt["testFiles"]:
        assert (dest / name).is_file(), name
    # Binary files come through untouched
    with zipfile.ZipFile(RACERS_ZIP) as zf:
        png = zf.read("Racers-master/.github/makecode/blocks.png")
    assert (dest / ".github" / "makecode" / "blocks.png").read_bytes() == png


@pytest.mark.parametrize("prefix", ["", "Game-main/"])
def test_zip_root_or_wrapper(tmp_path: Path, prefix: str) -> None:
    src = tmp_path / "game.zip"
    entries = {prefix + k: v for k, v in SAMPLE_BYTES.items()}
    entries[prefix + "assets/img.bin"] = bytes(range(256))
    make_zip(src, entries)
    expected = SAMPLE_BYTES | {"assets/img.bin": bytes(range(256))}
    assert read_project_files(src) == expected


def test_zip_keeps_line_endings(tmp_path: Path) -> None:
    src = tmp_path / "game.zip"
    make_zip(src, {"pxt.json": b"{}", "main.ts": b"a\r\nb\n"})
    extract_project(src, tmp_path / "out")
    assert (tmp_path / "out" / "main.ts").read_bytes() == b"a\r\nb\n"


@pytest.mark.parametrize(
    "entries",
    [
        {"main.ts": b""},  # no pxt.json at all
        {"a/b/pxt.json": b"{}"},  # nested too deep
        {"a/pxt.json": b"{}", "b/main.ts": b""},  # two top-level folders
    ],
)
def test_zip_without_project_root(tmp_path: Path, entries: dict[str, bytes]) -> None:
    src = tmp_path / "game.zip"
    make_zip(src, entries)
    with pytest.raises(EmbeddedSourceError, match="no pxt.json"):
        read_project_files(src)


def test_zip_skips_symlinks(tmp_path: Path) -> None:
    src = tmp_path / "game.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("pxt.json", b"{}")
        link = zipfile.ZipInfo("evil")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "/etc/passwd")
    assert read_project_files(src) == {"pxt.json": b"{}"}


def test_zip_path_traversal_rejected(tmp_path: Path) -> None:
    src = tmp_path / "game.zip"
    make_zip(src, {"pxt.json": b"{}", "../evil.ts": b"x"})
    dest = tmp_path / "out"
    with pytest.raises(EmbeddedSourceError, match="Refusing to write outside"):
        extract_project(src, dest)
    assert not dest.exists()
    assert not (tmp_path / "evil.ts").exists()


def test_zip_bomb_rejected(tmp_path: Path) -> None:
    src = tmp_path / "bomb.zip"
    with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pxt.json", b"{}")
        with zf.open("big.bin", "w", force_zip64=True) as f:
            chunk = b"\0" * 2**20
            for _ in range(ZIP_MAX_TOTAL_SIZE // len(chunk) + 1):
                f.write(chunk)
    with pytest.raises(EmbeddedSourceError, match="uncompressed"):
        read_project_files(src)


def test_corrupt_zip(tmp_path: Path) -> None:
    src = tmp_path / "game.zip"
    make_zip(src, SAMPLE_BYTES)
    src.write_bytes(src.read_bytes()[:-30])  # cut off the central directory
    with pytest.raises(EmbeddedSourceError, match="corrupt"):
        read_project_files(src)


def test_read_embedded_files_rejects_zip(tmp_path: Path) -> None:
    src = tmp_path / "game.zip"
    make_zip(src, SAMPLE_BYTES)
    with pytest.raises(EmbeddedSourceError, match="not a PNG or UF2"):
        read_embedded_files(src)


# ----------------------------------------------------------------- config -----


def test_config_file_source() -> None:
    yaml_path = Path(__file__).parent.parent / "fixtures"
    text = (yaml_path / "empty_game_build_to_statics.yaml").read_text(encoding="utf-8")
    text = text.replace(
        'type: path\n    value: "tests/fixtures/empty_game"',
        'type: file\n    value: "tests/fixtures/embedded/falling-duck.png"',
    )
    config = load_config_from_yaml(text)
    assert config.inputs.code.root == FileCodeSource(
        type="file", value="tests/fixtures/embedded/falling-duck.png"
    )
