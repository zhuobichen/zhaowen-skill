# Case study: Codex Desktop session store, sandbox, and auto-review

A worked example of reverse engineering a 318 MB single-binary Rust
application on Windows, where the interesting architecture turned out to be
readable from PE export tables, panic-path strings, and an unencrypted local
SQLite projection — with no decompiler and no REA semantic pass.

Target: `OpenAI Codex` Desktop for Windows, `cli_version 0.162.0-alpha.2`,
`originator: Codex Desktop`. Rust, built with rustc 1.95.0 MSVC.

Questions: where does the agent keep its conversation history, how does the
Windows sandbox isolate tool calls, and what does an external AI need in order
to reuse any of it.

## Why this case is worth reading

Four findings generalize beyond this product:

1. **An append-only JSONL log plus byte-offset columns in SQLite is a
   reconstructible store, not a cache.** `thread_turns.rollout_byte_offset`
   proves the database is a projection and the JSONL is the source of truth —
   which makes the whole history readable with `sqlite3` and a text editor.
2. **Export tables still carry hard evidence in a 318 MB binary.** 151 exports
   named the vendored regex engine, the TLS library and its exact version, and
   the bundled tree-sitter grammars, without a single disassembled instruction.
3. **A helper executable's _imports_ reveal a privilege-escalation design.**
   One 17 MB binary holding `NetUserAdd`, `NetLocalGroupAddMembers` and
   `FwpmFilterAdd0` in the same import table is a far clearer statement of
   intent than any amount of string archaeology on the main executable.
4. **Not every large target needs the full pipeline.** Skipping REA entirely was
   a deliberate, recorded decision here — the substitute evidence was graded
   separately, exactly as the evidence-discipline section requires.

## Route and outcome

| Step | Tool | Outcome |
| --- | --- | --- |
| Artifact identity | `pefile` section/entropy pass | 8 sections, `.pdata` entropy 7.519 |
| Export surface | `pefile` export dump | 151 exports: Oniguruma, tree-sitter, AWS-LC 0.45.0 |
| Import surface | `pefile` import dump | full token-manipulation, SSPI, WFP firewall, cert-chain set |
| Source map | ASCII path regex over `.rdata` | 678 paths, **456 first-party** |
| Config schema | keyword regex over `.rdata` | serde field names → full `ConfigToml` shape |
| State store | direct read of 6 SQLite files | **plaintext, unencrypted** |
| REA semantic layer | not invoked | see below |

**REA was not run.** `inspect-artifact` would have returned a sha256 and an
`evidence_id` and nothing else for a stripped 318 MB Rust binary; `analyze`
would have needed Ghidra or IDA, which are not installed. Rather than record
another row of `provider_unavailable`, the substitute route was chosen up
front and the substitution is stated here so the evidence grade is not
mistaken for REA graph output.

## Reading the export table instead of disassembling

The 151 exports fall into four families, and each one dates or fingerprints
the build:

| Family | Count | What it establishes |
| --- | --- | --- |
| `onig_*` | ~130 | Oniguruma regex engine is vendored |
| `OnigSyntaxRuby`, `OnigSyntaxOniguruma` | 2 | **Ruby-syntax regexes** are in use somewhere |
| `tree_sitter_bash`, `tree_sitter_powershell` | 2 | only these two grammars are separately exported |
| `aws_lc_0_45_0_jent_*` | 9 | **AWS-LC 0.45.0** — the newest crypto of the targets analyzed so far |
| `CrashForExceptionInNonABICompliantCodeRange` | 1 | crash capture |

Two cautions. Absence of a tree-sitter grammar from the export table does not
mean the parser is missing — statically registered and dynamically loaded
grammars both hide. And the Ruby regex dialect is a _lead_, not a conclusion:
the most plausible consumers are policy matching and hook matching, but no
call site was recovered.

## Panic strings recover the module tree

Rust builds retain source paths in panic and log payloads, so a regex over the
readable sections yields a directory tree for free — no decompiler, no symbol
server. 678 unique paths, of which 222 carry the crates.io hash prefix and
**456 are first-party**:

