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
async function navigate(page, path) {
    await page.goto(root + path, { waitUntil: 'domcontentloaded', timeout: 90000 });
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
(async () => {
 const browser=await chromium.launch({headless:true});
 try {
  for(const width of [1440,390]) {
   const context=await browser.newContext({viewport:{width,height:1000}});
   const page=await context.newPage();
   await navigate(page,'/upload/wizard/overview/');
   await page.locator('#username-input').waitFor({timeout:90000});
   const reject=page.getByRole('button',{name:'Reject Unnecessary Cookies',exact:true});if(await reject.isVisible())await reject.click();
   await page.locator('#username-input').fill(values.ORCID_SANDBOX_USERNAME);
   await page.locator('#password').fill(values.ORCID_SANDBOX_PASSWORD);
   await page.getByRole('button',{name:'Sign in to ORCID',exact:true}).click();
   await page.locator('button.repository-global-logout').waitFor({state:'attached',timeout:60000});
   assert.equal(new URL(page.url()).pathname,'/upload/wizard/overview/');
   assert(!(await context.cookies()).some(c=>c.name==='sessionid' && c.value));
   await navigate(page,'/catalogue/#/');
   await page.locator('button.repository-global-logout').waitFor({state:'attached',timeout:60000});
   assert.equal(new URL(page.url()).pathname,'/catalogue/');
   assert.equal(new URL(page.url()).hash,'#/');
   assert((await context.cookies()).some(c=>c.name==='sessionid' && c.value));
   const cookies=await context.cookies();const other=await context.newPage();
   await navigate(other,'/');await other.locator('button.repository-global-logout').waitFor({state:'attached'});
   console.log('PASS Upload-first -> catalogue -> GeoNode home authenticated',width);
   await logout(page,'geo');
   await context.close();
  }
 }finally{await browser.close()}
})().catch(e=>{console.error('Catalogue QA failed:',e.message.split('\n')[0].replace(/https?:\/\/\S+/g,'[URL]'));process.exit(1)});
