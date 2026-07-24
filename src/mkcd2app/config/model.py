from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, HttpUrl, RootModel


# Source code can be a share link, GitHub repo, or a path on disk

class ShareLinkCodeSource(BaseModel):
    type: Literal["share_link"]
    value: HttpUrl


class GitHubCodeSource(BaseModel):
    type: Literal["github"]
    value: HttpUrl
    checkout: str = "master"


class PathCodeSource(BaseModel):
    type: Literal["path"]
    value: str


CodeSource = RootModel[
    Annotated[
        Union[ShareLinkCodeSource, GitHubCodeSource, PathCodeSource],
        Field(discriminator="type")
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
    Annotated[
        Union[UrlAssetSource, PathAssetSource],
        Field(discriminator="type")
    ]
]


# Right now we only have one asset so far, just the icon
class Assets(BaseModel):
    icon: Optional[AssetSource] = None


# To build a project, we need multiple inputs
class Inputs(BaseModel):
    code: CodeSource
    assets: Assets


# Project metadata
class Project(BaseModel):
    name: str
    path_friendly_name: str
    description: Optional[str] = None
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
    window: Optional[WindowConfig] = None


class TauriOutput(BaseModel):
    type: Literal["tauri"]
    identifier: str
    window: Optional[WindowConfig] = None


OutputOption = RootModel[
    Annotated[
        Union[StaticOutput, StaticSinglefileOutput, ElectronOutput, TauriOutput],
        Field(discriminator="type")
    ]
]


# The entire config
class BuildConfig(BaseModel):
    version: int  # currently only 1 version so far
    project: Project
    inputs: Inputs
    build_dir: str = Field(..., alias="build_dir")
    outputs: List[OutputOption]

    class Config:
        populate_by_name = True
