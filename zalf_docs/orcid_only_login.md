# ORCID-only Login

## What this feature does

With one environment switch, GeoNode's public login and registration are restricted to **ORCID** (via ZALF's Keycloak, integrated through django-allauth's `openid_connect` provider). Local username/password accounts can no longer sign in, register, or reset passwords through the web UI.

```
SOCIALACCOUNT_ONLY=True
```

When enabled:

| Surface | Behavior |
|---------|----------|
| Top navbar (anonymous) | Single **"Register / Login via ORCID"** button — one click, straight to Keycloak/ORCID. Replaces the Register and Sign in buttons. |
| `/account/login/` | Kept as fallback (the app redirects here when login is required); shows only the ORCID provider button, no username/password form. `POST` returns 403. |
| `/account/signup/` | Shows the "Sign Up Closed" page. |
| `/account/password/reset/`, password change, email management | Gone (404) — allauth removes these URLs entirely. |
| `/account/ajax_login` | Gone (404) — not registered when the toggle is on. |
| Profile page | "Associated e-mails" and "Set/Change password" links hidden (their URLs no longer exist). |

**Deliberately unaffected:**

- **Django admin login** (`/admin/login/`) — superusers/staff keep password login (emergency access if Keycloak/ORCID is down).
- **API BasicAuthentication** — scripts, geonodectl and harvesters can keep authenticating with username/password against `/api/v2/...`. OAuth2 tokens and session auth work as before.
- Existing user accounts and their passwords are not modified — they just can't use the web login form anymore.

New users registering via ORCID get an account automatically: `OrcidExtractor` fills the profile (name, affiliation) and stores the authenticated ORCID iD in `Profile.orcid_identifier` (read from the `orcid` claim, falling back to `preferred_username`, only accepting values matching the ORCID pattern). The iD is displayed with the official ORCID icon and a hyperlinked ORCID record URL on the profile page and in the navbar user menu. The link target is configurable via `SOCIALACCOUNT_ORCID_BASE_URL` (default `https://orcid.org`; set to `https://sandbox.orcid.org` for sandbox deployments).

## Configuration

Set in the environment (dev: `.devcontainer/.env`, next to the other `SOCIALACCOUNT_*` variables):

```
# only allow login/registration via ORCID
SOCIALACCOUNT_ONLY=True

# the rest of the ORCID/Keycloak wiring (already present)
SOCIALACCOUNT_PROVIDER=ORCID
SOCIALACCOUNT_PROVIDER_HOST=https://identity-e.dataservice.zalf.de/
SOCIALACCOUNT_CLIENT_ID=...
SOCIALACCOUNT_CLIENT_SECRET=...

# where ORCID iD links point to; set to https://sandbox.orcid.org for
# deployments authenticating against the ORCID sandbox (default: https://orcid.org)
SOCIALACCOUNT_ORCID_BASE_URL=https://sandbox.orcid.org
```

Default is `False` — a deployment without the variable behaves exactly like stock GeoNode (local + social login side by side).

Setting `SOCIALACCOUNT_ONLY=True` automatically implies (forced in `settings.py`, no need to set them):

- `ACCOUNT_OPEN_SIGNUP=False` — local signup view closed
- `SOCIALACCOUNT_WITH_GEONODE_LOCAL_SINGUP=False` — local form hidden on the signup page
- `ACCOUNT_EMAIL_VERIFICATION="none"` — required by allauth's system check for social-only mode

The ORCID login URL is `/account/oidc/<SOCIALACCOUNT_PROVIDER>/login/` (e.g. `/account/oidc/ORCID/login/`). Because `SOCIALACCOUNT_LOGIN_ON_GET=True` (GeoNode default), opening it immediately redirects to Keycloak/ORCID.

## How it works (developers)

The switch leans on django-allauth ≥ 0.62 (`SOCIALACCOUNT_ONLY`, pinned 0.63.6 here), which at the URL/view level removes local signup/password/email routes and rejects login POSTs. The fork adds the glue around it:

