from autofit import exc


class Assertion:
    def __init__(
            self,
            lower,
            greater
    ):
        """
        Describes an assertion that the physical values associated with
        the lower and greater priors are lower and greater respectively.

        Parameters
        ----------
        lower: Prior
            A prior object with physical values that must be lower
        greater: Prior
            A prior object with physical values that must be greater
        """
        self.lower = lower
        self.greater = greater
        self.name = None

    def __gt__(self, other):
        return CompoundAssertion(
            self,
            self.lower > other
        )

    def __lt__(self, other):
        return CompoundAssertion(
            self,
            self.greater < other
        )

    def __call__(self, arg_dict: dict):
        """
        Assert that the value in the dictionary associated with the lower
        prior is lower than the value associated with the greater prior.

        Parameters
        ----------
        arg_dict
            A dictionary mapping priors to physical values.

        Raises
        ------
        FitException
            If the assertion is not met
        """
        if isinstance(
                self.lower,
                float
        ):
            lower = self.lower
        else:
            lower = arg_dict[
                self.lower
            ]

        if isinstance(
                self.greater,
                float
        ):
            greater = self.greater
        else:
            greater = arg_dict[
                self.greater
            ]

        if lower > greater:
            raise exc.FitException(
                "Assertion failed" + (
                    "" if self.name is None else f" '{self.name}'"
                )
            )


class CompoundAssertion:
    def __init__(self, assertion_1, assertion_2):
        self.assertion_1 = assertion_1
        self.assertion_2 = assertion_2

    def __call__(self, arg_dict: dict):
        self.assertion_1(arg_dict)
        self.assertion_2(arg_dict)
