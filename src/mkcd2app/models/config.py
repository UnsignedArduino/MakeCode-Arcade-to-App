import ntpath
from typing import Annotated, Literal

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    RootModel,
    field_validator,
)

from mkcd2app.utils.text import raise_for_invalid_strict_semver


class ConfigModel(BaseModel):
    """
    Base for the config's models. Unknown keys are errors, so that a typo like
    ``titel:`` fails instead of silently using the default.
    """

    model_config = ConfigDict(extra="forbid")


# Source code can be a share link, git repo, a path on disk, or a file: a PNG/UF2
# downloaded from the editor with the project embedded, or a ZIP of the project


class ShareLinkCodeSource(ConfigModel):
    type: Literal["share_link"]
    value: HttpUrl


class GitCodeSource(ConfigModel):
    type: Literal["git"]
    # Any URL dulwich can clone: https://, http://, git://, file://, or ssh:// (ssh://
    # needs an `ssh` executable on PATH)
    url: AnyUrl
    # Branch, tag, or (possibly abbreviated) commit SHA. None means the remote's
    # default branch.
    ref: str | None = None


class GitHubCodeSource(ConfigModel):
    """
    Alias for GitCodeSource, kept so older configs keep working: `value` is the
    URL and `checkout` is the ref.
    """

    type: Literal["github"]
    value: HttpUrl
    checkout: str = "master"


class PathCodeSource(ConfigModel):
    type: Literal["path"]
    value: str


class FileCodeSource(ConfigModel):
    """
    A PNG or UF2 downloaded from the MakeCode editor with the project embedded, or a
    ZIP of the project (e.g. GitHub's "Download ZIP"). Detected by content.
    """

    type: Literal["file"]
    value: str


CodeSource = RootModel[
    Annotated[
        ShareLinkCodeSource
        | GitCodeSource
        | GitHubCodeSource
        | PathCodeSource
        | FileCodeSource,
        Field(discriminator="type"),
    ]
]


# Assets can be a URL or path on disk


class UrlAssetSource(ConfigModel):
    type: Literal["url"]
    value: HttpUrl


class PathAssetSource(ConfigModel):
    type: Literal["path"]
    value: str


AssetSource = RootModel[
    Annotated[UrlAssetSource | PathAssetSource, Field(discriminator="type")]
]


# Right now we only have one asset so far, just the icon
class Assets(ConfigModel):
    icon: AssetSource | None = None


# To build a project, we need multiple inputs
class Inputs(ConfigModel):
    code: CodeSource
    assets: Assets


# Project metadata
class Project(ConfigModel):
    """
    ``title`` is the window/page title. The placeholders ``{NAME}``, ``{VERSION}``
    and ``{AUTHOR}`` are replaced with the matching fields, in a single pass (so a
    substituted value is never expanded again). Any other text, including other
    braces such as ``{Game}`` or ``{}``, is kept literally; there is no brace
    escaping, so ``{{NAME}}`` becomes ``{<name>}``.

    ``path_friendly_name`` names the stage directories inside ``build_dir`` and is the
    website's ``package.json`` name, so it must be a single path component that's also
    lowercase and URL-safe. A ``..`` or path separator would let a build delete and
    write outside ``build_dir``.
    """

    name: str
    path_friendly_name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=64)
    description: str | None = None
    author: str
    version: str
    title: str = "{NAME} v{VERSION}"

    @field_validator("path_friendly_name")
    @classmethod
    def _check_path_friendly_name_is_not_reserved(cls, v: str) -> str:
        # ntpath rather than os.path, so configs are rejected the same way on every OS
        if ntpath.isreserved(v):
            raise ValueError(f"{v!r} is a reserved file name on Windows")
        return v


class WindowConfig(ConfigModel):
    width: int = 640
    height: int = 480


# Different types of outputs available that we can build


class StaticOutput(ConfigModel):
    type: Literal["static"]


class StaticSinglefileOutput(ConfigModel):
    type: Literal["static-singlefile"]


class ElectronOutput(ConfigModel):
    type: Literal["electron"]
    window: WindowConfig | None = None


class TauriOutput(ConfigModel):
    type: Literal["tauri"]
    identifier: str
    window: WindowConfig | None = None


OutputOption = RootModel[
    Annotated[
        StaticOutput | StaticSinglefileOutput | ElectronOutput | TauriOutput,
        Field(discriminator="type"),
    ]
]


# The entire config
class BuildConfig(ConfigModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int  # currently only 1 version so far
    project: Project
    inputs: Inputs
    build_dir: str = Field(..., alias="build_dir")
    target: str = Field(..., alias="target")
    outputs: list[OutputOption] = Field(..., min_length=1)

    @field_validator("target")
    @classmethod
    def _check_target_is_strict_semver(cls, v: str) -> str:
        raise_for_invalid_strict_semver(v)
        return v
