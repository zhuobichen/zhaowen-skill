# Case study: a flag that is stored, shipped, and never read

A worked example of assessing a **SMAT-Cloud CE v1.3.0** atmospheric-analysis
platform (Vue 3 SPA + Vite/rolldown + Element Plus + axios + Pinia, ASP.NET
backend) under written authorization for security assessment. The target host,
operator identity, product branding, and the server address are redacted; the
methodology and the code shapes are not.

The driving question was the standard authorization question — *what does this
client actually enforce?* — and the answer turned out to be a single boolean
that the server sends, the store persists, and **no code ever reads**.

## Why this case is worth reading

Four findings generalize past this product:

1. **A persisted field is not an enforced control.** The login response carries
   `requirePasswordChange`. The Pinia store saves it to `localStorage` and
   rehydrates it on boot. Nothing else in the bundle ever mentions it. A reader
   skimming the store would reasonably conclude "forced password change is
   implemented." It is not implemented anywhere in this frontend.
2. **Route `meta` is an authorization surface.** Eleven business routes carried
   `meta:{requiresAuth:true}` and **zero** carried a role, scope, or permission
   field — including a route that renders a user-administration screen. The
   global guard reads exactly one key.
3. **`btoa` on a password is a plain-text password with extra steps.** The
   login action base64-encodes the password before POSTing it. It survives TLS,
   it does not survive a request log, a proxy body capture, or devtools.
4. **A changelog is a prioritized hint list.** The bundled release notes named a
   specific authorization fix ("user-level task name isolation"). That is the
   one place in a minified bundle that tells you *where the history hurt*.

## Route and outcome

| Step | Tool | Outcome |
| --- | --- | --- |
| Shell inventory | one `GET /` of the SPA entry | 14 assets named in `modulepreload` |
| Lazy-chunk enumeration | regex over the entry chunk | 68 referenced chunks recovered by filename |
| Bulk retrieval | 32 `GET`s for the analysis chunks | 1.08 MB of JS; no runtime traffic, no API calls |
| Endpoint recovery | regex for the axios call sites | 28 endpoints across 5 resources |
| Auth-flow reconstruction | targeted context reads | JWT bearer, refresh rotation, `localStorage` persistence |
| Guard audit | route table + `beforeEach` + store field census | one boolean unenforced; no role model in the client |

Passive retrieval only: public static assets. No authenticated request, no
enumeration, no concurrency, no credential use, no database access, and no
attempt to reach any endpoint named in the findings below.

## Start from the shell, not from a search

The entry HTML is 1.5 KB and names every eagerly-loaded asset:

```html
<title>SMAT-Cloud</title>
<script type="module" crossorigin src="/<base>/assets/index-<hash>.js"></script>
<link rel="modulepreload" href="/<base>/assets/rolldown-runtime-<hash>.js">
```

The `modulepreload` list is the eager set only. The real surface is one level
down: the entry chunk contains a `__vite__mapDeps` table and roughly thirty
`import("./Chunk-<hash>.js")` calls. Enumerating those filenames with a single
regex and fetching them is the whole collection step.

```powershell
[regex]::Matches($entry, 'assets/[A-Za-z0-9_\-]+\.js') |
    ForEach-Object { $_.Value } | Sort-Object -Unique
```

Chunk filenames here are **semantic** — `UserManager-<hash>.js`,
`TaskSubmissionDialog-<hash>.js`, `AnnualPM25Analysis-<hash>.js`. That is a
rolldown/Vite default, and it is worth stating plainly because it hands you the
application map before you parse a single statement. Read the filenames as the
route table.

## The endpoint surface

API base is `<base>/api/`, supplied to a single axios instance. Every business
call concatenates onto it, so endpoints are only recoverable as *call-site
strings*, not as declared constants — the base never appears next to them.

Recovering them is one regex over the concatenated bundle:

