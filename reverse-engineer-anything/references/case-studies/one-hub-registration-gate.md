# Case study: locating the real enforcement point in a web SPA

A worked example of assessing a third-party LLM API relay running **one-hub
v1.22.30** (React SPA + Go backend), where the driving question was not "what
does this code do" but **"is this disabled feature actually disabled, or just
hidden in the frontend?"** — the authorization-gate question.

Written under written authorization for security assessment. Target host,
operator identity, pricing, and account identifiers are redacted; the
methodology and the code shapes are not.

## Why this case is worth reading

Four findings generalize past this product:

1. **A whole-bundle `rg` can fail while returning megabytes of noise.** One
   search for a six-character Chinese literal produced 77,000 tokens of
   locale scaffolding and **truncated before the answer**. Component-chunk
   scoping is not an optimization, it is the difference between an answer and
   a truncated stream.
2. **Silence in a capture is not absence in the codebase.** The component
   imported a hook file that was missing from the local capture entirely. A
   negative result from an incomplete capture is worth nothing.
3. **A pass-through error slot is the tell.** When a form renders
   `errors.submit` that it received from the API, the client holds no policy
   at all — you can reach that conclusion without finding any banner string.
4. **The control and its envelope are different findings.** A correct
   server-side gate returned `HTTP 200` with `success:false`, which silently
   defeats every status-code-based detection rule.

## Route and outcome

| Step | Tool | Outcome |
| --- | --- | --- |
| Bundle inventory | REA JS analysis, 37 merged chunks | 574,692 AST nodes; architecture + channel-type matrix recovered |
| Network records | retained capture review | 84 records; public read-only endpoints enumerated |
| Public config | unauthenticated `GET /api/status` | version + feature-flag inventory, no auth |
| Price model | `GET /api/prices` | 105 models; operator-set ratios recovered |
| Gate location | chunk-scoped search + full-file read | enforcement point found to be **server-side** |
| Gate verification | one `POST` the page itself issues | refusal confirmed at runtime |

Only unauthenticated reads plus a single register-form submission were issued.
No enumeration, no concurrency, no credential use, no database access.

## Bundled-locale files will swallow your search

The naive move is to grep the whole extracted bundle for the exact string the
user sees. Here that was `管理员关闭了新用户注册`. The result was dominated by
embedded locale tables — one file exceeded 500 KB and contained deeply nested
`__i18n_ally_root__` structures from an i18n extraction tool, plus a full
channel-type prompt matrix. The real match never surfaced before truncation.

Fix: resolve the chunk chain from the route first, then search inside it.

```
/register  ->  Register-<hash>.js  ->  useRegister-<hash>.js
```

The route component was **8.6 KB**. At that size, stop searching and read the
whole file — it is faster and more reliable than any pattern.

## Confirm the capture is complete before trusting a negative

The component imported `useRegister-<hash>.js`. That file **was not in the
local capture**. Had the search for the banner string come back empty from the
component alone, the tempting conclusion would have been "the message is
built dynamically" or "there is no client-side check at all."

Both would have been unsupported. When a bundle grep is silent, first ask
whether the referenced chunk exists locally at all. **Incomplete captures
manufacture false negatives**, and a false negative here is exactly the kind
that gets written into a report as a confident architectural claim.

## The pass-through shape

The register component contains no branch for a closed-registration state.
Its submit handler is:

```js
const { success, message } = await register(values, turnstileToken)
success
  ? setStatus({ success: true })
  : setErrors({ submit: message })
```

rendered as:

```js
errors.submit && <HelperText error>{errors.submit}</HelperText>
```

The component generates no policy language and holds no closed-state variable.
It forwards whatever the API said. Contrast with a genuine client-side gate,
which reads a policy value and blocks locally:

```js
useEffect(() => setNeedsInvite(Boolean(siteInfo.invite_code_register)), [siteInfo])
return needsInvite && <Field name="invite_code" />
```

