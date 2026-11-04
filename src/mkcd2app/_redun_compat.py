import redun.file
from redun.file import ContentDir, ContentFile, Dir, File, RedunFileNotFoundError
from redun.hashing import hash_struct

# Monkey-patch redun.file.get_proto so Windows absolute paths like "E:\..."
# aren't parsed as having scheme "e" by urllib.parse.urlparse.
_orig_get_proto = redun.file.get_proto


def _patched_get_proto(url: str | None = None) -> str:
    if (
        url
        and len(url) >= 3
        and url[1] == ":"
        and url[0].isalpha()
        and url[2] in ("\\", "/")
    ):
        return "local"
    return _orig_get_proto(url)


redun.file.get_proto = _patched_get_proto


# Monkey patch ContentDir to use content-based hashing instead of mtime-based hashing.
# This addresses the issue where cache busts even on identical runs.
# Note: ContentDir.__iter__() already yields ContentFile objects (via
# ContentFileClasses), so f.hash is content-based — no need to create redundant
# ContentFile instances.
def _content_dir_calc_hash(self: Dir, files: list[File] | None = None) -> str:
    if files is None:
        files = list(self)

    return hash_struct([self.type_basename, self.path] + sorted(f.hash for f in files))


redun.file.ContentDir._calc_hash = _content_dir_calc_hash  # type: ignore[method-assign]


# Also patch Dir._calc_hash to prevent mtime-based hashing leak through any
# code path that uses Dir directly (e.g. FileSystem.iter_file_hashes).
# Note: we intentionally drop the `files` param because Dir.update_hash()
# passes File objects (mtime-based), not ContentFile objects. Re-iterating
# via ContentDir gives properly content-based hashing.
def _dir_calc_hash(self: Dir, files: list[File] | None = None) -> str:
    return ContentDir(self.path)._calc_hash()


redun.file.Dir._calc_hash = _dir_calc_hash  # type: ignore[method-assign]


# Monkey patch ContentFile so a deleted file counts as changed. redun raises from its
# cache check instead, so deleting a task's output would crash the next run rather
# than rerun the task. (File and ContentDir already handle this.)
_orig_content_file_calc_hash = redun.file.ContentFile._calc_hash


def _content_file_calc_hash(self: ContentFile) -> str:
    try:
        return _orig_content_file_calc_hash(self)
    except RedunFileNotFoundError:
        return hash_struct([self.type_basename, self.path, "missing"])


redun.file.ContentFile._calc_hash = _content_file_calc_hash  # type: ignore[method-assign]


def assert_pinned_redun_version() -> None:
    assert redun.__version__ == "0.44.1", (
        "compat patches assume this exact redun version; verify before bumping"
    )
