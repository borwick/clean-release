# MACHINE-CONFIG

`~/.config/clean-release/config.toml` and the terms files it lists:
who commits, and the denylist. Loaded by `src/clean_release/machine.py`.

- **`[identity]`** `name` and `email`, both required: the author,
  committer and tagger of every commit and tag clean-release makes
  (`Identity.env`). Nothing is taken from
  git's own config.
- **Per repo:** `[repos.<name>]`, keyed by the basename of the private
  repo's root, sets `public` and `terms`. `[defaults] terms` applies to
  every repo. A repo's terms files are the union of both lists.
- **Fail closed.** A repo whose union is empty refuses, unless its
  `[repos.<name>]` says `terms = []`. A listed file that is missing
  refuses, and so does one with no entries: the opt-out belongs in the
  config, not in an empty file.
- **A terms file** holds `plain`, terms matched case-insensitively, and
  `sha256`, digests (64 lowercase hex) of terms that must not appear
  even here. Any other key refuses. They load as `Terms`; `check` grades
  the export against them.
- **A digest** is the sha256 hex of a word, or of two words joined by
  one space, lowercased; a word is a run of letters and digits. For a
  term `Foo Bar`: `printf %s 'foo bar' | shasum -a 256`. `check` hashes
  every word and word pair it reads and never prints the match; a path
  holding one prints as `<tag path N>`, its line in `git ls-tree -r
  --name-only <tag>`.
- **Reviewing the terms:** `clean-release doctor` counts, per terms file
  and entry in file order, the files at the private repo's HEAD that hold
  it, path included; a 0 is a candidate to prune.
