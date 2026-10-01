// Run against serve.py instances and idp_stub.py, using synthetic identities only.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const geo = 'http://127.0.0.1:18991';
const upload = 'http://127.0.0.1:18992';

(async () => {
  const browser = await chromium.launch({headless: true});
  let scenarios = 0;
  try {
    for (const width of [320, 360, 375, 390, 412, 430, 768, 1440]) {
      for (const entry of [geo, upload]) {
        const context = await browser.newContext({viewport: {width, height: 900}});
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
        let authorizations = 0;
        page.on('request', request => {
          if (new URL(request.url()).pathname.endsWith('/auth')) authorizations++;
        });
        await page.goto(entry + '/');
        await page.waitForURL(entry + '/');
        await page.getByText('Anonymous', {exact: false}).waitFor();
        await page.getByRole('link', {name: 'Login', exact: true}).click();
        await page.waitForURL(entry + '/protected/');
        assert.equal(await page.textContent('body'), 'Protected');
        const other = entry === geo ? upload : geo;
        await page.goto(other + '/');
        await page.waitForURL(other + '/');
        await page.getByText('Signed in', {exact: false}).waitFor();
        assert.equal(authorizations, 3, 'one anonymous probe, explicit login, and cross-app silent SSO');
        for (const base of [geo, upload]) {
          const expire = await context.request.post(base + '/fixture/expire-refresh/', {form: {fixture: 'expire'}});
          assert.equal(expire.status(), 200);
          const refreshed = await context.request.get(base + '/protected/');
          assert.equal(refreshed.status(), 200, 'bound session must refresh through the IdP');
        }
        const old = await context.cookies();
        const oldSessions = old.filter(cookie => ['repository_session', 'upload_session'].includes(cookie.name));
        assert.equal(oldSessions.length, 2);
        await page.goto(entry + '/account/logout/?next=https://attacker.invalid/');
        assert.equal(await page.getByRole('button', {name: 'Log out', exact: true}).count(), 1);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'logout page overflow');
        const bounds = await page.getByRole('button', {name: 'Log out', exact: true}).boundingBox();
        assert.ok(bounds.height >= 44);
        if (entry === geo && width === 390 && process.env.SSO_QA_SCREENSHOT) {
          await page.screenshot({path: process.env.SSO_QA_SCREENSHOT});
        }
        await page.getByRole('button', {name: 'Log out', exact: true}).click();
        await page.waitForURL(geo + '/');
        await page.getByText('Anonymous', {exact: false}).waitFor();
        for (const [base, name] of [[geo, 'repository_session'], [upload, 'upload_session']]) {
          const cookie = oldSessions.find(cookie => cookie.name === name);
          const result = await context.request.get(base + '/protected/', {
            headers: {Cookie: name + '=' + cookie.value}, maxRedirects: 0,
          });
          assert.equal(result.status(), 302, 'replayed old app cookie must not authenticate');
        }
        assert.equal(errors.length, 0, 'browser errors');
        scenarios++;
        await context.close();
      }
    }
    for (const entry of [geo, upload]) {
      const context = await browser.newContext();
      const page = await context.newPage();
      await page.goto(entry + '/account/login/');
      await page.waitForURL(entry + '/protected/');
      const other = entry === geo ? upload : geo;
      await page.goto(other + '/');
      await page.getByText('Signed in', {exact: false}).waitFor();
      const result = await context.request.post('http://127.0.0.1:18990/fixture/revoke/', {form: {fixture: 'revoke'}});
      assert.equal(result.status(), 200);
      for (const base of [geo, upload]) {
        const response = await context.request.get(base + '/protected/', {maxRedirects: 0});
        assert.equal(response.status(), 302, 'IdP-initiated logout must revoke both application sessions');
      }
      scenarios++;
      await context.close();
    }
    console.log(JSON.stringify({passed: scenarios, widths: [320,360,375,390,412,430,768,1440],
      checks: ['anonymous silent probe', 'OIDC code and PKCE', 'existing identity', 'cross-app SSO',
               'session refresh', 'global logout both directions', 'IdP-initiated logout', 'backchannel logout', 'old cookie replay',
               'logout return allowlist', 'CSRF form', 'overflow', 'touch target', 'browser errors']}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
