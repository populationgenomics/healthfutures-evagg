import csv
import json
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime

from lib.evagg import __version__
from lib.evagg.utils.run import get_run_path

from .interfaces import IWriteOutput

logger = logging.getLogger(__name__)


def _get_output_path(name: str | None, extension: str) -> str | None:
    """Helper to get output path, handling both absolute and relative paths."""
    if not name:
        return None

    filename = name if name.endswith(f".{extension}") else f"{name}.{extension}"
    if os.path.isabs(name):
        return filename
    else:
        return os.path.join(get_run_path(), filename)


class TableOutputWriter(IWriteOutput):
    def __init__(self, tsv_name: str | None = None) -> None:
        self._generated = datetime.now().astimezone()
        self._path = _get_output_path(tsv_name, "tsv")
        if self._path and os.path.exists(self._path):
            logger.warning(f"Overwriting existing output file: {self._path}")

    async def write(self, output: Sequence[Mapping[str, str]]) -> str | None:
        logger.info(f"Writing output to: {self._path or 'stdout'}")

        if len(output) == 0:
            logger.warning("No results to write")
            return None

        if self._path:
            parent = os.path.dirname(self._path)
            if not os.path.exists(parent):
                os.makedirs(parent)

        if self._path:
            with open(self._path, "w") as output_stream:
                writer = csv.writer(output_stream, delimiter="\t", lineterminator="\n")
                writer.writerow([f"# Generated {self._generated.strftime('%Y-%m-%d %H:%M:%S %Z')}"])

                field_names = output[0].keys()
                writer.writerow(field_names)
                for line in output:
                    # For table output, all rows should have the same keys.
                    assert line.keys() == field_names
                    writer.writerow(line.values())
        else:
            writer = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
            writer.writerow([f"# Generated {self._generated.strftime('%Y-%m-%d %H:%M:%S %Z')}"])

            field_names = output[0].keys()
            writer.writerow(field_names)
            for line in output:
                # For table output, all rows should have the same keys.
                assert line.keys() == field_names
                writer.writerow(line.values())
        return self._path


class JSONOutputWriter(IWriteOutput):
    def __init__(self, json_name: str | None = None, env_config: dict[str, str] | None = None) -> None:
        self._generated = datetime.now().astimezone()

        # Build version: base version + model version (if provided in env_config)
        if env_config and "model" in env_config:
            self._version = f"{__version__}-{env_config['model']}"
        else:
            self._version = __version__

        self._path = _get_output_path(json_name, "json")
        if self._path and os.path.exists(self._path):
            logger.warning(f"Overwriting existing output file: {self._path}")

    async def write(self, output: Sequence[Mapping[str, str]]) -> str | None:
        logger.info(f"Writing output to: {self._path or 'stdout'}")

        if len(output) == 0:
            logger.warning("No results to write")
            return None

        if self._path:
            parent = os.path.dirname(self._path)
            if not os.path.exists(parent):
                os.makedirs(parent)

        # Convert Mapping objects to regular dicts for JSON serialization
        json_output = {
            "generated": self._generated.isoformat(),
            "version": self._version,
            "data": [dict(item) for item in output],
        }

        if self._path:
            with open(self._path, "w") as f:
                json.dump(json_output, f, indent=2)
        else:
            json.dump(json_output, sys.stdout, indent=2)

        return self._path