| File | Change |
|------|--------|
| `geonode/settings.py` (ORCID section) | Reads `SOCIALACCOUNT_ONLY` from env; forces the three dependent settings when on. |
| `geonode/context_processors.py` | Exposes `SOCIALACCOUNT_ONLY` and `SOCIALACCOUNT_PROVIDER` to all templates. |
| `geonode/templates/geonode-mapstore-client/snippets/brand_navbar_default_right_menu_items.html` | Anonymous navbar: ORCID button when toggle on, stock Register/Sign in otherwise. Keeps `id="sign-in"` so the SPA's JS keeps updating the `?next=` parameter on navigation. |
| `geonode/templates/account/login.html` | Local form + "or" divider wrapped in `{% if not SOCIALACCOUNT_ONLY %}` (the flag is provided by allauth's LoginView context). |
| `geonode/people/templates/people/profile_detail.html` | Email/password links gated — the `account_email` / `account_change_password` URL names don't exist in social-only mode and would raise `NoReverseMatch` (500). |
| `geonode/urls.py` | `account/ajax_login` registered only when local login is allowed. |

Notes:

- `account_signup` / `account_login` URL names stay registered (other templates reverse them); the views themselves are closed/restricted.
- Admin and API auth are untouched because `SOCIALACCOUNT_ONLY` acts only inside allauth's views — `django.contrib.auth.backends.ModelBackend` remains in `AUTHENTICATION_BACKENDS`.

## Verification checklist

1. `python manage.py check` — allauth's system checks must pass (fails if `ACCOUNT_EMAIL_VERIFICATION` is overridden to something other than `none`).
2. Anonymous navbar shows the single ORCID button; hovering shows `/account/oidc/ORCID/login/?next=/`; clicking lands on Keycloak/ORCID.
3. `/account/login/` shows only the ORCID button; `POST` → 403.
4. `/account/signup/` → Sign Up Closed; `/account/password/reset/` → 404; `POST /account/ajax_login` → 404.
5. `/admin/login/` still accepts a superuser password; `curl -u <user>:<pass> .../api/v2/users/` still returns 200.
6. Full round-trip: ORCID login → own profile page renders without email/password links → Log out → redirect to `SOCIALACCOUNT_LOGOUT_REDIRECT_URL`.

## Logout

The logout confirmation page (`/account/logout/`) offers two actions:

- **Log out** — ends only the GeoNode session (redirect to `next` / `ACCOUNT_LOGOUT_REDIRECT_URL`).
- **Log out from GeoNode and ORCID** — full RP-initiated logout chain:
  1. GeoNode session is ended;
  2. redirect to Keycloak's `end_session_endpoint` (`SOCIALACCOUNT_PROVIDER_END_SESSION_URL`, derived from `SOCIALACCOUNT_PROVIDER_ROOT`) with `id_token_hint` (stashed in the session at login) so the **Keycloak SSO session is terminated** — without this, the next "Login via ORCID" would sign the user in silently;
  3. Keycloak forwards to the ORCID signout page (`SOCIALACCOUNT_LOGOUT_REDIRECT_URL` as `post_logout_redirect_uri`), ending the orcid.org session too.

Implemented in `LocalAccountAdapter.get_logout_redirect_url` (honors the `logout_orcid` form field; the button lives in its own form without a `next` field because allauth lets `next` override the adapter redirect). The id_token is stored in the Django session by `GenericOpenIDConnectAdapter.complete_login`; for sessions predating that, `client_id` is sent instead and Keycloak shows a logout confirmation.

**Keycloak client configuration required:** the ORCID signout URL (e.g. `https://sandbox.orcid.org/signout`) must be listed under **"Valid post logout redirect URIs"** of the GeoNode client in Keycloak — otherwise Keycloak rejects the logout redirect.

## Known limitations

- The superuser "Invite users" flow leads invitees to the closed signup page (invitations don't work in ORCID-only mode).
- `/people/forgotname` still exists (harmless — usernames come from ORCID).
- If Keycloak/ORCID is unreachable, only `/admin/login/` works; plan superuser access accordingly.

## ORCID member-integration compliance (issue #309)

Status against the [minimum requirements for member integrations](https://info.orcid.org/documentation/integration-guide/minimum-requirements-for-member-integrations/):

| Requirement | Status | Implementation |
|---|---|---|
| Collect authenticated ORCID iDs using OAuth | ✅ | Keycloak ORCID plugin brokers the OAuth flow; GeoNode consumes it via django-allauth `openid_connect`. No self-asserted iDs. |
| ORCID as primary sign-in / ORCID-branded button | ✅ | With `SOCIALACCOUNT_ONLY=True`, ORCID is the *only* sign-in. Navbar button and login-page button carry the official ORCID iD icon (`geonode/static/geonode/img/orcid_id.svg`, vendored unaltered from orcid.org). |
| HTTPS redirect URIs only | ✅ (deployment) | Production runs behind HTTPS; the redirect URIs registered in Keycloak/ORCID must be `https://` — verify per deployment. |
| Relevant scopes | ✅ | `openid`, `email`, `profile` via the OIDC well-known configuration. |
| Store Name, ORCID iD and access token | ✅ | Name via `OrcidExtractor` (`given_name`/`family_name`); ORCID iD stored in `Profile.orcid_identifier` (`extract_orcid_identifier`: `orcid` claim → `preferred_username` fallback, ORCID-pattern validated); tokens persisted via `SOCIALACCOUNT_STORE_TOKENS=True` (allauth `SocialToken`). |
| Display the iD per display guidelines | ✅ | Official icon + full hyperlinked ORCID record URL on the profile page; icon + compact iD in the navbar user menu. Base URL via `SOCIALACCOUNT_ORCID_BASE_URL` (production `https://orcid.org`, sandbox `https://sandbox.orcid.org`). |
| No manual entry/search of the iD | ✅ | `orcid_identifier` removed from the profile edit form — set exclusively by the authenticated login. (Django admin retains it for staff corrections.) |
| No visibility-settings / public-email requests | ✅ | Nothing asks users to change ORCID visibility or publish their email. |
| Latest API version | ⚠️ (external) | Depends on the Keycloak ORCID plugin — track upstream plugin updates. |
| Explain ORCID benefits to users | ✅ | Benefits explanation (why the iD is collected, what users gain, free registration, link to orcid.org) on the login page; a "What is ORCID?" link next to the navbar sign-in button leads there. |
