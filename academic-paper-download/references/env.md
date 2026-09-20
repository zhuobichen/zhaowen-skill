# Environment Configuration

Use Python 3.10 or newer. `pyproject.toml` declares the tested embedding range
`pypdf>=6.14,<7`; `requirements.lock` pins the CLI and smoke-test runtime to the
reviewed `pypdf==6.14.2` wheel and SHA-256.

Resolve the installed skill directory to an absolute path, then explicitly
bootstrap and validate the locked runtime:

```bash
SKILL_DIR='/absolute/path/to/academic-paper-download'
python3 "$SKILL_DIR/scripts/runtime.py" bootstrap --locked --json
python3 "$SKILL_DIR/scripts/runtime.py" smoke --offline --json
```

`npx skills add` installs or links skill files only. It does not install Python
packages or run post-install hooks. `bootstrap` is therefore an explicit,
reviewable setup step. It creates a Python-version-, platform-, and lock-bound
environment outside the skill directory:

- `ACADEMIC_PAPER_DOWNLOAD_CACHE_DIR` when explicitly set;
- otherwise the platform cache root under
  `tiangong-skills/academic-paper-download/`.

Normal `fetch`, `browser-finalize`, `notify-human`, `doctor`, and `smoke`
commands never install packages. They fail with `runtime_missing` or
`runtime_invalid` before network retrieval when the locked runtime is absent or
does not pass its exact-version import preflight.

Use `doctor --json` for a read-only runtime check. Use `smoke --offline --json`
for the acceptance test: it disables socket creation, generates a temporary
one-page PDF, parses it through the production validator, verifies SHA-256 and
size, writes nothing to the installed skill, and performs no network access.

When embedding `paper_fetch` in an existing application, manage that
application's environment normally against the compatible range from
`pyproject.toml`. The exact lock is the supported CLI/test environment, not a
requirement that an embedding host downgrade an otherwise compatible pypdf 6.x
installation.

For the optional CloakBrowser handoff, create a separate isolated environment
and install both locks:

```bash
CLOAK_VENV='/absolute/path/to/isolated-cloakbrowser-venv'
python3 -m venv "$CLOAK_VENV"
CLOAK_PYTHON="$CLOAK_VENV/bin/python"
"$CLOAK_PYTHON" -m pip install \
  -r "$SKILL_DIR/requirements.lock" \
  -r "$SKILL_DIR/requirements-cloakbrowser.txt"
```

On Windows, set `CLOAK_PYTHON` to the environment's `Scripts/python.exe`.

The optional lock pins `cloakbrowser==0.4.12`, Playwright, and all transitive
Python dependencies. Keep this environment separate from the core locked CLI
runtime. Ordinary OA downloads require only the core runtime.

| Variable | Default | Purpose |
| --- | --- | --- |
| `UNPAYWALL_EMAIL` | unset | Enable Unpaywall with its required contact email. |
| `SEMANTIC_SCHOLAR_API_KEY` | unset | Optional Semantic Scholar `x-api-key`. |

The CloakBrowser executor passes an exact browser version and forces
`CLOAKBROWSER_AUTO_UPDATE=false` while running. It rejects
`CLOAKBROWSER_BINARY_PATH`, `CLOAKBROWSER_DOWNLOAD_URL`, and
`CLOAKBROWSER_SKIP_CHECKSUM=true` because those settings would weaken the
recorded binary provenance or official signature/checksum path. Never print or
record `CLOAKBROWSER_LICENSE_KEY`; the reproducible free-binary executor does
not request or use it and masks it from the child browser process.

The automatic source order is Unpaywall, Semantic Scholar open-access PDF,
arXiv, then browser handoff. URLs, errors, manifests, and events redact contact
email and sensitive query/header values.

Do not store or request API keys, usernames, passwords, cookies, institutional
proxy credentials, or session tokens in skill resources or chat. Publisher
authentication stays in the explicitly selected browser session; see
[browser-handoff.md](browser-handoff.md).