| Directory | Files | Responsibility |
| --- | --- | --- |
| `src/app` | 28 | session lifecycle, thread manager, startup, pets |
| `src/tools` | 22 | registry / router / handlers / parallel / code_mode / unified_exec |
| `src/transport` | 21 | stdio / websocket / SSE / streamable_http / remote_control |
| `src/request_processors` | 21 | thread / turn / config / apps / plugins / windows_sandbox |
| `src/chatwidget` | 17 | TUI |
| `src/session` | 17 | turn / context / mcp / token_budget / review |

Standouts: `guardian/` (auto-review), `transport/remote_control/` (device
enrollment), `endpoint/realtime_websocket/` (**two protocol generations
side by side** — `protocol_v1`, `protocol_v2`, `protocol_frameless_bidi`),
`skills_{config,watcher}.rs` plus `mcp_skill_dependencies.rs` (**a skill can
declare an MCP dependency**), and `external_agent_config_migration/`.

An anomaly worth recording: `.pdata` has entropy **7.519** against `.text`'s
6.221. That section is nominally the exception-handling table, so it is
carrying a large volume of compressed or encrypted payload. Any tool that
extracts strings per-section will misbehave on it.

## The store: JSONL is truth, SQLite is a projection

Six SQLite files under `~/.codex/`, **all plaintext**:

| File | Size | Notable tables (rows) |
| --- | --- | --- |
| `state_5.sqlite` | 448 KB | `threads`(78), `projects`(8), `thread_spawn_edges`(11), `thread_dynamic_tools`, `remote_control_enrollments`, `_sqlx_migrations`(59) |
| `thread_history_1.sqlite` | 78 MB | `thread_items`(11770), `thread_turns`(400) |
| `logs_2.sqlite` | 73 MB | `logs`(18852) |
| `memories_1.sqlite` | 44 KB | `consolidation_progress`, `stage1_outputs`, `jobs` |
| `goals_1.sqlite` | 32 KB | `thread_goals`, `thread_goal_continuation_deferrals` |
| `queue_1.sqlite` | 40 KB | `queued_items`, `queued_thread_revisions` |

The decisive schema detail is three columns on `thread_turns`:

```
rollout_byte_offset
rollout_end_ordinal
rollout_end_byte_offset
```

`threads.rollout_path` points into `~/.codex/sessions/YYYY/MM/DD/`. Those
offset columns mean the database holds **pointers into the log, not copies of
the content** — the 78 MB history database can be deleted and rebuilt from the
JSONL. That is why `rollout_migration_state` and `backfill_state` exist as
tables. The JSONL tree is 746 MB across 33 files; each line is an event, and
the first is `session_meta` carrying `cwd`, `originator`, `cli_version` and
`base_instructions`.

This inverts the TRAE conclusion. There, the vector index was SQLCipher-encrypted
and therefore unusable, and the practical answer was "read the Markdown, skip
the vectors". Here there is nothing to unlock — the cheapest path is also the
complete one.

One schema column explains a whole subsystem:

```sql
thread_dynamic_tools(thread_id, position, name, description,
                    input_schema, defer_loading, namespace)
```

`defer_loading` is tool **deferred loading** — MCP tool descriptions are not
all pushed into context at startup, which is why `src/session/mcp_prewarm.rs`
exists. `namespace` disambiguates same-named tools across servers.
`input_schema` being persisted means third-party tool schemas sit in a local
plaintext database.

## The Windows sandbox has four paths and one privileged helper

The sandbox core is a vendored crate (`mxc-2dea3fbc8fb244f2`). Four backends
exist: **BaseContainer (MXC)** as default, **AppContainer** as the degradation
path, a **ProcessContainer** dispatcher, and a **PSEC/V2** path. Linux uses
in-tree Landlock (`sandboxing/src/landlock.rs`).

Isolation primitives, straight from the import table:

```
CreateRestrictedToken                        restricted token
DeriveAppContainerSidFromAppContainerName    AppContainer SID
CreateProcessAsUserW                         launch under the token
SetEntriesInAclW / BuildSecurityDescriptorW  DENY ACEs
CreateJobObjectW                             job-object limits
```

