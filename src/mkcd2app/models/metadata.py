from pydantic import BaseModel, Field, HttpUrl


# {
#   "simUrl":"https://trg-arcade.userpxt.io/---simulator",
#   "cdnUrl":"https://cdn.makecode.com",
#   "version":"v0.0.0",
#   "target":"arcade",
#   "targetVersion":"4.0.14"
# }
class BinaryJSMetadata(BaseModel):
    simUrl: HttpUrl = Field(..., description="Simulator URL")
    cdnUrl: HttpUrl = Field(..., description="CDN base URL")
    version: str = Field(..., description="Package version")
    target: str = Field(..., description="Build target name")
    targetVersion: str = Field(..., description="Target version string")

    class Config:
        extra = "forbid"
