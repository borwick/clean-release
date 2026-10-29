"""clean-release: carry a private repo to its public twin."""

from importlib.metadata import version

__version__ = version("clean-release")


class Refusal(Exception):
    """The input is wrong: the message says what is wrong and what would be right."""
