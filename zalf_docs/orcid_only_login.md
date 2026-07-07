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

New users registering via ORCID get an account automatically (profile filled by `OrcidExtractor`; ORCID iD stored on the profile).

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

## Known limitations

- The superuser "Invite users" flow leads invitees to the closed signup page (invitations don't work in ORCID-only mode).
- `/people/forgotname` still exists (harmless — usernames come from ORCID).
- If Keycloak/ORCID is unreachable, only `/admin/login/` works; plan superuser access accordingly.
