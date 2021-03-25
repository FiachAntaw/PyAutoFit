import json
import os
import pickle
import shutil
import zipfile
from configparser import NoSectionError
from functools import wraps
from os import path

from autoconf import conf
from autofit.mapper import link
from autofit.non_linear import samples
from autofit.non_linear.log import logger
from autofit.text import formatter


def make_path(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        full_path = func(*args, **kwargs)
        os.makedirs(full_path, exist_ok=True)
        return full_path

    return wrapper


def convert_paths(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if len(args) > 1:
            raise AssertionError(
                "Only phase name is allowed to be a positional argument in a phase constructor"
            )

        first_arg = kwargs.pop("paths", None)
        if first_arg is None and len(args) == 1:
            first_arg = args[0]

        if isinstance(first_arg, Paths):
            return func(self, paths=first_arg, **kwargs)

        if first_arg is None:
            first_arg = kwargs.pop("name", None)

        # TODO : Using the class nam avoids us needing to mak an sintance - still cant get the kwargs.get() to work
        # TODO : nicely though.

        search = kwargs.get("search")

        if search is not None:

            search = kwargs["search"]
            search_name = search._config("tag", "name", str)

            def non_linear_tag_function():
                return search.tag

        else:

            search_name = None

            def non_linear_tag_function():
                return ""

        paths = Paths(
            name=first_arg,
            tag=kwargs.pop("phase_tag", None),
            path_prefix=kwargs.pop("path_prefix", None),
            non_linear_name=search_name,
            non_linear_tag_function=non_linear_tag_function,
        )

        if search is not None:
            search.paths = paths

        func(self, paths=paths, **kwargs)

    return wrapper


class Paths:
    def __init__(
            self,
            name="",
            tag=None,
            path_prefix=None,
            non_linear_name=None,
            non_linear_tag_function=lambda: ""
    ):
        """Manages the path structure for `NonLinearSearch` output, for analyses both not using and using the phase
        API. Use via non-linear searches requires manual input of paths, whereas the phase API manages this using the
        phase attributes.

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
            The name of the non-linear search, which is used as a folder name after the ``path_prefix``. For phases
            this name is the ``name``.
        tag : str
            A tag for the non-linear search, typically used for instances where the same data is fitted with the same
            model but with slight variants. For phases this is the phase_tag.
        path_prefix : str
            A prefixed path that appears after the output_path but beflore the name variable.
        non_linear_name : str
            The name of the non-linear search, e.g. Emcee -> emcee. Phases automatically set up and use this variable.
        """

        self.path_prefix = path_prefix or ""
        self.name = name or ""
        self.tag = tag or ""
        self.non_linear_name = non_linear_name or ""
        self.non_linear_tag_function = non_linear_tag_function

        try:
            self.remove_files = conf.instance["general"]["output"]["remove_files"]

            if conf.instance["general"]["hpc"]["hpc_mode"]:
                self.remove_files = True
        except NoSectionError as e:
            logger.exception(e)

    def save_all(self, model, info, search, pickle_files):
        self._save_model_info(model=model)
        self._save_parameter_names_file(model=model)
        self._save_info(info=info)
        self._save_search(search=search)
        self._save_model(model=model)
        self._save_metadata(
            search_name=type(self).__name__.lower()
        )
        self._move_pickle_files(pickle_files=pickle_files)

    def _save_metadata(self, search_name):
        """
        Save metadata associated with the phase, such as the name of the pipeline, the
        name of the phase and the name of the dataset being fit
        """
        with open(path.join(self.make_path(), "metadata"), "a") as f:
            f.write(f"""name={self.name}
tag={self.tag}
non_linear_search={search_name}
""")

    def _move_pickle_files(self, pickle_files):
        """
        Move extra files a user has input the full path + filename of from the location specified to the
        pickles folder of the Aggregator, so that they can be accessed via the aggregator.
        """
        if pickle_files is not None:
            [shutil.copy(file, self.pickle_path) for file in pickle_files]

    def _save_model_info(self, model):
        """Save the model.info file, which summarizes every parameter and prior."""
        with open(self.file_model_info, "w+") as f:
            f.write(f"Total Free Parameters = {model.prior_count} \n\n")
            f.write(model.info)

    def _save_parameter_names_file(self, model):
        """Create the param_names file listing every parameter's label and Latex tag, which is used for *corner.py*
        visualization.

        The parameter labels are determined using the label.ini and label_format.ini config files."""

        parameter_names = model.model_component_and_parameter_names
        parameter_labels = model.parameter_labels
        subscripts = model.subscripts
        parameter_labels_with_subscript = [f"{label}_{subscript}" for label, subscript in
                                           zip(parameter_labels, subscripts)]

        parameter_name_and_label = []

        for i in range(model.prior_count):
            line = formatter.add_whitespace(
                str0=parameter_names[i], str1=parameter_labels_with_subscript[i], whitespace=70
            )
            parameter_name_and_label += [f"{line}\n"]

        formatter.output_list_of_strings_to_file(
            file=self.file_param_names, list_of_strings=parameter_name_and_label
        )

    def _save_info(self, info):
        """
        Save the dataset associated with the phase
        """
        with open(path.join(self.pickle_path, "info.pickle"), "wb") as f:
            pickle.dump(info, f)

    def _save_search(self, search):
        """
        Save the search associated with the phase as a pickle
        """
        with open(self.make_search_pickle_path(), "w+b") as f:
            f.write(pickle.dumps(search))

    def _save_model(self, model):
        """
        Save the model associated with the phase as a pickle
        """
        with open(self.make_model_pickle_path(), "w+b") as f:
            f.write(pickle.dumps(model))

    def save_samples(self, samples):
        """
        Save the final-result samples associated with the phase as a pickle
        """
        samples.write_table(filename=self.samples_file)
        samples.info_to_json(filename=self.info_file)

        with open(self.make_samples_pickle_path(), "w+b") as f:
            f.write(pickle.dumps(samples))

    def __getstate__(self):
        state = self.__dict__.copy()
        state["non_linear_tag"] = state.pop("non_linear_tag_function")()
        return state

    def __setstate__(self, state):
        non_linear_tag = state.pop("non_linear_tag")
        self.non_linear_tag_function = lambda: non_linear_tag
        self.__dict__.update(state)

    @property
    def non_linear_tag(self):
        return self.non_linear_tag_function()

    @property
    def path(self):
        return link.make_linked_folder(self.sym_path)

    def __eq__(self, other):
        return isinstance(other, Paths) and all(
            [
                self.path_prefix == other.path_prefix,
                self.name == other.name,
                self.tag == other.tag,
                self.non_linear_name == other.non_linear_name,
            ]
        )

    @property
    @make_path
    def samples_path(self) -> str:
        """
        The path to the samples folder.
        """
        return path.join(self.output_path, "samples")

    @property
    def _samples_file(self) -> str:
        return path.join(self.samples_path, "samples.csv")

    @property
    def _info_file(self) -> str:
        return path.join(self.samples_path, "info.json")

    @property
    def image_path(self) -> str:
        """
        The path to the image folder.
        """
        return path.join(self.output_path, "image")

    @property
    def zip_path(self) -> str:
        return f"{self.output_path}.zip"

    @property
    @make_path
    def output_path(self) -> str:
        """
        The path to the output information for a phase.
        """
        strings = (
            list(filter(
                len,
                [
                    str(conf.instance.output_path),
                    self.path_prefix,
                    self.name,
                    self.tag,
                    self.non_linear_tag,
                ],
            )
            )
        )

        return path.join("", *strings)

    @property
    def is_complete(self):
        return path.exists(
            self._has_completed_path
        )

    def completed(self):
        open(self._has_completed_path, "w+").close()

    @property
    def _has_completed_path(self) -> str:
        """
        A file indicating that a `NonLinearSearch` has been completed previously
        """
        return path.join(self.output_path, ".completed")

    @property
    @make_path
    def sym_path(self) -> str:
        return path.join(
            conf.instance.output_path,
            self.path_prefix,
            self.name,
            self.tag,
            self.non_linear_tag,
        )

    @property
    def file_param_names(self) -> str:
        return path.join(self.samples_path, "model.paramnames")

    @property
    def file_model_info(self) -> str:
        return path.join(self.output_path, "model.info")

    @property
    def file_search_summary(self) -> str:
        return path.join(self.output_path, "search.summary")

    @property
    def file_results(self):
        return path.join(self.output_path, "model.results")

    @property
    @make_path
    def pickle_path(self) -> str:
        return path.join(self.make_path(), "pickles")

    def make_search_pickle_path(self) -> str:
        """
        Returns the path at which the search pickle should be saved
        """
        return path.join(self.pickle_path, "search.pickle")

    def make_model_pickle_path(self):
        """
        Returns the path at which the model pickle should be saved
        """
        return path.join(self.pickle_path, "model.pickle")

    def make_samples_pickle_path(self) -> str:
        """
        Returns the path at which the search pickle should be saved
        """
        return path.join(self.pickle_path, "samples.pickle")

    @make_path
    def make_path(self) -> str:
        """
        Returns the path to the folder at which the metadata should be saved
        """
        return path.join(
            conf.instance.output_path,
            self.path_prefix,
            self.name,
            self.tag,
            self.non_linear_tag,
        )

    def zip_remove(self):
        """
        Copy files from the sym linked search folder then remove the sym linked folder.
        """

        self.zip()

        if self.remove_files:
            try:
                shutil.rmtree(self.path)
            except (FileNotFoundError, PermissionError):
                pass

    def restore(self):
        """
        Copy files from the ``.zip`` file to the samples folder.
        """

        if path.exists(self.zip_path):
            with zipfile.ZipFile(self.zip_path, "r") as f:
                f.extractall(self.output_path)

            os.remove(self.zip_path)

    def zip(self):

        try:
            with zipfile.ZipFile(self.zip_path, "w", zipfile.ZIP_DEFLATED) as f:
                for root, dirs, files in os.walk(self.output_path):

                    for file in files:

                        # TODO : I removed lstrip("/") here, I think it is ok...

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

    def load_samples(self):
        return samples.load_from_table(
            filename=self._samples_file
        )

    def load_samples_info(self):
        with open(self._info_file) as infile:
            return json.load(infile)