Under the AppContainer fallback, denial is expressed as **DENY ACEs on a
DACL** rather than as capabilities. That explains a limitation recovered
verbatim from the binary: `filesystem.deniedPaths` **cannot be enforced** on
the BaseContainer path because the `SANDBOX_CAP_FS_DENY` capability is absent
there — it only takes effect via ProcessContainer or AppContainer.

A second limitation is worth knowing before designing around it:
`network.allowedHosts` / `network.blockedHosts` are **not implemented on
Windows at all**; the binary errors out and directs you to
`network.defaultPolicy` or a proxy. Per-domain network allowlisting is
Linux-only.

### The helper is the interesting artifact

`codex-windows-sandbox-setup.exe` (17 MB) is the only binary in the install
that holds three capabilities in one import table:

```
netapi32   NetUserAdd, NetLocalGroupAdd, NetLocalGroupAddMembers
fwpuclnt   FwpmEngineOpen0, FwpmFilterAdd0, FwpmSubLayerAdd0,
           FwpmTransactionBegin0, FwpmTransactionCommit0
secur32    AcquireCredentialsHandle, InitializeSecurityContext,
           EncryptMessage, DecryptMessage
```

Its error enum names the sequence outright:

```
orchestrator_elevation_required
helper_dpapi_protect_failed
helper_capability_sid_failed
helper_firewall_rule_create_or_add_failed
helper_users_group_create_failed
```

So the elevated sandbox path **creates a dedicated local user and group,
protects credentials with DPAPI, and installs WFP firewall rules**, with a
full SSPI/Negotiate handshake and certificate-store manipulation on top. The
sandbox runs as a persistent Windows service. Config side:
`[windows] sandbox = "elevated"`, hidden flags `--run-as-windows-sandbox` /
`--codex-run-as-f-sandbox`, and `CODEX_WINDOWS_REGISTERED_CORE`.

Stating this is an observation about the design. Nothing here is a
reconstruction path, and the case study deliberately stops at "the import
table and error enum say this" — it does not enumerate how to drive the helper.

`codex-command-runner.exe` (7.8 MB, GUI subsystem, no exports) is the other
half: `CreateRestrictedToken` + `CreateProcessAsUserW` + `SetEntriesInAclW` +
`CreateJobObjectW`, i.e. the actual restricted-token launcher.

`codex-code-mode-host.exe` (71 MB) has only **13 first-party source files**
against the main binary's 456, and links `tonic` 0.14.3 + `h2` + `hyper-util`.
Its first-party set includes `cell_actor/`, `route_aware_client_pool/` and
`custom_ca.rs`, and it imports `accept`/`bind`. The strong inference is a
**remote execution-cell gateway over gRPC with configurable private CA** — a
tool call is forwarded to a sandboxed cell whose identity is verified by
certificate. No protocol documentation was recovered, so this stays an
inference.

## The auto-reviewer exists, and its design is legible

`approvals_reviewer = "auto_review"` routes approval requests through an
automated reviewer implemented in `src/guardian/` plus
`guardian_assessment.rs`. The binary embeds the reviewer's **full system
prompt**. Its dimensions are public by design: risk tier
(low/medium/high/critical) × user-authorization score
(high/medium/low/unknown), with data exfiltration, credential probing and
persistent security weakening singled out.

The architecturally important part is the **evidence grading**. Only user and
developer messages, `AGENTS.md`, and `request_user_input` responses count as
trusted content. Tool output, skill descriptions and the assistant's own
messages are untrusted evidence. That is the structural defense against
prompt injection: **a tool result or a skill file cannot self-authorize**, no
matter what it claims. The reviewer itself runs read-only and without network
access, and cannot grant `sandbox_permissions`.

The v2 configuration shows the reviewer moving from synchronous transcript
review to an **asynchronous incremental classifier**:

```
async_classifier_mode              review_threshold_basis_points
max_tool_call_lag                  classifier_instructions
tools sources: cyber / description / parameters /
                indirect_description_prefixes
modalities: multi_agent / code_mode / mcp_resources
reuse_parent_compaction
```

`indirect_description_prefixes` means tool-description prefixes are inspected
— a defense against moving a payload into a description. `cyber` is a separate
classification dimension. This is an inference from field names and event
structure; runtime behavior was not observed.

