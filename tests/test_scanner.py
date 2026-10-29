import pytest

from clean_release import Refusal, scanner
from clean_release.scan import Finding
from tests.conftest import path_without_scanners, token


def planted(tmp_path):
    export = tmp_path / "export"
    (export / "src").mkdir(parents=True)
    (export / "src/conf.py").write_text(f'X = 1\nT = "{token()}"\n')
    return export


def test_a_planted_secret_is_a_finding_without_the_secret(tmp_path):
    assert scanner.scan("betterleaks", planted(tmp_path)) == [
        Finding("src/conf.py", 2, "secret (github-pat)")
    ]


def test_config_in_the_environment_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("BETTERLEAKS_CONFIG", str(tmp_path / "no-such.toml"))
    monkeypatch.setenv("GITLEAKS_CONFIG", str(tmp_path / "no-such.toml"))
    assert len(scanner.scan("betterleaks", planted(tmp_path))) == 1


def test_a_scanner_error_refuses(tmp_path):
    with pytest.raises(Refusal, match="betterleaks failed with exit"):
        scanner.scan("betterleaks", tmp_path / "missing")


def test_present_scanner_is_not_missing():
    assert scanner.missing("betterleaks") is None


def test_missing_scanner_names_the_hint(tmp_path, monkeypatch):
    path_without_scanners(tmp_path, monkeypatch)
    message = scanner.missing("betterleaks")
    assert "`betterleaks` is not on PATH" in message
    assert "brew install betterleaks" in message
    assert "https://github.com/betterleaks/betterleaks" in message
    assert "secrets =" not in message


def test_missing_scanner_names_another_on_path(tmp_path, monkeypatch):
    path_without_scanners(tmp_path, monkeypatch, "gitleaks")
    assert '`[scan] secrets = "gitleaks"`' in scanner.missing("betterleaks")


def test_no_validation_flag():
    assert not any("validation" in a for a in scanner.argv("x", "e", "r"))
