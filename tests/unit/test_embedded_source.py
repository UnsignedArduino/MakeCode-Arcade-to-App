import hashlib
import json
import lzma
import struct
from pathlib import Path

import pytest
from PIL import Image

from mkcd2app.build_project.inputs.embedded_source import (
    PNG_HEADER_SIZE,
    PNG_MAGIC,
    SOURCE_MAGIC,
    UF2_FLAG_NOT_MAIN_FLASH,
    UF2_MAGIC0,
    UF2_MAGIC1,
    EmbeddedSourceError,
    extract_project,
    read_embedded_files,
)
from mkcd2app.config import load_config_from_yaml
from mkcd2app.models.config import FileCodeSource

FIXTURES = Path(__file__).parent.parent / "fixtures" / "embedded"
DUCK_UF2 = FIXTURES / "falling-duck.uf2"
DUCK_PNG = FIXTURES / "falling-duck.png"
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
    path: Path, meta: dict[str, object], text: bytes, pad: int = 1000
) -> None:
    """Embed source the way pxt does, then chunk it into 256-byte UF2 blocks."""
    meta_bytes = json.dumps(meta).encode()
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


needs_duck = pytest.mark.skipif(
    not (DUCK_UF2.exists() and DUCK_PNG.exists()),
    reason="falling-duck fixtures not present in tests/fixtures/embedded",
)


def _check_duck(files: dict[str, str]) -> None:
    assert set(files) == DUCK_FILES
    main_ts = files["main.ts"]
    assert main_ts.startswith("enum ActionKind {")
    assert len(main_ts.splitlines()) == 539
    assert hashlib.sha256(main_ts.encode()).hexdigest() == DUCK_MAIN_TS_SHA256
    pxt = json.loads(files["pxt.json"])
    assert pxt["name"] == "falling duck"
    assert {"device", "animation"} <= set(pxt["dependencies"])


@needs_duck
def test_duck_uf2() -> None:
    _check_duck(read_embedded_files(DUCK_UF2))


@needs_duck
def test_duck_png_matches_uf2() -> None:
    png = read_embedded_files(DUCK_PNG)
    _check_duck(png)
    uf2 = read_embedded_files(DUCK_UF2)
    for name in ("main.ts", "README.md", "assets.json"):
        assert png[name] == uf2[name]


@needs_duck
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
    with pytest.raises(EmbeddedSourceError, match="neither a PNG nor a UF2"):
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
