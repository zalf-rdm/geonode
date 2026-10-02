# Repository authentication through Keycloak

Implementation: [GeoNode #778](https://github.com/zalf-rdm/geonode/issues/778) and [Upload Tool #553](https://github.com/zalf-rdm/upload-tool/issues/553). The coordinated runtime changes were merged in GeoNode PR #780 and Upload Tool PR #554.

`repository_sso` is an application-owned Django integration, vendored in both repositories. Keep its Python modules, migrations, and protocol tests synchronized. The logout template deliberately uses each application's own base template and block. GeoNode retains its profile/group adapter; Upload Tool retains its existing login signals and group mappings. Browser login/logout entry routes are handled by GeoNode. The coordinated ZALF MapStore navigation fix uses canonical `/upload/` and `/catalogue/` URLs.

## Behavior

With `KEYCLOAK_SSO_ENABLED=true` (the default), interactive login goes through the configured Keycloak OIDC provider, including Django admin and development-login routes. Application password/signup/reset entry points cannot authenticate locally. Accounts and resource permissions remain in each application. Existing SocialAccounts are identified by the existing provider ID and Keycloak `sub`; automatic email linking is disabled.

Opening an anonymous home page or GeoNode catalogue attempts OIDC with `prompt=none`. An existing Keycloak session establishes the second application's session without asking for credentials. A missing SSO session returns to the anonymous page, with a per-application 60-second probe cooldown. Explicit login starts the ordinary Keycloak flow. Protected deep links use the ordinary login flow. Session/CSRF cookies remain separate, including when the apps share a host through `/upload/`.

The callback validates the ID token with the configured realm's signing keys and client audience, then requires matching UserInfo subject and a Keycloak `sid`. It binds the resulting Django session to that identity in the application database. Unbound sessions created before activation must authenticate again.

Logout is a CSRF-protected POST. It immediately revokes the initiating application's binding, flushes its session, and sends the browser to Keycloak's end-session endpoint with the user's ID token. A supplied `next` or old application-only option cannot override global logout. The browser returns to the configured Repository home URL. External ORCID Registry logout is controlled by Keycloak's identity-provider/broker policy; this implementation does not promise to clear external ORCID cookies.

Keycloak posts signed logout tokens to `/sso/backchannel-logout/` in both applications. Validation checks RS256 signature, configured issuer, client audience, `iat` (maximum age 300 seconds, 10 seconds of clock tolerance), optional JWT expiry, nonempty identifiers, logout event, and absence of `nonce`. Durable event records reject replay. Session logout targets the specified `sid`; subject-only logout targets the subject's sessions created before the event. Binding revocation rejects resurrected/replayed application sessions and callbacks that arrive after their Keycloak session was revoked. Logout records must remain available while associated sessions or pending login flows can still be used; do not truncate them during ordinary `clearsessions` maintenance.

Authenticated use also refreshes the user's token against Keycloak at most once per 60 seconds (earlier near ID-token expiry). This bounds a missed backchannel notification to the next check. A database row lock serializes refresh across workers, and rotating refresh tokens are stored in the binding rather than in competing request-local session snapshots. Use PostgreSQL or another database with row locking for deployment; SQLite is only the isolated test harness. Refresh rejection ends local access. An IdP/network failure returns HTTP 503 and preserves the session for retry. Logout remains available during an outage.

This controls interactive application sessions. Existing service/API credentials need their own migration policy and are not converted to browser SSO by this change.

## Configure and activate

1. Configure both applications against the same existing Keycloak realm, with a separate confidential client per app. Keep provider IDs stable so existing SocialAccounts still resolve.
2. Enable standard authorization-code flow, PKCE S256, RS256 ID-token signing, and online refresh tokens. Configure the Keycloak login screen to expose the desired username/password, institutional and ORCID options. Remove any forced ORCID-only redirect if other login methods must be available. Do not replace the realm or change subjects casually.
3. Retain the existing callback URLs: GeoNode `/account/oidc/<provider_id>/login/callback/`; Upload Tool its existing localized `/accounts/oidc/<provider_id>/login/callback/`, including any public `/upload` prefix. Preserve HTTPS/proxy/script-prefix configuration.
4. Set each client's **Backchannel Logout URL** to that application's public `/sso/backchannel-logout/` endpoint (include `/upload` when mounted there). Enable **Backchannel Logout Session Required**. Verify Keycloak can reach both endpoints directly and that gateways do not require a browser session or block their POSTs. The endpoint itself authenticates the JWT, so it is CSRF exempt.
5. Allow the exact Repository home URL in each client's **Valid post logout redirect URIs**. Set `KEYCLOAK_SSO_POST_LOGOUT_URL` to that URL in both apps. Upload Tool's `REPOSITORY_PUBLIC_BASE_URL` controls browser navigation separately from its GeoNode API destination.
6. Supply the existing client configuration: GeoNode `SOCIALACCOUNT_PROVIDER_HOST`, `SOCIALACCOUNT_PROVIDER_REALM`, `SOCIALACCOUNT_PROVIDER`, `SOCIALACCOUNT_CLIENT_ID`, `SOCIALACCOUNT_CLIENT_SECRET`; Upload Tool `DJANGO_IDANDSSO_PROVIDER_HOST`, `DJANGO_IDANDSSO_PROVIDER_REALM`, `DJANGO_IDANDSSO_PROVIDER_ID`, `DJANGO_IDANDSSO_CLIENT_ID`, `DJANGO_IDANDSSO_SECRET_KEY`. Hosts retain their existing trailing-slash convention. Session engine must be Django `db` or `cached_db`. System checks reject missing clients/issuer or unsupported session engines.
7. Vet legacy local accounts against Keycloak's realm export/admin records. Provision or federate their credentials in Keycloak before activation; local Django password hashes are not automatically imported. For each verified pairing, run `python manage.py link_keycloak_identity --user-id <local-id> --subject <keycloak-sub>` in each application, then repeat with `--apply` to persist it. Dry run is the default. The command refuses identity collisions and preserves the local user ID, data and permissions. Never infer ownership from an unverified matching email.
8. Run `python manage.py migrate repository_sso` in both applications before enabling the new runtime. Run `python manage.py check`, then validate a fresh login and logout using the deployed clients. Existing unbound sessions will require a new login. Setting `KEYCLOAK_SSO_ENABLED=false` is a source-level rollback toggle; it restores the previous local-auth policy and does not undo identity links or migrations.

Protect application database access and backups: bindings contain the user's ID and refresh tokens, like existing allauth token storage. Do not log tokens, full auth URLs, session cookies or client secrets. Keep the applications' clocks synchronized with Keycloak.

References: [Keycloak OIDC logout](https://www.keycloak.org/docs/latest/server_admin/index.html#_oidc-logout) and [OIDC Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html).

## Verification

On 2026-10-01, the isolated integration suite passed 29 tests for each application (58 executions): Django 5.2.12 with GeoNode's allauth 0.63.6 and PyJWT 2.8.0, and Upload Tool's allauth 65.14.1. It checks signed/forged/malformed/replayed JWTs, session and subject isolation, late login, replayed cookies, local-login guards, CSRF, global redirect enforcement, refresh rejection/outage, stale worker snapshots, and explicit account linking.

Run from GeoNode's root or Upload Tool's `src`, using the corresponding environment:

```sh
python -m django test repository_sso.tests --settings=repository_sso.tests.settings
```

The browser harness uses two separate Django processes with the two allauth versions and an HTTP OIDC fixture. It exercises real authorization codes and PKCE, existing-account login, cross-app SSO, refresh, global logout in both directions, old-cookie rejection, and provider-initiated logout. It passed 18 scenarios: both entry directions at 320/360/375/390/412/430/768/1440 px, plus two provider-initiated logout cases. No page/console errors, horizontal overflow or undersized logout buttons were found. The harness renders the shipped logout body in minimal base templates; it does not validate the full GeoNode/Upload navigation or production styling.

To reproduce, use separate terminals (GeoNode root for the first two, Upload Tool `src` for the third):

```sh
python -m repository_sso.tests.idp_stub
```

```sh
SSO_TEST_DB=/tmp/repository-sso-qa.sqlite SSO_TEST_CLIENT=repository SSO_TEST_ISSUER=http://127.0.0.1:18990/realms/repository SSO_TEST_RETURN=http://127.0.0.1:18991/ python -m repository_sso.tests.serve 18991
```

```sh
SSO_TEST_DB=/tmp/upload-sso-qa.sqlite SSO_TEST_CLIENT=upload SSO_TEST_ISSUER=http://127.0.0.1:18990/realms/repository SSO_TEST_RETURN=http://127.0.0.1:18991/ python -m repository_sso.tests.serve 18992
```

Then run `node repository_sso/tests/browser.cjs` from GeoNode root with Playwright/Chromium installed and available to Node (set `NODE_PATH` to the installed `node_modules` directory when needed). All fixture identities are synthetic; fixtures are never included in application URL configurations.

## Live test deployment — 2026-10-01

At the user’s request, the integration was copied to the running GeoNode pod and both Upload Tool web pods on `kubernetes-admin@fizz.cluster`, and both migrations and Django system checks passed. This is a temporary container filesystem overlay; a container restart or redeploy restores the image version. The source branches still need the normal image/release workflow.

The existing `ORCID` realm at `https://identity-e.dataservice.zalf.de/` was configured using the supplied administrator credentials. Both existing confidential clients now use PKCE S256, RS256, refresh tokens, session-required backchannel logout, and the exact Repository home post-logout redirect. GeoNode’s backchannel is `https://repository-e.dataservice.zalf.de/sso/backchannel-logout/`; Upload Tool’s public backchannel is `https://repository-e.dataservice.zalf.de/upload/sso/backchannel-logout/`. Existing broker identities and client callback allowlists were preserved.

Real Chromium login with the supplied ORCID Sandbox account passed, followed by silent SSO into `/upload/`. The shipped profile dropdowns submit a CSRF-protected POST directly to global logout. Logout from either app returned to the anonymous Repository, and replaying the previous cookies did not restore access in either app. Deleting the QA session at Keycloak also delivered backchannel logout: matching bindings were revoked in both application databases, visible from both Upload Tool pods. Actual menus were exercised at 320/360/375/390/412/430/768/1440 px, with visible logout controls at least 44 px high and no document horizontal overflow. Phone screenshots were visually inspected.

The existing Upload Tool Kubernetes health probe uses the account-login URL. Central SSO would redirect that request and cause container restarts. GET requests to that route with the Kubernetes probe user agent now receive only `OK`; ordinary browser requests and all login POSTs continue to Keycloak. The new regression confirms that neither probe GET nor POST authenticates locally. Both live pods’ health probes return HTTP 200, and 30 isolated integration tests pass per app (60 executions).

ORCID Registry cookies are governed by the external broker; the tested global logout ends Keycloak and application sessions.

## ORCID reauthentication and catalogue handoff

The final test realm broker uses `config.defaultScope=openid`, `config.prompt=login`, and `config.acceptsPromptNoneForwardFromClient=false`. ORCID processes `prompt` only for an OpenID request; `/authenticate` alone silently reused the ORCID browser cookie after global logout. Existing Keycloak SSO still allows cross-app navigation without a password prompt. The ORCID plugin does not expose `prompt` in its admin UI; configure it through the Admin API. See [ORCID official OpenID documentation](https://github.com/ORCID/ORCID-Source/blob/main/orcid-web/ORCID_AUTH_WITH_OPENID_CONNECT.md).

The landing-path allowlist includes GeoNode `/catalogue/` and localized app roots. This establishes a GeoNode session when the first login was in Upload Tool, before the catalogue SPA receives its user configuration. HTML requests probe once; JSON/API requests do not. The additional regression covers the catalogue destination/query and Portuguese root, no redirect loop, and JSON exclusion. The current isolated suites pass 31 tests per app.

Final sanitized Keycloak JSON and annotated screenshots are in GeoNode `testing/keycloak-sso-2026-10-01/`. The permanent images deployed on 2026-10-02 are Upload Tool `0.1.346` and GeoNode `v5.0.3-zalf001.27`; the latter includes MapStore client `5.0.1.post54`.

## Release verification — 2026-10-02

GeoNode's full GitHub Actions suite passed in run `36986366532`. Upload Tool passed 189 application tests and 32 isolated SSO tests in its Docker/PostgreSQL environment. Both repositories include a PostgreSQL-only concurrent refresh regression. The test starts two independent database connections with the same stale binding and verifies that the row lock permits exactly one refresh request and persists a single rotating-token result. The same two-connection check passed against each deployed application's PostgreSQL database using a synthetic binding that was deleted after the assertion.

The identity audit compares local accounts with Keycloak subjects without logging names, email addresses, credentials, tokens, or complete authorization URLs. The realm had six enabled users, all federated through ORCID. All six were already linked in GeoNode. Upload Tool had three links; one additional local account matched a subject already vetted in GeoNode by unique email and exact full name. Its dry run and applied link both passed, preserving its local ID, groups, submissions, and permissions.

Legacy migration is still required before declaring activation complete for every existing user. The audit found 11 unlinked GeoNode accounts and 21 unlinked Upload Tool accounts used during the preceding year. Keycloak has no subjects to pair with them yet. Automatic email linking remains disabled because it could transfer an account's permissions to an unverified identity. An administrator must verify each owner, provision or federate that person in Keycloak, run `link_keycloak_identity` without `--apply`, inspect the pairing, and then apply it. Service identities need an explicit non-browser authentication policy. Keep issues #778 and #553 open until this list reaches zero or every remaining account has an approved documented exception.
