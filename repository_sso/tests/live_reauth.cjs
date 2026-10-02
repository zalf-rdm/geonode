const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const root = process.env.REPOSITORY_QA_URL || 'https://repository-e.dataservice.zalf.de';
const envFile = process.env.ORCID_QA_ENV;
const values = { ...process.env };
if (envFile) {
    for (const line of fs.readFileSync(envFile, 'utf8').split('\n')) {
        const match = line.match(/^\s*(ORCID_SANDBOX_USERNAME|ORCID_SANDBOX_PASSWORD)\s*=\s*(.*)\s*$/);
        if (match) values[match[1]] = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
    }
}
for (const key of ['ORCID_SANDBOX_USERNAME', 'ORCID_SANDBOX_PASSWORD']) {
    if (!values[key]) throw new Error('Missing QA credential: ' + key);
}
async function qaContext(browser, options) {
    const context = await browser.newContext(options);
    if (process.env.MAPSTORE_QA_DIST) {
        const path = require('node:path');
        const dist = path.resolve(process.env.MAPSTORE_QA_DIST);
        await context.route(root + '/static/mapstore/dist/**', async route => {
            const relative = new URL(route.request().url()).pathname.split('/static/mapstore/dist/')[1];
            const asset = path.resolve(dist, relative);
            if (asset.startsWith(dist + path.sep) && fs.existsSync(asset) && fs.statSync(asset).isFile()) {
                await route.fulfill({ path: asset });
            } else {
                await route.continue();
            }
        });
    }
    return context;
}
async function navigate(page, path) {
    await page.goto(root + path, { waitUntil: 'domcontentloaded' });
}
async function signIn(page) {
    await navigate(page, '/account/oidc/ORCID/login/?next=/');
    await page.locator('#username-input').waitFor({ timeout: 45000 });
    const reject = page.getByRole('button', { name: 'Reject Unnecessary Cookies', exact: true });
    if (await reject.isVisible()) await reject.click();
    await page.locator('#username-input').fill(values.ORCID_SANDBOX_USERNAME);
    await page.locator('#password').fill(values.ORCID_SANDBOX_PASSWORD);
    await page.getByRole('button', { name: 'Sign in to ORCID', exact: true }).click();
    await page.waitForURL(url => url.origin === root && url.pathname === '/', { timeout: 60000, waitUntil: 'domcontentloaded' });
    await page.locator('button.repository-global-logout').waitFor({ state: 'attached' });
}
async function assertReauth(page) {
    try { await page.locator('#username-input').waitFor({ timeout: 45000 }); } catch(error) {
        const url=new URL(page.url());console.log('REAUTH_SCREEN',url.host,url.pathname,'headings',await page.locator('h1,h2').allTextContents());throw error;
    }
    assert.equal(new URL(page.url()).host, 'sandbox.orcid.org');
    assert.equal(new URL(page.url()).searchParams.get('prompt'), 'login');
    assert(new URL(page.url()).searchParams.get('scope').split(' ').includes('openid'));
    assert(await page.locator('#password').isVisible());
    // Pause to ensure this is not a transient page that silently signs in.
    await page.waitForTimeout(1500);
    assert.equal(new URL(page.url()).host, 'sandbox.orcid.org');
}
async function logout(page, app) {
    const toggle = page.locator(app === 'geo' ? '.gn-user-menu-dropdown .dropdown-toggle' : '.repository-user-toggle').last();
    if (!await toggle.isVisible()) {
        await page.locator('.navbar-toggler,button.navbar-toggle,.zalf-navigation__toggle').first().click();
    }
    await toggle.click();
    await page.locator('button.repository-global-logout').click();
    await page.waitForURL(url => url.origin === root && url.pathname === '/', { timeout: 45000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);
    assert.equal(await page.locator('button.repository-global-logout').count(), 0);
}
async function scenario(browser, app, lang, width) {
    console.log('CASE',app,lang,width);
    const context = await qaContext(browser, { viewport: { width, height: 1000 } });
    const page = await context.newPage();
    let pageErrors = 0;
    page.on('pageerror', () => pageErrors++);
    page.on('requestfailed',r=>{const u=new URL(r.url());console.log('NETWORK_FAILURE',u.host,u.pathname,r.failure()?.errorText)});
    await signIn(page);console.log('STEP signed in');
    const geoTab = await context.newPage();
    await navigate(geoTab, '/');
    const uploadTab = await context.newPage();
    await navigate(uploadTab, '/upload/' + lang + '/');
    await uploadTab.locator('button.repository-global-logout').waitFor({ state: 'attached', timeout: 45000 });
    assert.equal(new URL(uploadTab.url()).origin, root);
    assert((await context.cookies()).some(cookie => cookie.domain.includes('sandbox.orcid.org')));
    console.log('STEP cross-app SSO');
    const catalogueTab = await context.newPage();
    await navigate(catalogueTab, '/catalogue/#/');
    await catalogueTab.locator('button.repository-global-logout').waitFor({ state: 'attached' });
    const oldState = await context.storageState();
    if (app === 'upload') await navigate(page, '/upload/' + lang + '/');
    await logout(page, app);console.log('STEP logged out');
    const menu = page.getByRole('link', { name: 'Upload', exact: true }).first();
    if (!await menu.isVisible()) await page.locator('.zalf-navigation__toggle').click();
    console.log('UPLOAD_LINK',await menu.getAttribute('href'));
    await menu.click();console.log('AFTER_UPLOAD_CLICK',new URL(page.url()).host,new URL(page.url()).pathname);
    await assertReauth(page);console.log('STEP reentry asks credentials');
    // Open tabs must lose server access on their next request.
    await uploadTab.reload({ waitUntil: 'domcontentloaded' });
    await assertReauth(uploadTab);console.log('STEP stale upload tab');
    await geoTab.reload({ waitUntil: 'domcontentloaded' });
    await geoTab.waitForTimeout(1500);
    assert.equal(await geoTab.locator('button.repository-global-logout').count(), 0);
    assert.equal(new URL(geoTab.url()).origin, root);
    await catalogueTab.reload({ waitUntil: 'domcontentloaded' });
    await catalogueTab.waitForTimeout(1500);
    assert.equal(await catalogueTab.locator('button.repository-global-logout').count(), 0);
    // Restore the old cookie jar, including ORCID cookies, in another context.
    const replay = await qaContext(browser, { storageState: oldState });
    const replayPage = await replay.newPage();
    await navigate(replayPage, '/upload/wizard/overview/');
    await assertReauth(replayPage);console.log('STEP cookie replay');
    await replay.close();
    console.log('PASS', JSON.stringify({ logout: app, language: lang, width, sso: true, uploadReentryRequiresCredentials: true, staleTabs: true, oldCookies: true, pageErrors }));
    assert.equal(pageErrors, 0);
    await context.close();
}
async function providerScenario(browser) {
    const { spawnSync } = require('node:child_process');
    const context = await qaContext(browser, { viewport: { width: 1440, height: 1000 } });
    const other = await qaContext(browser, { viewport: { width: 1440, height: 1000 } });
    try {
        const page = await context.newPage();
        await signIn(page);
        await navigate(page, '/upload/pt/');
        await page.locator('button.repository-global-logout').waitFor({ state: 'attached' });
        const otherPage = await other.newPage();
        await signIn(otherPage);
        await navigate(otherPage, '/upload/en/');
        await otherPage.locator('button.repository-global-logout').waitFor({ state: 'attached' });
        const state = await context.storageState();
        const result = spawnSync('python', [process.env.ORCID_QA_PROVIDER_HELPER], { input: JSON.stringify(state), encoding: 'utf8', timeout: 45000 });
        assert.equal(result.status, 0, 'Keycloak session revocation must reach both applications');
        console.log(result.stdout.trim());
        await page.reload({ waitUntil: 'domcontentloaded' });
        await assertReauth(page);
        await otherPage.reload({ waitUntil: 'domcontentloaded' });
        await otherPage.locator('button.repository-global-logout').waitFor({ state: 'attached' });
        assert.equal(new URL(otherPage.url()).origin, root);
        await logout(otherPage, 'upload');
        console.log('PASS provider logout: both apps revoked across workers, reentry needs password, independent browser session preserved');
    } finally {
        await context.close();
        await other.close();
    }
}
(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        if (process.env.ORCID_QA_CASE === 'provider') {
            assert(process.env.ORCID_QA_PROVIDER_HELPER, 'Missing provider QA helper');
            await providerScenario(browser);
            return;
        }
        for (const [app, lang, width] of [['upload', 'en', 1440], ['geo', 'en', 1440], ['upload', 'pt', 390], ['geo', 'pt', 390]]) {
            if(process.env.ORCID_QA_CASE==='mobile' && width!==390)continue;
            await scenario(browser, app, lang, width);
        }
    } finally {
        await browser.close();
    }
})().catch(error => {
    console.error('Live reauthentication QA failed:', error.message.split('\n')[0].replace(/https?:\/\/\S+/g, '[URL]'));
    process.exit(1);
});
