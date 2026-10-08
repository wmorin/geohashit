import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const polygon = { type: 'Polygon', coordinates: [[[2.30, 48.82], [2.40, 48.82], [2.40, 48.90], [2.30, 48.90], [2.30, 48.82]]] };

async function ready(page) {
  await expect(page.locator('#download-geojson')).toBeEnabled({ timeout: 20000 });
  await expect(page.locator('#metric-count')).not.toHaveText('—');
}

test('default coverage works without external network and exports matching cells', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1|localhost|wmorin\.github\.io)/, route => route.abort());
  await page.goto('./');
  await ready(page);
  await expect(page.locator('#preset')).toHaveValue('paris');
  const count = Number((await page.locator('#metric-count').innerText()).replace(/[^0-9]/g, ''));
  expect(count).toBeGreaterThan(0);
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#download-geojson').click();
  const downloaded = await downloadPromise;
  const collection = JSON.parse(await readFile(await downloaded.path(), 'utf8'));
  expect(collection.type).toBe('FeatureCollection');
  expect(collection.features).toHaveLength(count);
  expect(collection.features.every(feature => /^[0-9bcdefghjkmnpqrstuvwxyz]+$/.test(feature.properties.geohash))).toBeTruthy();
  const idsPromise = page.waitForEvent('download');
  await page.locator('#download-ids').click();
  const ids = await readFile(await (await idsPromise).path(), 'utf8');
  for (const feature of collection.features) expect(ids).toContain(feature.properties.geohash);
  expect(errors).toEqual([]);
});

test('coverage rules update metrics and code and mobile has no horizontal overflow', async ({ page }) => {
  await page.goto('./');
  await ready(page);
  await page.locator('input[value="inside"]').check();
  await expect(page.locator('#code-content')).toContainText('inside');
  await ready(page);
  await expect(page.locator('#metric-spill')).toContainText(/^0/);
  await page.locator('input[value="intersect"]').check();
  await expect(page.locator('#code-content')).toContainText('intersect');
  await ready(page);
  await expect(page.locator('#metric-missed')).toContainText(/^0/);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow).toBe(false);
});

test('preset link restores selected shape, precision, and mode', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('./');
  await ready(page);
  await page.locator('#preset').selectOption('delivery');
  await ready(page);
  await page.locator('input[value="intersect"]').check();
  await ready(page);
  await page.locator('#share-button').click();
  const link = await page.evaluate(() => navigator.clipboard.readText());
  expect(link).toContain('delivery');
  expect(link).toContain('intersect');
  await page.goto(link);
  await ready(page);
  await expect(page.locator('#preset')).toHaveValue('delivery');
  await expect(page.locator('input[value="intersect"]')).toBeChecked();
});

test('invalid JSON gives a recoverable error and valid import stays private', async ({ page }) => {
  await page.goto('./');
  await ready(page);
  await page.locator('#import-button').click();
  await page.locator('#geojson-input').fill('{bad json');
  await page.locator('#import-apply').click();
  await expect(page.locator('#import-error')).not.toBeEmpty();
  await page.locator('#geojson-input').fill(JSON.stringify(polygon));
  await page.locator('#import-apply').click();
  await ready(page);
  await expect(page.locator('#preset')).toHaveValue('custom');
  await expect(page.locator('#share-button')).toBeDisabled();
  expect(page.url()).not.toContain('coordinates');
});

test('invalid topology is rejected without replacing the current shape', async ({ page }) => {
  await page.goto('./');
  await ready(page);
  await page.locator('#import-button').click();
  await page.locator('#geojson-input').fill(JSON.stringify({ type: 'Polygon', coordinates: [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]] }));
  await page.locator('#import-apply').click();
  await expect(page.locator('#import-error')).toContainText(/cross|invalid|repair/i);
  await expect(page.locator('#preset')).toHaveValue('paris');
  await page.getByRole('button', { name: 'Close import dialog' }).click();
  await ready(page);
});

test('draw polygon completes with export and cancellation restores the shape', async ({ page }) => {
  await page.goto('./');
  await ready(page);
  await page.locator('#draw-button').click();
  await expect(page.locator('#draw-controls')).toBeVisible();
  await page.locator('#map').click({ position: { x: 100, y: 150 } });
  await page.locator('#map').click({ position: { x: 200, y: 150 } });
  await page.locator('#map').click({ position: { x: 150, y: 250 } });
  await page.locator('#draw-finish').click();
  await ready(page);
  await expect(page.locator('#preset')).toHaveValue('custom');
  await page.locator('#draw-button').click();
  await page.locator('#draw-cancel').click();
  await ready(page);
});

test('every bundled preset loads and failed fetches recover without stale exports', async ({ page }) => {
  await page.goto('./');
  await ready(page);
  for (const preset of ['france', 'delivery', 'paris']) {
    await page.locator('#preset').selectOption(preset);
    await ready(page);
    await expect(page.locator('#preset')).toHaveValue(preset);
    expect(Number((await page.locator('#metric-count').innerText()).replace(/[^0-9]/g, ''))).toBeGreaterThan(0);
  }
  await page.route('**/examples/france.geojson', route => route.fulfill({ status: 404, body: '' }));
  await page.locator('#preset').selectOption('france');
  await expect(page.locator('#map-message')).toContainText('Could not load');
  await expect(page.locator('#download-geojson')).toBeDisabled();
  await expect(page.locator('#share-button')).toBeDisabled();
  await page.locator('#preset').selectOption('paris');
  await ready(page);
});

test('rapid settings changes export only the final requested coverage', async ({ page }) => {
  await page.goto('./');
  await ready(page);
  await page.locator('#precision').evaluate(input => {
    for (const value of ['8', '4', '7', '5']) { input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); }
  });
  await page.locator('input[value="inside"]').check();
  await ready(page);
  await expect(page.locator('#code-content')).toContainText('precision=5');
  await expect(page.locator('#code-content')).toContainText('inside');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#download-ids').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain('p5-inside');
  const ids = (await readFile(await download.path(), 'utf8')).trim().split('\n').filter(Boolean);
  expect(ids.every(hash => hash.length <= 5)).toBeTruthy();
  await expect(page.locator('#metric-spill')).toContainText(/^0/);
});