```powershell
[regex]::Matches($blob, '\.\s*(get|post|put|delete|patch)\(\s*["''`]([^"''`]{2,90})["''`]')
```

| Resource | Endpoints |
| --- | --- |
| `/Account` | `POST Login`, `POST Register`, `POST RefreshToken`, `DELETE Logout`, `POST ForgotPassword`, `POST SendRegisterCaptcha?email=`, `POST SendForgotPasswordCaptcha?email=` |
| `/Users` | `GET`, `POST`, `PUT /{id}`, `DELETE /{id}`, `DELETE` (bulk) |
| `/Projects` | `GET`, `POST`, `DELETE /{id}` |
| `/Tasks` | `GET`, `POST`, `DELETE /{id}`, `GET /Log/{id}` |
| `/Files` | `GET Upload`, `POST Upload`, `DELETE Upload/{id}`, `GET Result/{a}/{b}`, `GET SampleData`, `GET Result/` |

Five resources, twenty-eight endpoints, one base path. Note the shape of the
authorization surface before any of it is tested: **every resource is a flat
collection keyed by a client-supplied identifier**, with no version, tenant, or
workspace segment anywhere in the path. Every one of these is an IDOR candidate
by construction; none was probed.

## Authentication, reconstructed

An axios request interceptor attaches the bearer token, with an explicit
opt-out flag:

```js
$l.interceptors.request.use(async e => {
  let t = e.requiresAuth !== false;
  delete e.requiresAuth;
  if (t) {
    let t = await yu().getToken();
    if (t) e.headers.Authorization = `Bearer ${t}`;
  }
  return e;
})
```

Two details are worth more than the pattern they implement:

- **The opt-out is a property on the request config, not a URL allowlist.**
  Adding `requiresAuth:false` to a call is how the unauthenticated endpoints
  (`Login`, `Register`, `RefreshToken`, the two captcha sends) are marked. The
  mechanism is sound, and a future endpoint that forgets the flag fails closed
  — that direction is correct.
- **Authentication is header-based, so there is no CSRF surface here.** Cookie
  helpers ship in the bundle (axios `withCredentials`, `xsrfCookieName`) but the
  auth token never rides a cookie. Do not spend report space on CSRF.

Refresh is a **single-flight with a generation counter**, and it is written
correctly:

```js
if (!this._u) {                       // _u = in-flight promise
  let e = this._gen, t = this.refreshToken;
  let n = decodeExpiry(t).then(n => {
    if (this._gen !== e || this.refreshToken !== t)
      throw Error(`Authentication session changed during token refresh`);
    return this.saveToken(n), this.accessToken;
  })
}
```

The generation counter is incremented by `saveToken` **and** `clearCredentials`,
and the resolved refresh is discarded if either moved underneath it. That is the
correct handling of the logout-during-refresh race, and it is rarer than it
should be. Call it out as a positive finding.

Expiry is evaluated **client-side** (`decodeExpiry` parses the token's expiry
claim), and the refresh token is sent to `POST /Account/RefreshToken` to obtain
a new pair. That is a refresh-token rotation shape. Whether rotation is
actually enforced — old token revoked on use, reuse detected — is a runtime
question this static pass cannot answer, and the report says so.

## Finding 1 — the enforced-flag that enforces nothing

The login response type and the store both carry a boolean:

```js
{ userId, userName, displayName, phoneNumber, email,
  accessToken, refreshToken, accessTokenExpiresAt, refreshTokenExpiresAt,
  requirePasswordChange }
```

```js
saveToken(e) {
  ...
  this.requirePasswordChange = e.requirePasswordChange;
  localStorage.setItem('user-info', JSON.stringify(pick(e)));
}
```

Now count the occurrences of that identifier across all thirty-two business
chunks plus the entry:

```
index-<hash>.js  x5
```

All five are the store: the field list, the persisted-state slice, the action
assignment, the `saveToken` copy, and the localStorage write. **Zero**
occurrences in any component, any route definition, any guard, any template.

The entire authorization model of the application is one global guard:

```js
router.beforeEach(async (to, from) => {
  if (to.meta.requiresAuth) {
    let n = false;
    try { n = await store.isLoggedIn(); } catch { n = false; }
    if (!n) return { name: 'Login', query: { redirect: to.fullPath } };
  }
})
```

One key: `requiresAuth`. One predicate: *is there a usable token.*

**Consequence.** A user whose credential an administrator force-reset — the
exact population `requirePasswordChange` exists to constrain — receives
`true`, stores it, and then browses every feature in the application with no
password change, because no code path reads the flag. If the backend also
ignores it, the control does not exist; if the backend rejects the API calls,
the user gets an opaque failure loop with no client-side explanation.

This is the shape the `ui-gates-and-server-enforcement` reference describes,
and it is the mirror image of the one-hub case: there, a refusal banner was
**client-only**; here, a real server-issued policy flag is **client-unused**.
Both reduce to the same question — *where is the decision actually made* — and
both are answered by locating the enforcement point, not by finding the string.

## Finding 2 — a user-administration route with no role check

The route table carries `meta` on eleven business routes. Every one is the same
object:

```js
meta: { requiresAuth: true }
```

There is no `role`, no `scope`, no `permission`, no `admin` key on any route,
including:

```js
{ path: 'user-manager', name: 'UserManager',
  component: () => import('./UserManager-<hash>.js'), ... }
```

And the bundle contains **no occurrence of `isAdmin`, `is_admin`, or the string
`admin` in any casing**, across all thirty-three chunks.

Combined with Finding 1, the client carries **no authorization model at all** —
only authentication. Every role decision, if one exists, is server-side.

State it precisely, because the strong version of this claim is not supportable
from static evidence: *the SPA gates on identity and nothing else.* Whether
`GET /Users` rejects a non-admin bearer token is exactly the kind of question
that needs one authorized request to answer, and it was not asked here. What
static analysis establishes is the correct precondition for the test — if the
server does enforce it, the client is merely redundant; if it does not, this is
a full user-management takeover.

Note also that `DELETE /Users` takes **no identifier**. A bulk-delete endpoint
whose authorization cannot be distinguished from `DELETE /Users/{id}` in the
client is worth a row in the report on its own.

## Finding 3 — `btoa` is not password protection

```js
async login(e, t) {
  t = btoa(t);
  let n = await api.post('/Account/Login',
                { loginName: e, password: t },
                { requiresAuth: false });
  this.saveToken(n);
}
```

The password is base64-encoded, then sent as the `password` field. This is
**encoding, not protection**: the server must base64-decode it to obtain the
actual credential, so the plaintext password exists on the wire inside the TLS
tunnel and is trivially recovered from any request-body capture, reverse proxy
log, or Copy-as-cURL. Anyone reading the bundle can confirm the scheme in five
seconds.

The severity is **low**, and the report should say so plainly: over TLS this
adds no attacker capability. It is listed because it is a false control — it
reads like password handling and provides none — and because a reader who
audits by grepping for `password` will otherwise mark this endpoint as clean.

The correct fix is server-side password hashing plus simply relying on TLS.
There is no client-side fix, and saying "hash the password in the browser" would
be wrong.

## Finding 4 — both tokens in `localStorage`

```js
localStorage.setItem('user-info', JSON.stringify({
  userId, userName, displayName, phoneNumber, email,
  accessToken, refreshToken, accessTokenExpiresAt, refreshTokenExpiresAt,
  requirePasswordChange
}));
```

The **refresh token** — the long-lived, high-value credential — is stored in
plaintext `localStorage` under a fixed, guessable key, alongside the access
token and the full user profile.

The exposure model is the standard one: any XSS on the origin, or any injected
third-party script, reads `localStorage['user-info']` once and walks away with a
session that survives page reload. Because the refresh token is included, one
read yields a *renewable* session rather than one that dies at access-token
expiry.

Also note the key is `user-info`, not something namespaced to the app — it
collides by construction with any other SPA on the same origin, and this
platform already serves multiple SPAs.

Severity **medium**, conditional on an XSS existing. The honest framing is that
this finding is *amplification*: it determines what an XSS costs. The primary
vulnerability is whatever produces script execution; this sets the blast radius
to "long-lived account takeover." Recommended mitigations, in order of
preference: an `HttpOnly; Secure; SameSite=Strict` refresh cookie with rotation
and reuse detection, and CSP with nonces to make injection harder in the first
place.

## The changelog as a hint list

The store ships its own release notes in the bundle:

```js
[{ version: '1.3.0', date: '2026-01-15', update: [
    `Fixed blank page when viewing templates in TemplateList.`,
    `Corrected exported JSON filenames in TemplateList and TasksList.`,
    `Implemented user-level task name isolation, allowing different users
     to use the same task name.`]},
 { version: '1.2.0', date: '2026-01-05', update: [
    `Corrected the accuracy of VNA, eVNA and Downscaler in SMAT Cloud`]},
 { version: '1.1.0', date: '2025-05-19', update: [
    `Add Data page to show all data in Data Viewer page`]}]
```

Two of the three entries in the current version are cosmetic. The third is an
authorization change, and its phrasing is the tell: *user-level task name
isolation, allowing different users to use the same task name.* "Isolation" and
"allowing different users" describes fixing a namespace collision — which is
exactly what you also fix when tasks were previously addressable by a
user-supplied name alone, with no owner check.

It also dates the change: **2026-01-15**, roughly nine months before this
assessment. A collision fixed recently is worth re-testing, because adjacent
resources often missed the same fix. `/Tasks` is keyed by identifier on `DELETE`
and `GET /Log/{id}`, with `GET /Tasks` taking the collection — that is the test
surface. Not exercised here.

The general lesson is worth stating in the method section of any report:
**minified bundles frequently ship their own changelog, and a security-relevant
line in it is a pre-scoped test target that costs nothing to read.**

## A false positive worth documenting

`assets/use-global-config-<hash>.js` has a filename that reads like a backend
configuration module. It is 1.5 KB of Element Plus
`provideGlobalConfig`/`useGlobalConfig` composable — namespace, locale, z-index,
component size. Zero backend configuration. The name is a coincidence of the
component it belongs to.

It is recorded here because the same reasoning error is expensive in a bundle
with hundreds of chunks: **a filename is a hint, not evidence.** The
`use-global-config` lead was on the shortlist precisely because it sounded like
the API gateway configuration, and it cost a read to eliminate.

## A second false positive: the literal `[REDACTED ****]`

The entry chunk contains a genuine string constant:

```js
var es = `[REDACTED ****]`;
```

This is **not a leaked secret and not an operator redaction** — it is the
placeholder the HTTP layer substitutes when stripping credentials and sensitive
query values out of a URL before logging it:

```js
nc = (e) => e.replace(/(^|&)([^=&]*=)?[^&]+/g,
                      (m, a, b = '') => `${a}${b}${es}`)
rc = (e) => { let t = e.replace(/^(https?:\/{0,2})[^/?#]*@/i, `$1${es}@`);
              /* ... mask query values ... */ }
```

It is good practice, and the analysis correctly continued past it. The reason
it earns a section is that the literal text `REDACTED` in a bundle is exactly
the sort of token that stops a grep-driven review cold, and the instinct to
report it as a leaked credential is wrong. **Confirm the placeholder's role
before escalating it.**

## What static analysis did and did not establish

Established from the bundle:

- full endpoint inventory (28 endpoints, 5 resources, one base path)
- authentication mechanism, refresh rotation design, and its race handling
- token storage location and contents
- the exact scope of the client-side authorization model: **identity only**
- one persisted-but-unenforced security flag
- one route rendering a user-administration screen with no client role check

Not established, and explicitly left open in the report:

- whether any server endpoint enforces role, ownership, or tenant isolation
- whether `requirePasswordChange` is enforced server-side
- whether refresh-token rotation revokes the prior token and detects reuse
- whether file upload validates type, size, or content server-side
- whether `GET /Users`, `DELETE /Users`, `GET /Tasks` leak or mutate
  cross-tenant objects
- runtime behavior of any kind — nothing was executed against the API

## Reusable checklist this case produced

For an authenticated Vue/React SPA assessed under authorization, the high-yield
static targets in order:

1. **Entry HTML `modulepreload` set** — the eager chunks, named.
2. **Lazy-chunk filename census** — `assets/*.js` regex over the entry.
   Semantic filenames are the application map.
3. **The axios/fetch base URL plus a call-site regex** — endpoints never appear
   next to their base.
4. **The global navigation guard, in full** — count the `meta` keys it reads.
   One key means authentication only.
5. **A census of every security-relevant store field across all chunks** — a
   field name with occurrences only in the store is an unenforced control.
6. **Token persistence** — `localStorage`/`sessionStorage`/cookie, and whether
   the *refresh* token is included.
7. **The bundled changelog** — free, pre-scoped test targets.

Steps 4 and 5 are the ones that generalize. A guard that reads one boolean, and
a policy field that only the store knows about, are the two failure modes that
produce a report full of claims the backend has to disprove.

## Boundaries observed

Passive static retrieval of publicly served assets only: one `GET` of the SPA
shell and thirty-three `GET`s of JavaScript and CSS files. No authenticated
request. No endpoint invocation. No enumeration. No credential use. No
concurrency or load. No database access. Findings that would require a live
request are recorded as untested, with the exact request shape that would
answer them.
