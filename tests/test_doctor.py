import hashlib

from clean_release.cli import main
from tests.conftest import TERM, commit_all, git, path_without_scanners


def doctor(capsys):
    code = main(["doctor"])
    return code, capsys.readouterr().out


def public_tree(home, path):
    config = home / ".config/clean-release/config.toml"
    config.write_text(config.read_text() + f'\n[repos.repo]\npublic = "{path}"\n')


def test_a_good_setup_is_all_ok(repo, home, tmp_path, capsys):
    (tmp_path / "public").mkdir()
    public_tree(home, tmp_path / "public")
    code, out = doctor(capsys)
    assert code == 0, out
    assert "ok: machine config" in out and "1 terms file(s), 1 term(s)" in out
    assert "ok: scanner betterleaks: " in out
    assert "ok: public tree" in out and out.endswith("doctor: all ok\n")
    assert TERM not in out


def test_an_unset_public_tree_is_a_problem(repo, capsys):
    code, out = doctor(capsys)
    assert code == 1
    assert "ok: machine config" in out and "ok: scanner betterleaks" in out
    assert "problem: no public tree" in out and "doctor: 1 problem(s)" in out


def test_a_missing_scanner_is_a_problem(repo, tmp_path, monkeypatch, capsys):
    path_without_scanners(tmp_path, monkeypatch)
    code, out = doctor(capsys)
    assert code == 1
    assert "problem: `betterleaks` is not on PATH; install it: brew install" in out


def test_a_dirty_public_tree_is_a_problem(repo, home, tmp_path, capsys):
    public = tmp_path / "public"
    public.mkdir()
    git(public, "init", "-q")
    (public / "stray.txt").write_text("x\n")
    public_tree(home, public)
    code, out = doctor(capsys)
    assert code == 1
    assert "has uncommitted changes" in out


def test_a_missing_machine_config_is_a_problem(repo, home, capsys):
    (home / ".config/clean-release/config.toml").unlink()
    code, out = doctor(capsys)
    assert code == 1
    assert "problem: " in out and "config.toml does not exist" in out


def test_terms_are_counted_per_entry_never_shown(repo, home, capsys):
    absent = "quorvelling"
    digest = hashlib.sha256(b"zibblethorp").hexdigest()
    (home / ".config/clean-release/terms/common.toml").write_text(
        f'plain = ["{TERM}", "{absent}"]\nsha256 = ["{digest}"]\n'
    )
    (repo / "a.txt").write_text(f"{TERM}\nZibblethorp\n")
    (repo / "b.txt").write_text(f"{TERM}\n")
    commit_all(repo, "terms")
    _, out = doctor(capsys)
    assert "files at HEAD per entry: plain [2, 0], sha256 [1]" in out
    assert TERM not in out and absent not in out and "zibblethorp" not in out.lower()
