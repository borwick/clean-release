import re

import pytest

from clean_release import Refusal, machine
from tests.conftest import TERM


def config(home, body):
    (home / ".config/clean-release/config.toml").write_text(
        '[identity]\nname = "S"\nemail = "s@example.org"\n\n' + body
    )


def test_fixture_config_loads(home):
    loaded = machine.load("repo")
    assert loaded.identity.name == "Stager"
    assert loaded.terms.plain == (TERM,)


def test_missing_machine_config_refuses(home):
    (home / ".config/clean-release/config.toml").unlink()
    with pytest.raises(Refusal, match=re.escape("config.toml does not exist")):
        machine.load("repo")


def test_no_terms_file_refuses(home):
    config(home, "")
    with pytest.raises(Refusal, match=r"no terms file for repo.*terms = \[\]"):
        machine.load("repo")


def test_explicit_empty_terms_loads(home):
    config(home, "[repos.repo]\nterms = []\n")
    assert machine.load("repo").terms == machine.Terms((), frozenset())


def test_listed_terms_file_missing_refuses(home):
    config(home, '[repos.repo]\nterms = ["~/nowhere.toml"]\n')
    with pytest.raises(Refusal, match=re.escape("nowhere.toml does not exist")):
        machine.load("repo")


def test_empty_terms_file_refuses(home):
    (home / "empty.toml").write_text("plain = []\n")
    config(home, '[repos.repo]\nterms = ["~/empty.toml"]\n')
    with pytest.raises(Refusal, match="has no entries"):
        machine.load("repo")


def test_malformed_sha256_refuses(home):
    (home / "bad.toml").write_text('sha256 = ["ABC123"]\n')
    config(home, '[repos.repo]\nterms = ["~/bad.toml"]\n')
    with pytest.raises(Refusal, match="64 lowercase hex"):
        machine.load("repo")


def test_terms_union_and_lowercase(home):
    digest = "a" * 64
    (home / "more.toml").write_text(
        f'plain = ["Other-Made-Up"]\nsha256 = ["{digest}"]\n'
    )
    config(
        home,
        '[defaults]\nterms = ["~/.config/clean-release/terms/common.toml"]\n'
        '[repos.repo]\nterms = ["~/more.toml"]\n',
    )
    terms = machine.load("repo").terms
    assert terms.plain == (TERM, "other-made-up")
    assert terms.sha256 == frozenset({digest})
