# clean-release

Carry a private git repo to its public twin, one checked snapshot commit
per version.

A private repo keeps everything: planning, history, notes, names that must
not leave it. clean-release publishes the part worth publishing. Each
release of the private repo becomes exactly one commit and one annotated
tag in a separate public repo, built from the private release tag's tree
after a policy is applied. No private history ships, and nothing ships
that the owner has not seen and approved.

clean-release never pushes, uploads or creates a remote: it prints those
commands for the owner to run.

## Install

Python 3.14 and [uv](https://docs.astral.sh/uv/):

```
uv tool install git+https://github.com/borwick/clean-release
```

`check` runs a secrets scanner, [betterleaks](https://github.com/betterleaks/betterleaks)
by default; `clean-release doctor` says how to install it when it is missing.

## How it works

Two files say what a release may contain:

- **The policy**, `clean-release.toml` in the private repo: which paths
  ship and which never do, text rewritten on the way out, and the checks
  to run. Every tracked file must be named one way or the other; an
  unnamed file stops the release. The policy itself never ships.
- **The machine config**, `~/.config/clean-release/config.toml`, outside
  every repo: the name and email public commits and tags are made under,
  where each public repo lives, and the terms files listing words a
  release must never contain. A missing terms file stops the release.

A release, after tagging `v1.2.0` in the private repo:

```
clean-release init           # once: write a starter policy to edit
clean-release doctor         # the machine config, scanner and public tree
clean-release stage 1.2.0    # build the export from the tag's tree
clean-release check          # grade it; nonzero on any finding
clean-release diff           # what would change in the public repo
clean-release approve        # run check again and approve this exact tree
clean-release commit         # one commit and tag in the public repo
clean-release status         # last public version, staged, approved, clean
```

`check` looks for the denylisted terms (in the content, the path names
and the release message, never printing the term it found), secrets,
unlisted binaries, symlinks out of the tree, submodules and LFS pointers;
and, as the policy's `[scan]` turns them on, home-directory paths, email
addresses, and citations of paths that do not ship.
It then runs the policy's `[verify]` commands, such as the test suite, on
a copy of the export.

`commit` refuses a tree that was not approved or changed since, a public
repo that is dirty, has moved past its last release, or already holds the
version, and a version not newer than the last. It never deletes or
re-creates the public directory.

## Reference

- [The policy](https://github.com/borwick/clean-release/blob/main/docs/data-structures/POLICY.md)
- [The machine config](https://github.com/borwick/clean-release/blob/main/docs/data-structures/MACHINE-CONFIG.md)
- [The staging repo](https://github.com/borwick/clean-release/blob/main/docs/data-structures/STAGING-REPO.md)
- [The public repo](https://github.com/borwick/clean-release/blob/main/docs/data-structures/PUBLIC-REPO.md)

## How this was written

clean-release was written with Claude Code;
[the disclosure](https://github.com/borwick/clean-release/blob/main/docs/ai-disclosure.md)
says who did what.

## License

BSD 3-Clause; see
[LICENSE](https://github.com/borwick/clean-release/blob/main/LICENSE).
