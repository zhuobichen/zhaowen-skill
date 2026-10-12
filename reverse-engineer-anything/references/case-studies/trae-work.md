# Case study: TRAE Work CN memory and index internals

A worked example of reverse engineering a large Electron application with
native Rust and Go modules on a memory-constrained Windows host, where REA's
semantic layer could not run and the decompiler providers were absent.

Target: `TRAE SOLO CN` 0.1.63 (VSCode fork, baseline 1.107.1), Windows, packaged
as a fully expanded Electron directory tree with **no `app.asar`**.

Question: where does the agent keep its memory, how is code indexed, and can an
external AI reuse that index for fast retrieval?

## Why this case is worth reading

Three findings generalize beyond this product:

1. A Rust binary's panic and log strings leak a **source map** — file paths with
   line numbers — which recovers the module layout without any decompilation.
2. PE **export tables** carry hard evidence when no decompiler is installed.
   Import counts and Go buildinfo identify language runtime and vendored
   dependency versions.
3. The JS analyzer's `coverage.status = partial` is a **heap-bound** limit, not an
   input-size limit, and is often fixable with an explicit flag.

## Route and outcome

| Step | Tool | Outcome |
| --- | --- | --- |
| Artifact identity | `rea inspect-artifact` | sha256 + `evidence_id` + `format: pe` |
| JS structure | `rea analyze-javascript-application` | exit 0 after `--max-heap-mb`; 728,496 AST nodes |
| JS semantics | same, semantic pass | `partial` — worker heap exhausted, left unresolved |
| ELF layout | `rea inspect-binary-layout` | `unsupported_provider` (pwntools is Linux x64 only) |
| Native decompile | `rea analyze` | `provider_unavailable` — no Ghidra, no IDA, no JDK |
| Native fallback | `pefile` + ASCII string regex | export/import tables, Go buildinfo, Rust paths |

No step was abandoned silently: each unsupported or partial result was recorded
with its reason and paired with a supported substitute, and the substitute's
evidence grade was stated separately from REA graph output.

## Fixing the "OOM" that was a heap default

The first pass analyzed the full staging tree (3155 files), the node process grew
to 2.5 GB and exited non-zero with a zero-byte artifact. Narrowing to 3 files
failed identically — which is the clue that the input was never the problem.

```powershell
Get-CimInstance Win32_ComputerSystem |
  Select-Object @{n='TotalGB';e={[math]::Round($_.TotalPhysicalMemory/1GB,1)}}
[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1)
# -> 15.9 GB total, 1.6 GB free
```

The analyzer documents `--max-heap-mb` (default **1024**) for its isolated worker.
A 2.84 MB minified `main.js` exceeds 1 GB of old-space. Both knobs are required:

```powershell
$env:NODE_OPTIONS="--max-old-space-size=1400"   # the CLI's own main process
npx -y rea-agents@latest analyze-javascript-application <dir> `
  --max-heap-mb 1400 --analysis-timeout-ms 300000 --format json
