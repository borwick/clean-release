# POLICY

`clean-release.toml`, at the root of the private repo: what ships and how
it is rewritten. Loaded and validated by `src/clean_release/policy.py`;
`clean-release init` writes a starter (`src/clean_release/starter.py`).

- **Read from the working tree, never from a tag.** The tag's name comes
  from `[release] tag`, so the policy is read before the tag is known.
  Only the export's content comes from the tag. The policy itself never
  ships.
- **Tables:** `[release]` (`tag`, `message`, `public`, `unclassified`,
  `disclosure`),
  `[paths]` (`include`, `exclude`), `[[rewrite]]` (`path`, `pattern`,
  `replace`, `expect`), `[scan]` (`patterns`, `binaries`, `citations`,
  `citable`, `secrets`) and `[verify]` (`commands`). An unknown
  key in any table refuses by name.
- **Classification:** every path in the tag's tree is matched with
  `PurePosixPath.full_match`, in this order: the built-in never-ship list
  (`NEVER_SHIP`), then `exclude`, then `include`. A path matching none of
  them refuses the release. No `include` overrides the never-ship list,
  whose globs match at any depth, except `local/**` at the root only.
- **`[release] disclosure`** names the AI disclosure document, a path in
  the export, such as `docs/ai-disclosure.md`. When it is set, `check`
  fails an export that does not ship it as a regular file (lesson 9: the
  snapshot commit drops the private history's `Co-Authored-By`
  trailers). Optional; `init` sets it and writes a starter document for
  the owner to edit, keeping one that exists.
- **Rewrites** run in file order on shipped files. `path` is exact, not
  a glob. Each must match exactly `expect` times (1 or more), or the
  release refuses.
- **`[scan]`:** `patterns`, the built-in generic patterns by name,
  `home-paths` and `emails`, both by default; `binaries`, globs of the
  binary files allowed to ship; `citations`, on by default, failing a
  shipped file that names a path that did not ship; `citable`, globs of
  unshipped paths the citations check never flags, a directory citable
  when every path under it is. Placeholder home
  paths and documentation addresses (RFC 2606 and 6761), a `noreply`
  address and the machine config's identity pass. `secrets` names the
  secrets scanner, `betterleaks` by default or `gitleaks` (`SCANNERS` in
  `scanner.py`); there is no opt-out, and a scanner missing from PATH
  refuses `check`.
- **`[verify] commands`:** each a command line, split with `shlex`, run
  without a shell in a temporary copy of the export; a nonzero exit fails
  `check`.
