import os
import re
import shutil
import zipfile
from abc import ABC
from configparser import NoSectionError
from functools import wraps
from os import path

from autoconf import conf
from autofit.mapper import link
from autofit.mapper.model_object import Identifier
from autofit.non_linear.log import logger


def make_path(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        full_path = func(*args, **kwargs)
        os.makedirs(full_path, exist_ok=True)
        return full_path

    return wrapper


pattern = re.compile(r'(?<!^)(?=[A-Z])')


class AbstractPaths(ABC):
    def __init__(
            self,
            name="",
            path_prefix=None
    ):
        """Manages the path structure for `NonLinearSearch` output, for analyses both not using and using the search
        API. Use via non-linear searches requires manual input of paths, whereas the search API manages this using the
        search attributes.

        The output path within which the *Paths* objects path structure is contained is set via PyAutoConf, using the
        command:

        from autoconf import conf
        conf.instance = conf.Config(output_path="path/to/output")

        If we assume all the input strings above are used with the following example names:

        name = "name"
        tag = "tag"
        path_prefix = "folder_0/folder_1"
        non_linear_name = "emcee"

        The output path of the `NonLinearSearch` results will be:

        /path/to/output/folder_0/folder_1/name/tag/emcee

        Parameters
        ----------
        name : str
            The name of the non-linear search, which is used as a folder name after the ``path_prefix``. For searchs
            this name is the ``name``.
        path_prefix : str
            A prefixed path that appears after the output_path but beflore the name variable.
        """

        self.path_prefix = path_prefix or ""
        self.name = name or ""

        self._search = None
        self.model = None

        self._non_linear_name = None
        self._identifier = None

        try:
            self.remove_files = conf.instance["general"]["output"]["remove_files"]

            if conf.instance["general"]["hpc"]["hpc_mode"]:
                self.remove_files = True
        except NoSectionError as e:
            logger.exception(e)

    @property
    def search(self):
        return self._search

    @search.setter
    def search(self, search):
        self._search = search
        self._non_linear_name = pattern.sub(
            '_', type(
                self.search
            ).__name__
        ).lower()

    @property
    def non_linear_name(self):
        return self._non_linear_name

    @property
    def identifier(self):
        if None in (self.model, self.search):
            logger.warn(
                "Both model and search should be set before the tag is determined"
            )
        if self._identifier is None:
            self._identifier = str(
                Identifier([
                    self.search,
                    self.model
                ])
            )
        return self._identifier

    @property
    def path(self):
        return link.make_linked_folder(self._sym_path)

    @property
    @make_path
    def samples_path(self) -> str:
        """
        The path to the samples folder.
        """
        return path.join(self.output_path, "samples")

    @property
    def image_path(self) -> str:
        """
        The path to the image folder.
        """
        return path.join(self.output_path, "image")

    @property
    @make_path
    def output_path(self) -> str:
        """
        The path to the output information for a search.
        """
        strings = (
            list(filter(
                len,
                [
                    str(conf.instance.output_path),
                    self.path_prefix,
                    self.name,
                    self.identifier,
                ],
            )
            )
        )

        return path.join("", *strings)

    def zip_remove(self):
        """
        Copy files from the sym linked search folder then remove the sym linked folder.
        """

        self._zip()

        if self.remove_files:
            try:
                shutil.rmtree(self.path)
            except (FileNotFoundError, PermissionError):
                pass

    def _zip(self):

        try:
            with zipfile.ZipFile(self._zip_path, "w", zipfile.ZIP_DEFLATED) as f:
                for root, dirs, files in os.walk(self.output_path):

                    for file in files:
                        f.write(
                            path.join(root, file),
                            path.join(
                                root[len(self.output_path):], file
                            ),
                        )

            if self.remove_files:
                shutil.rmtree(self.output_path)

        except FileNotFoundError:
            pass

    def restore(self):
        """
        Copy files from the ``.zip`` file to the samples folder.
        """

        if path.exists(self._zip_path):
            with zipfile.ZipFile(self._zip_path, "r") as f:
                f.extractall(self.output_path)

            os.remove(self._zip_path)

    @property
    @make_path
    def _sym_path(self) -> str:
        return path.join(
            conf.instance.output_path,
            self.path_prefix,
            self.name,
            self.identifier,
        )

    def __eq__(self, other):
        return isinstance(other, AbstractPaths) and all(
            [
                self.path_prefix == other.path_prefix,
                self.name == other.name,
                self.non_linear_name == other.non_linear_name,
            ]
        )

    @property
    def _zip_path(self) -> str:
        return f"{self.output_path}.zip"
