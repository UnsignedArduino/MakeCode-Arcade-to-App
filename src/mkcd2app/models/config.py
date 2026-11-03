from typing import Annotated, Literal

from pydantic import AnyUrl, BaseModel, Field, HttpUrl, RootModel

# Source code can be a share link, git repo, a path on disk, or a PNG/UF2 file
# downloaded from the editor with the project embedded


class ShareLinkCodeSource(BaseModel):
    type: Literal["share_link"]
    value: HttpUrl


class GitCodeSource(BaseModel):
    type: Literal["git"]
    # Any URL dulwich can clone: https://, http://, git://, file://, or ssh:// (ssh://
    # needs an `ssh` executable on PATH)
    url: AnyUrl
    # Branch, tag, or (possibly abbreviated) commit SHA. None means the remote's
    # default branch.
    ref: str | None = None


class GitHubCodeSource(BaseModel):
    """
    Alias for GitCodeSource, kept so older configs keep working: `value` is the
    URL and `checkout` is the ref.
    """

    type: Literal["github"]
    value: HttpUrl
    checkout: str = "master"


class PathCodeSource(BaseModel):
    type: Literal["path"]
    value: str


class FileCodeSource(BaseModel):
    """A PNG or UF2 downloaded from the MakeCode editor with the project embedded."""

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


class UrlAssetSource(BaseModel):
    type: Literal["url"]
    value: HttpUrl


class PathAssetSource(BaseModel):
    type: Literal["path"]
    value: str


AssetSource = RootModel[
    Annotated[UrlAssetSource | PathAssetSource, Field(discriminator="type")]
]


# Right now we only have one asset so far, just the icon
class Assets(BaseModel):
    icon: AssetSource | None = None


# To build a project, we need multiple inputs
class Inputs(BaseModel):
    code: CodeSource
    assets: Assets


# Project metadata
class Project(BaseModel):
    name: str
    path_friendly_name: str
    description: str | None = None
    author: str
    version: str
    title: str = "{NAME} v{VERSION}"


class WindowConfig(BaseModel):
    width: int = 640
    height: int = 480


# Different types of outputs available that we can build


class StaticOutput(BaseModel):
    type: Literal["static"]


class StaticSinglefileOutput(BaseModel):
    type: Literal["static-singlefile"]


class ElectronOutput(BaseModel):
    type: Literal["electron"]
    window: WindowConfig | None = None


class TauriOutput(BaseModel):
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
class BuildConfig(BaseModel):
    version: int  # currently only 1 version so far
    project: Project
    inputs: Inputs
    build_dir: str = Field(..., alias="build_dir")
    target: str = Field(..., alias="target")
    outputs: list[OutputOption]

    class Config:
        populate_by_name = True
