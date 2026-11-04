// Regenerates the LZMA-JS payloads used by tests/unit/test_embedded_source.py.
//
// MakeCode compresses projects with LZMA-JS, which encodes strings as CESU-8 (each
// UTF-16 code unit on its own, so emoji become two 3-byte surrogates). Python's
// lzma can't produce that, so these payloads come from the real library:
//
//   npm install --no-save lzma@2.3.2
//   node generate.cjs
//
// Output: png-project.lzma (the PNG blob), uf2-source.lzma (the UF2 LZMA text),
// uf2-header-size.txt (headerSize, in UTF-16 code units), and files.json (the
// expected {filename: text} map, as normal UTF-8).
const fs = require("fs");
const path = require("path");
const LZMA = require("lzma");

const files = {
  "pxt.json": JSON.stringify({ name: "emoji 😀 game", dependencies: { device: "*" } }),
  "main.ts": 'game.splash("hello 😀")\r\nlet s = "é ✓ 𝄞"\n',
  "README.md": "# 🦆 Duck\n",
};
const meta = { name: "emoji 😀 game", editor: "tsprj" };

function compress(text) {
  return Buffer.from(Uint8Array.from(LZMA.compress(text, 9), (b) => b & 0xff));
}

const out = __dirname;
// PNG: pxt's compressProjectAsync -> {meta, source: JSON of files}
fs.writeFileSync(
  path.join(out, "png-project.lzma"),
  compress(JSON.stringify({ meta, source: JSON.stringify(files) })),
);
// UF2: header JSON then files JSON, headerSize = header's JS string length
const header = JSON.stringify(meta);
fs.writeFileSync(path.join(out, "uf2-source.lzma"), compress(header + JSON.stringify(files)));
fs.writeFileSync(path.join(out, "uf2-header-size.txt"), String(header.length));
fs.writeFileSync(path.join(out, "files.json"), JSON.stringify(files));
