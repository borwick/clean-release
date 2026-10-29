import os

from clean_release import scan
from clean_release.machine import Terms
from tests.conftest import TERM

PLAIN = Terms((TERM,), frozenset())
ME = "me" + "@" + "mydomain.dev"


def kinds(found):
    return [(f.line, f.kind) for f in found]


def test_plain_term_is_case_insensitive_and_unbounded():
    text = f"ok\nx{TERM.upper()}y\n"
    assert kinds(scan.terms("f", text, PLAIN)) == [(2, "denylist term")]


def test_digest_matches_a_word_and_a_pair_across_a_line_break():
    terms = Terms((), frozenset({scan.digest("wombat"), scan.digest("blue moon")}))
    found = scan.terms("f", "a Wombat_x\nblue\nMoon\n", terms)
    assert kinds(found) == [(1, "denylist digest"), (2, "denylist digest")]


def test_where_suffixes_the_kind():
    found = scan.terms("f", TERM, PLAIN, " in the rewrite source")
    assert kinds(found) == [(1, "denylist term in the rewrite source")]


def test_finding_never_carries_the_text():
    assert str(scan.Finding("a/b.md", 3, "denylist term")) == "a/b.md:3: denylist term"
    assert str(scan.Finding("a/b.md", None, "submodule")) == "a/b.md: submodule"


def test_home_paths_and_placeholders():
    users, home = os.sep + "Users" + os.sep, os.sep + "home" + os.sep
    leaks = f"{users}alice\n{home}bob/x\nC:\\Users\\carol\n"
    placeholders = f"{users}you/x {home}<user> {home}$USER\n"
    names = ("home-paths",)
    assert kinds(scan.patterns("f", leaks, names, ME)) == [
        (1, "home path"),
        (2, "home path"),
        (3, "home path"),
    ]
    assert scan.patterns("f", placeholders, names, ME) == []


def test_emails_allow_documentation_noreply_and_identity():
    at = "@"
    allowed = [
        f"a{at}example.com",
        f"b{at}mail.example.org",
        f"c{at}site.test",
        f"d{at}host.localhost",
        f"noreply{at}corp.io",
        ME.upper(),
    ]
    text = " ".join(allowed) + f"\nbob{at}corp.io\n"
    assert kinds(scan.patterns("f", text, ("emails",), ME)) == [(2, "email")]


def test_patterns_run_only_when_named():
    assert scan.patterns("f", "bob" + "@" + "corp.io", ("home-paths",), ME) == []
