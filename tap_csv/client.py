"""Custom client handling, including CSVStream base class."""

import bz2
import csv
import gzip
import lzma
import os
from typing import Iterable, List, Optional

from singer_sdk import typing as th
from singer_sdk.streams import Stream


class CSVStream(Stream):
    """Stream class for CSV streams."""

    file_paths: List[str] = []

    def __init__(self, *args, **kwargs):
        """Init CSVStram."""
        # cache file_config so we dont need to go iterating the config list again later
        self.file_config = kwargs.pop("file_config")
        super().__init__(*args, **kwargs)

    def get_records(self, context: Optional[dict]) -> Iterable[dict]:
        """Return a generator of row-type dictionary objects.

        The optional `context` argument is used to identify a specific slice of the
        stream if partitioning is required for the stream. Most implementations do not
        require partitioning and should ignore the `context` argument.
        """
        for file_path in self.get_file_paths():
            headers: List[str] = []
            for row in self.get_rows(file_path):
                if not headers:
                    headers = row
                    continue
                yield dict(zip(headers, row))

    def get_file_paths(self) -> list:
        """Return a list of file paths to read.

        This tap accepts file names and directories so it will detect
        directories and iterate files inside.
        """
        # Cache file paths so we dont have to iterate multiple times
        if self.file_paths:
            return self.file_paths

        file_path = self.file_config["path"]
        if not os.path.exists(file_path):
            raise Exception(f"File path does not exist {file_path}")

        file_paths = []
        if os.path.isdir(file_path):
            clean_file_path = os.path.normpath(file_path) + os.sep
            for filename in os.listdir(clean_file_path):
                file_path = clean_file_path + filename
                if self.is_valid_filename(file_path):
                    file_paths.append(file_path)
        else:
            if self.is_valid_filename(file_path):
                file_paths.append(file_path)

        if not file_paths:
            raise Exception(
                f"Stream '{self.name}' has no acceptable files. \
                    See warning for more detail."
            )
        self.file_paths = file_paths
        return file_paths

    def is_valid_filename(self, file_path: str) -> bool:
        """Return a boolean of whether the file includes CSV extension."""
        supported_extensions = ['.csv', '.csv.gz', '.csv.bz2', '.csv.xz', '.csv.lzma']
        file_path = file_path.lower()

        for check_ext in supported_extensions:
            if file_path.endswith(check_ext):
                return True

        self.logger.warning(f"Skipping non-csv file '{file_path}'")
        self.logger.warning("Please provide a CSV file with any of supported extensions: "
                            f"{', '.join(supported_extensions)}")
        return False

    def get_rows(self, file_path: str) -> Iterable[list]:
        """Return a generator of the rows in a particular CSV file."""

        if file_path.lower().endswith('.gz'):
            opener = gzip.open
        elif file_path.lower().endswith('.bz2'):
            opener = bz2.open
        elif file_path.lower().endswith('.xz') or file_path.lower().endswith('.lzma'):
            opener = lzma.open
        else:
            opener = open

        with opener(file_path, "rt") as f:
            reader = csv.reader(f)
            for row in reader:
                yield row

    @property
    def schema(self) -> dict:
        """Return dictionary of record schema.

        Dynamically detect the json schema for the stream.
        This is evaluated prior to any records being retrieved.
        """
        properties: List[th.Property] = []
        self.primary_keys = self.file_config.get("keys", [])

        for file_path in self.get_file_paths():
            for header in self.get_rows(file_path):
                break
            break

        # TODO: header might be uninitialized here if the CSV file is empty.
        for column in header:
            # Set all types to string
            # TODO: Try to be smarter about inferring types.
            properties.append(th.Property(column, th.StringType()))
        return th.PropertiesList(*properties).to_dict()
