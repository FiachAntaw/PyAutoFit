import pytest

from autofit.tools.edenise import LineItem


@pytest.fixture(
    autouse=True
)
def set_flag(package):
    package._should_remove_type_annotations = True


def test_is_function(
        package
):
    assert LineItem(
        "def my_func():",
        parent=package
    ).is_function is True


def test_regression(
        package
):
    assert LineItem(
        """def path_instances_of_class(
        obj, cls: type, ignore_class: Optional[Union[type, Tuple[type]]] = None
):""",
        parent=package
    ).target_string == """def path_instances_of_class(
        obj, cls, ignore_class= None
):"""


class TestStripAnnotations:
    @pytest.mark.parametrize(
        "string",
        [
            "def my_func() -> dict:",
            "def my_func()->dict:",
            "def my_func() -> dict :",
        ]
    )
    def test_strip_return_type(
            self,
            package,
            string
    ):
        assert LineItem(
            string,
            parent=package
        ).target_string == "def my_func():"

    def test_across_new_lines(
            self,
            package
    ):
        line_item = LineItem(
            """def my_func(
                one: dict,
                two: dict
            ):
            """,
            parent=package
        )
        assert line_item.is_function
        assert line_item.target_string == """def my_func(
                one,
                two
            ):
            """

    @pytest.mark.parametrize(
        "annotation",
        [
            "Optional[Union[list, str]]",
            "Optional[Union[type, Tuple[type]]]"
        ]
    )
    def test_complex_type_annotation(
            self,
            package,
            annotation
    ):
        assert LineItem(
            f"def my_func(complex: {annotation}):",
            parent=package
        ).target_string == "def my_func(complex):"

    def test_dont_convert_dict(
            self,
            package
    ):
        string = "{'one': 1, 'two': 2}"
        assert LineItem(
            string,
            parent=package
        ).target_string == string

    @pytest.mark.parametrize(
        "string",
        [
            "def my_func() -> dict:",
            "def my_func()->dict:",
            "def my_func() -> dict :",
        ]
    )
    def test_strip_return_type(
            self,
            package,
            string
    ):
        assert LineItem(
            string,
            parent=package
        ).target_string == "def my_func():"

    def test_multiple_arguments(
            self,
            package
    ):
        assert LineItem(
            "def my_func(arg1: dict, arg2: dict):",
            parent=package
        ).target_string == "def my_func(arg1, arg2):"

    @pytest.mark.parametrize(
        "string",
        [
            "def my_func(arg: dict):",
            "def my_func(arg: dict ):",
            "def my_func(arg : dict ):",
        ]
    )
    def test_strip_argument_type(
            self,
            package,
            string
    ):
        assert LineItem(
            string,
            parent=package
        ).target_string == "def my_func(arg):"