Distinguishing these two shapes is often faster and more reliable than
hunting for the banner string.

## Feature flags are not alternative paths

`/api/status` was unauthenticated and returned the full flag set. Recording
their values mattered, but reading a flag's *name* is not reading its *effect*.

The relevant entry was `invite_code_register: false`. The tempting report line
would have been "registration is closed, but an invite code may work." It would
have been wrong: with the flag false, an invite code is rejected exactly like
an open registration. **Enumerate what each flag unlocks before offering it as
a workaround.**

The same endpoint also showed `turnstile_check: false` — inert while the gate
is shut, but a scripting surface the moment the operator reopens registration.
Flag state is only interpretable against the current gate position.

## One probe, wrapped

The single request the page itself would issue converts inference into
observation:

```powershell
try {
  $r = Invoke-WebRequest -Uri "<api>/user/register" -Method POST `
        -ContentType "application/json" -Body $body -TimeoutSec 25 -ErrorAction Stop
  "HTTP $($r.StatusCode)"; $r.Content
} catch {
  $resp = $_.Exception.Response
  "HTTP $([int]$resp.StatusCode)"
  (New-Object System.IO.StreamReader($resp.GetResponseStream())).ReadToEnd()
}
```

The `try/catch` is not defensive style. A refused request throws, and an
unwrapped `Invoke-WebRequest` discards the response body — which here was the
entire payload of the observation.

Use a deterministic probe identity (`sec_probe_<date>`) so any account the
probe creates is greppable in the target's data and attributable. Disclose it.

## The control, and the envelope

```
HTTP 200
{"message":"<registration closed>","success":false}
```

**The gate is server-side and correctly implemented.** That is a positive
result: there is no client-side bypass, and the assessment should say so
plainly rather than manufacturing a finding.

**The envelope is a separate finding.** A refused operation answering `200`
means WAF, SIEM, and proxy-log rules keyed on status code see nothing. Bulk
registration attempts are invisible at that layer. Harmless to the frontend,
real for detection — and it matters most in the window where an operator
reopens the gate. Report it with that condition attached.

## The authorization boundary

Testing authorization is not authorization to defeat it. The deliverable for a
gate is the **enforcement point**, not a way past it:

- which layer decides, with the evidence for that claim
- who can change the decision — the operator, via which setting
- whether the alternative paths are actually open
- what the response envelope reveals

The correct output was a concrete unblock request to the operator (reopen the
flag, or provision the test account), plus a note that reopening registration
without enabling turnstile silently changes the assessment's subject.

Handing over a bypass method for a control you were asked to evaluate is the
one deliverable that should never ship, regardless of the authorization
claimed.

## Open items

Recorded rather than guessed:

1. Whether any endpoint besides `/register` reveals policy state to an
   unauthenticated caller beyond what `/api/status` already exposes.
2. Server-side handling of inputs other than the single probe — notably
   username collisions and password-policy edge cases.
3. Whether sibling deployments of the same software version share the gate
   configuration.
4. What the operator's own fleet-wide detection does with the `200` envelope.

## Reproducing

Extract the shipped bundle, resolve the route's chunk chain from the router
table, read the route component in full, then issue one registration request.
The full report, the 105-model price table, and the raw network records are in
the author's local knowledge base and are **not committed** — they carry
operator pricing and target identifiers.

## Evidence discipline

Graded as in every case study here:

- **Evidenced** — the `POST` status and envelope; the absence of any
  closed-state branch in a named, fully-read 8.6 KB component chunk; the
  feature-flag values returned by `/api/status`
- **Inferred** — that the client holds no policy, from the pass-through shape
  of the submit handler
- **Unknown** — chunks absent from the local capture; server behavior for
  inputs other than the single probe; operator-side detection behavior

Absence of a banner string in a captured chunk is not proof the gate is
server-side. The runtime probe is what carried that claim, and it is the only
step in this case that converted an architectural inference into an
observation.
