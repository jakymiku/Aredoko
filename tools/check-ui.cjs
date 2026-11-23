// Run against a dedicated demo database; see run-ui-check.cjs for isolated startup.
// Node Playwright + Edge are required unless AREDOKO_BROWSER_CHANNEL=chromium.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const channel = process.env.AREDOKO_BROWSER_CHANNEL || 'msedge';
  const browser = await chromium.launch(channel === 'chromium' ? {headless: true} : {channel, headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1050}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(process.env.AREDOKO_BASE_URL || 'http://127.0.0.1:8765');
  await page.waitForFunction(() => document.querySelectorAll('.card').length === 60);
  assert.equal(await page.locator('#result-count').textContent(), '50,000 件');
  assert.ok(await page.locator('#inspector').isVisible());

  await page.locator('[data-kind="book"]').click();
  await page.waitForFunction(() => document.querySelector('#result-count').textContent === '12,500 件');
  await page.locator('#query').fill('雨の街');
  await page.waitForFunction(() => document.querySelector('#result-count').textContent === '1,562 件');
  assert.ok((await page.locator('.card h3').allTextContents()).every(text => text.includes('雨の街')));
  await page.locator('.art-open').first().click();
  await page.locator('#edit-form').waitFor({state: 'visible'});
  const original = {
    tags: await page.locator('#tags').inputValue(),
    shelf: await page.locator('#shelf').inputValue(),
    favorite: await page.locator('#favorite').isChecked(),
    reviewed: await page.locator('#reviewed').isChecked()
  };

  await page.locator('#tags').fill('雨の街, サンプル, UI検証済み');
  await page.locator('#shelf').fill('試作チェック');
  await page.locator('#favorite').check();
  await page.locator('#save').click();
  await page.waitForFunction(() => document.querySelector('#save-state').textContent === '変更なし');
  await page.reload();
  await page.locator('#query').fill('UI検証済み');
  await page.waitForFunction(() => document.querySelector('#result-count').textContent === '1 件');
  assert.equal(await page.locator('.card .star').count(), 1);
  await page.locator('.art-open').first().click();
  await page.locator('#edit-form').waitFor({state: 'visible'});
  assert.equal(await page.locator('#shelf').inputValue(), '試作チェック');

  // Restore the fictional record to its original state.
  await page.locator('#tags').fill(original.tags);
  await page.locator('#shelf').fill(original.shelf);
  if (original.favorite) await page.locator('#favorite').check();
  else await page.locator('#favorite').uncheck();
  if (original.reviewed) await page.locator('#reviewed').check();
  else await page.locator('#reviewed').uncheck();
  await page.locator('#save').click();
  await page.waitForFunction(() => document.querySelector('#save-state').textContent === '変更なし');
  await page.locator('#query').fill('');
  await page.waitForFunction(() => document.querySelector('#result-count').textContent === '12,500 件');
  await page.locator('[data-kind=""]').click();
  await page.waitForFunction(() => document.querySelector('#result-count').textContent === '50,000 件');
  await page.locator('#next').click();
  await page.waitForFunction(() => document.querySelector('#page-info').textContent.startsWith('2 /'));
  await page.locator('#select-page').check();
  assert.equal(await page.locator('#selected-count').textContent(), '60件選択');
  await page.locator('#bulk').click();
  await page.locator('#edit-form').waitFor({state: 'visible'});
  assert.match(await page.locator('#bulk-note').textContent(), /置き換え/);
  await page.locator('#tags').fill('未保存のテスト');
  page.once('dialog', dialog => dialog.accept());
  await page.locator('[data-view="favorites"]').click();
  await page.waitForFunction(() => document.querySelector('#breadcrumb').textContent === 'お気に入り');
  assert.ok(await page.locator('#edit-form').isHidden());
  await page.locator('[data-view="all"]').click();
  await page.waitForFunction(() => document.querySelectorAll('.card').length === 60);
  await page.keyboard.press('Control+k');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'query');

  const out = path.resolve('cache/qa');
  fs.mkdirSync(out, {recursive: true});
  await page.screenshot({path: path.join(out, 'desktop.png'), animations: 'disabled'});
  for (const width of [320, 375, 414, 540, 768]) {
    await page.setViewportSize({width, height: 900});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `overflow ${width}px`);
  }
  await page.setViewportSize({width: 540, height: 900});
  await page.screenshot({path: path.join(out, 'narrow.png'), animations: 'disabled'});
  await page.locator('.art-open').first().click();
  await page.locator('#edit-form').waitFor({state: 'visible'});
  assert.equal(await page.locator('#inspector').evaluate(el => el.classList.contains('is-open')), true);
  await page.locator('#close').click();
  assert.ok(await page.locator('#edit-form').isHidden());

  // Simulate a failed list request and ensure stale cards cannot be acted on.
  await page.route('**/api/items?**', route => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({error: '一時的なテスト障害'})
  }), {times: 1});
  await page.locator('[data-kind="image"]').click();
  await page.locator('#grid-status button').waitFor({state: 'visible'});
  assert.equal(await page.locator('.card').count(), 0);
  assert.equal(await page.locator('#select-page').isDisabled(), true);
  await page.locator('#grid-status button').click();
  await page.waitForFunction(() => document.querySelectorAll('.card').length === 60);
  assert.ok(await page.locator('#grid-status').isHidden());
  assert.deepEqual(errors, []);
  console.log('PASS: filters, search, inspector edit/persistence, paging, bulk warning, unsaved prompt, shortcut, responsive, failed-request recovery');
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