```

Setting only `--max-heap-mb` leaves the CLI process itself at the default cap.

| Input | Exit | Graph | AST nodes | Findings |
| --- | --- | --- | --- | --- |
| `bootstrap-fork.js` + `cli.js` (268 KB) | 0 | 179 KB | 62,737 | 48 |
| `main.js` (2.84 MB) | 0 | 1.55 MB | 728,496 | 574 |

Residual limit: the structural graph completes; the `semantic_graph` pass still
exhausts the worker heap at 1.4 GB. Closing large resident applications and
raising `--max-heap-mb` to 3000+ is the known remedy — it was not applied because
terminating the user's other applications was outside the authorized scope.

## Native evidence without a decompiler

`inspect-binary-layout` is Linux-x64-only and `analyze` needs Ghidra or IDA. The
host had neither, and no JDK to install Ghidra. `pefile` recovers the same class
of facts from the file itself:

- **Language runtime** — `libckg.dll` is Go: the `Go buildinfo` blob enumerates
  79 vendored modules with versions, including `go-git/v5 v5.19.1`.
- **Linked toolchains** — `toolhost.dll` exports 936 `git_*` symbols, i.e. it
  **statically links libgit2 1.8.1** and does not shell out to `git.exe`.
- **Embedded interpreters** — `harness.dll` exports `v8_inspector_*` alongside
  `rusty_v8` markers: an in-process V8 with a CDP endpoint.
- **Parsers** — `ai_agent.dll` links tree-sitter 0.25.8 for 14 languages, so code
  retrieval is AST-based rather than regex-based.
- **Networking** — `sscronet.dll` exports 1125 `Cronet_*` symbols. Model traffic
  uses a private Chromium Cronet stack, so packet capture must target this
  library rather than Electron's own networking.
- **Version skew** — `ai_agent.dll` embeds `aws_lc_0_32_3_*` while `harness.dll`
  and `toolhost.dll` embed `aws_lc_0_41_0_*`. **Co-packaged does not imply
  co-versioned**; treat each module's provenance separately.

## Rust panic strings as a source map

Panic and log messages embed `\` + source path + `:line`, e.g.

```
event apps\icube_server_rs\modules\ai-agent\src\domain\plan\simple_service_v2.rs:14827
```

A regex over the `.rdata` section yielded **948 unique paths**, enough to
reconstruct the workspace: `domain/toolcall` (176 files) as the largest module,
`migration_version` (79), `infrastructure/adapter` (52), `context_resolver` (27),
`memory` (15). This replaced guesswork about the agent's architecture with a
file-counted module inventory, and it cost one regex pass.

```python
re.compile(rb"[A-Za-z0-9_\\/-]+\.rs:\d+")
```

## What the mechanism turned out to be

The product keeps a **dual-track** store, which is the reusable design idea:

- **Track A — human-readable memory.** `~/.trae-cn/memory/` holds
  `user_profile.md`, `project_memory.md`, and dated
  `session_memory_*.jsonl` / `topics.md`. Plain Markdown and JSONL: directly
  readable by an external agent with no decryption.
- **Track B — encrypted vector index.** `libckg.dll` (Go + CGO + PyO3) loads the
  `sqlite_vec` extension into `%APPDATA%\TRAE SOLO CN\ModularData\`, creating a
  `vec_items_v2` virtual table. Embeddings are produced locally by
  `codekg_bge_m3` (BGE-M3), and the server-supplied feature gate sets
  `force_local_embedding: true`. The database is **SQLCipher (AES-256)** and
  cannot be read without the key.

Retrieval is not one vector search. Three paths run in parallel — tree-sitter
AST, `sqlite_vec` vectors, and FTS5 full-text (`global_search/fts_backfill.rs`)
— aggregated by ~18 dedicated resolvers under `context_resolver`
(`code/`, `artifact/`, `docset/`, `file_diff/`, `lint_error/`, `log/`,
`user_content/`, …).

Memory is a **cache with eviction**, not an append-only log. `domain/memory/
core_memory/strategy/` holds six policies — LRU, LFU, linear decay, exponential
decay, hybrid half-life, and Window-TinyLFU — backed by a `core_memory` table
created in `m20251023_000001_create_core_memory_table.rs`. The presence of
Window-TinyLFU indicates explicit handling of scan pollution, where a burst of
new entries evicts the hot set. Six strategy files do **not** prove six
concurrent policies; the selection logic lives in `core_memory/service.rs` and
was not recovered.

The Rust side calls CKG over gRPC with 22 methods. One log line is worth
remembering as a version-compatibility pattern:

```
[CKGService] retrieve code chunk method not found, use fallback
```

The agent capability-probes the server and degrades when a method is absent,
which is why the CKG DLL can be upgraded independently of the agent.

## Practical outcome for an external AI

The cheapest usable path is Track A. Read `~/.trae-cn/memory/` directly for
user profile, project context, and session history; it needs no key and no
service. Track B is not worth attacking — the SQLCipher key is unknown, so a
parallel index over the same tree is the practical substitute for vector search.

Anti-patterns: do not shell out to `git` expecting `toolhost.dll` to use it, do
not assume the packaged DLLs share one dependency version, and do not point
capture tooling at Electron networking when the model traffic goes through
`sscronet.dll`.

## Open items

Recorded rather than guessed:

1. Timeout threshold behind `[CKG] Failed to acquire read lock within …`.
2. The concrete fallback path taken when `RetrieveCodeChunk` is missing.
3. Whether `core_memory` DDL or `~/.trae-cn/memory/*.md` is the source of truth
   for memory — answerable by reading the local SQLCipher database directly.
4. Window size `W` for `w_tinylfu`, and how the six strategies are selected.
5. Whether `sscronet.dll` enables QUIC or certificate pinning.

## Reproducing

The full 1247-line report, the `pefile` extraction script, the Rust-path regex,
and the export-table dump are in the author's knowledge base
(`ZhaoWen_KnowledgeBase/AI项目生成文档_AI对话沉淀/TRAEWork记忆与索引机制逆向分析.md`).
MB-scale graph artifacts are not committed; regenerate them with the commands
above.

## Evidence discipline

Conclusions here are graded: PE headers, export tables, and string literals are
direct file observations; module structure inferred from path counts is a strong
inference; runtime behavior is unverified because no execution evidence was
collected. Absence of a symbol in an export table is not proof a capability is
missing — statically linked and `dlopen`-ed code can both hide from it.
