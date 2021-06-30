import pytest

import autofit as af
from autofit.mock import mock
from autofit.mock import mock_real
from autofit.text import formatter as frm


def test_parameterization():
    model = af.Collection(
        collection=af.Collection(
            gaussian=af.Model(af.Gaussian)
        )
    )

    parameterization = model.parameterization
    assert parameterization == (
        """collection
    gaussian                                                                              Gaussian (N=3)"""
    )


def test_root():
    model = af.Model(af.Gaussian)
    parameterization = model.parameterization
    print(parameterization)
    assert parameterization == (
        '(root)                                                                                    Gaussian (N=3)'
    )


@pytest.fixture(name="formatter")
def make_info_dict():
    formatter = frm.TextFormatter(line_length=20, indent=4)
    formatter.add(("one", "one"), 1)
    formatter.add(("one", "two"), 2)
    formatter.add(("one", "three", "four"), 4)
    formatter.add(("three", "four"), 4)

    return formatter


class TestGenerateModelInfo:
    def test_add_to_info_dict(self, formatter):
        print(formatter.dict)
        assert formatter.dict == {
            "one": {"one": 1, "two": 2, "three": {"four": 4}},
            "three": {"four": 4},
        }

    def test_info_string(self, formatter):
        ls = formatter.list

        assert ls[0] == "one"
        assert len(ls[1]) == 21
        assert ls[1] == "    one             1"
        assert ls[2] == "    two             2"
        assert ls[3] == "    three"
        assert ls[4] == "        four        4"
        assert ls[5] == "three"
        assert ls[6] == "    four            4"

    def test_basic(self):
        mm = af.ModelMapper()
        mm.mock_class = mock.MockClassx2
        model_info = mm.info

        assert (
                model_info
                == """mock_class
    one                                                                                   UniformPrior, lower_limit = 0.0, upper_limit = 1.0
    two                                                                                   UniformPrior, lower_limit = 0.0, upper_limit = 2.0"""
        )

    def test_with_instance(self):
        mm = af.ModelMapper()
        mm.mock_class = mock.MockClassx2

        mm.mock_class.two = 1.0

        model_info = mm.info

        assert (
                model_info
                == """mock_class
    one                                                                                   UniformPrior, lower_limit = 0.0, upper_limit = 1.0
    two                                                                                   1.0"""
        )

    def test_with_tuple(self):
        mm = af.ModelMapper()
        mm.tuple = (0, 1)

        assert (
                mm.info
                == "tuple                                                                                     (0, 1)"
        )

    # noinspection PyUnresolvedReferences
    def test_tuple_instance_model_info(self, mapper):
        mapper.profile = mock_real.EllSersicCore
        info = mapper.info

        mapper.profile.centre_0 = 1.0

        assert len(mapper.profile.centre.instance_tuples) == 1
        assert len(mapper.profile.instance_tuples) == 1

        assert len(info.split("\n")) == len(mapper.info.split("\n"))
