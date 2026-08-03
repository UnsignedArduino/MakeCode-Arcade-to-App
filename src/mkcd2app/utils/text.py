import re
from pathlib import Path

from mkcd2app.models.metadata import BinaryJSMetadata


def extract_meta_comment(file_path: Path) -> BinaryJSMetadata:
    """
    Extracts the // meta={} data from the binary.js file.

    :param file_path: Path to the binary.js
    :return: The metadata (a BinaryJSMetadata)
    :raises ValueError: If the meta comment is not found in file.
    """
    with file_path.open("rt") as f:
        for line in f:
            line = line.strip()
            if line.startswith("// meta="):
                # Extract everything after '// meta='
                json_str = line.split("// meta=", 1)[1]
                return BinaryJSMetadata.model_validate_json(json_str)

    raise ValueError("Meta comment not found in file.")


# Thanks Gemini
STRICT_NUMERIC_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def is_strict_semver(version: str) -> bool:
    """Validates string using official SemVer 2.0.0 regex pattern."""
    return bool(STRICT_NUMERIC_SEMVER.match(version))


def raise_for_invalid_strict_semver(version: str) -> None:
    if not is_strict_semver(version):
        raise ValueError(
            f"Version '{version}' is not a valid strict numeric semver (e.g., 1.2.3)."
        )