Granular approval is per-category (`sandbox_approval`, `skill_approval`,
`request_permissions`, `mcp_elicitations`), where a category set to `false` is
auto-rejected rather than prompted. Above all of this sits a 43-field
`ConfigRequirementsToml` — the deployment-side allowlist covering
`allowed_sandbox_modes`, `allowed_approvals_reviewers`,
`allow_managed_hooks_only` and `enforce_residency`, none of which a user can
override.

## Practical outcome for an external AI

The useful path is cheap and complete:

1. **Full conversation history, losslessly.** Read
   `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. Every event carries a `type`
   field — `agent_message`, `exec_command_*`, `mcp_tool_call_*`,
   `patch_apply_*`, `token_count`, `context_compacted`, `guardian_assessment`,
   `hook_*`, `collab_*`. The first line's `base_instructions` even contains the
   system prompt.
2. **Metadata cheaply.**
   `sqlite3 "file:$HOME/.codex/state_5.sqlite?mode=ro&immutable=1"`.
   `immutable=1` guarantees no WAL write, no migration, no lock.
3. **Multi-agent trees.**
   `thread_spawn_edges(parent_thread_id, child_thread_id, status)` is an
   explicit derivation graph, not something to be inferred.

Anti-patterns, all learned the expensive way:

- **Do not grep the whole sessions tree.** It is 746 MB. Filter by date or
  filename first, or use `rollout_byte_offset` to seek.
- **Do not full-scan `thread_history_1.sqlite` or `logs_2.sqlite`** (78 MB /
  73 MB). Use `LIMIT` and an indexed column.
- **Do not print `config.toml` raw.** It carries `notify` paths,
  `[mcp_servers.*].env` and `shell_environment_policy.set` values. Redact
  `token` / `secret` / `api_key` / `password` / `RefreshToken` / `user_id` /
  `device_id` on read, and never echo a value back.
- **Do not assume `hooks.json` and `config.toml [hooks]` are one system.**
  They coexist; the merge order was not traced. `hooks.json` holds
  Claude-Code-shaped entries whose commands are Base64-wrapped PowerShell —
  convenient for escaping, but Base64 is not encryption and those hooks are
  hard to audit.

The `trusted_hash = "sha256:..."` map under `[hooks.state]`, keyed by
`path:event:index`, is the anti-tamper mechanism: change a hook script's
contents and the hash stops matching.

## Open items

Recorded rather than guessed:

1. Whether `hooks.json` and `config.toml [hooks]` merge, and in what order.
2. `guardian_policy_config`'s full schema — key names were seen, defaults and
   value ranges were not.
3. What actually drives `defer_loading` per MCP server.
4. `useStateDbOnly` on thread creation: whether a mode exists that writes no
   JSONL at all, which would change the "JSONL is always truth" claim.
5. `daybreak_enabled` and `guardianslug` semantics.
6. The `code-mode` gRPC contract and what `custom_ca.rs` is for.
7. The contents of the 11.5 MB high-entropy `.pdata` region.

## Reproducing

The full 702-line report lives in the author's analysis directory
(`rea-codex-work/CODEX-DESKTOP-ANALYSIS.md`) together with the generalized
`rsrc.py` path extractor, the reused `pe.py` / `str.py`, and the SQLite schema
dumper. The 746 MB JSONL tree, the 78 MB history database and the 73 MB log
database are **not** committed — they contain conversation content.

## Evidence discipline

Graded as follows. Direct file observations: PE headers, the 151 exports,
import tables and counts, panic-path strings, serde field names, the SQLite
schemas and row counts, and the embedded reviewer prompt. Strong inferences:
that `code-mode-host` is a remote cell gateway, and that guardian v2 is an
async incremental classifier. Weak inference: that `noise_relay/` refers to
the Noise protocol — only the directory name was seen, no protocol constants.
Unverified: all runtime behavior, and the `hooks.json` merge order.

The PE route also carries the usual caveat: **absence from the export table is
not proof of absence.** Statically linked and dynamically loaded code both
hide from it — which is exactly why only bash and powershell tree-sitter
grammars appear here.
