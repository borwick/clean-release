import pytest

from clean_release import Refusal, policy


def load(tmp_path, body):
    (tmp_path / "clean-release.toml").write_text(
        '[release]\nmessage = "m {version}"\n' + body
    )
    return policy.load(tmp_path)


def test_unclassified_path_refuses_listing_each(tmp_path):
    pol = load(tmp_path, '[paths]\ninclude = ["src/**"]\n')
    with pytest.raises(Refusal) as raised:
        policy.classify(pol, ["src/a.py", "notes.txt", "data/x.csv"])
    assert "notes.txt" in str(raised.value) and "data/x.csv" in str(raised.value)


def test_exclude_beats_include(tmp_path):
    pol = load(tmp_path, '[paths]\ninclude = ["**"]\nexclude = ["docs/private/**"]\n')
    shipped, excluded = policy.classify(pol, ["docs/a.md", "docs/private/b.md"])
    assert shipped == ["docs/a.md"] and excluded == ["docs/private/b.md"]


def test_never_ship_beats_include_at_depth(tmp_path):
    pol = load(tmp_path, '[paths]\ninclude = ["**"]\n')
    paths = [
        "a/b/CLAUDE.md",
        "x/notes.org",
        ".claude/other.json",
        "local/x",
        "ok.py",
    ]
    shipped, excluded = policy.classify(pol, paths)
    assert shipped == ["ok.py"]
    assert excluded == paths[:4]


def test_local_is_never_shipped_at_the_root_only(tmp_path):
    pol = load(tmp_path, '[paths]\ninclude = ["**"]\n')
    assert policy.classify(pol, ["src/local/x.py"]) == (["src/local/x.py"], [])


def test_unknown_policy_key_refuses(tmp_path):
    with pytest.raises(Refusal, match=r"unknown key.*inclde"):
        load(tmp_path, '[paths]\ninclde = ["**"]\n')


def test_expect_zero_refuses(tmp_path):
    rule = '[[rewrite]]\npath = "README.md"\npattern = "x"\nreplace = "y"\nexpect = 0\n'
    with pytest.raises(Refusal, match=r"\[\[rewrite\]\] 1: expect = 0"):
        load(tmp_path, rule)


def test_tag_without_version_refuses(tmp_path):
    (tmp_path / "clean-release.toml").write_text(
        '[release]\nmessage = "m"\ntag = "v1"\n'
    )
    with pytest.raises(Refusal, match=r"\{version\}"):
        policy.load(tmp_path)


def test_missing_policy_names_init(tmp_path):
    with pytest.raises(Refusal, match="clean-release init"):
        policy.load(tmp_path)


def test_matcher_uses_full_match():
    assert policy.matches("src/a/b.py", ("src/**",))
    assert not policy.matches("lib/src/b.py", ("src/**",))


def test_scan_defaults_load(tmp_path):
    pol = load(tmp_path, "")
    assert pol.scan == policy.Scan(
        patterns=("home-paths", "emails"),
        binaries=(),
        citations=True,
        citable=(),
        secrets="betterleaks",
    )
    assert pol.verify == policy.Verify(())


def test_unknown_scan_key_refuses(tmp_path):
    with pytest.raises(Refusal, match=r"\[scan\] has unknown key.*citation\b"):
        load(tmp_path, "[scan]\ncitation = true\n")


def test_unknown_pattern_name_refuses(tmp_path):
    with pytest.raises(Refusal, match=r"unknown name.*phones"):
        load(tmp_path, '[scan]\npatterns = ["emails", "phones"]\n')


def test_citations_must_be_a_bool(tmp_path):
    with pytest.raises(Refusal, match="citations = 'yes'"):
        load(tmp_path, '[scan]\ncitations = "yes"\n')


def test_citable_must_be_a_list(tmp_path):
    with pytest.raises(Refusal, match=r"\[scan\] citable must be a list of strings"):
        load(tmp_path, '[scan]\ncitable = "x"\n')


def test_citable_loads_as_a_tuple(tmp_path):
    pol = load(tmp_path, '[scan]\ncitable = ["clean-release.toml", "docs/**"]\n')
    assert pol.scan.citable == ("clean-release.toml", "docs/**")


def test_secrets_none_refuses(tmp_path):
    with pytest.raises(Refusal, match="secrets = 'none'; the scanners are betterleaks"):
        load(tmp_path, '[scan]\nsecrets = "none"\n')


def test_gitleaks_loads(tmp_path):
    assert load(tmp_path, '[scan]\nsecrets = "gitleaks"\n').scan.secrets == "gitleaks"


def test_unknown_verify_key_refuses(tmp_path):
    with pytest.raises(Refusal, match=r"\[verify\] has unknown key.*command\b"):
        load(tmp_path, '[verify]\ncommand = ["make test"]\n')


def test_verify_commands_must_be_a_list(tmp_path):
    with pytest.raises(Refusal, match=r"\[verify\] commands must be a list"):
        load(tmp_path, '[verify]\ncommands = "x"\n')


def test_an_unparsable_command_refuses(tmp_path):
    with pytest.raises(Refusal, match="does not parse"):
        load(tmp_path, "[verify]\ncommands = ['make \"test']\n")


def test_an_empty_command_refuses(tmp_path):
    with pytest.raises(Refusal, match="is empty"):
        load(tmp_path, '[verify]\ncommands = ["  "]\n')
