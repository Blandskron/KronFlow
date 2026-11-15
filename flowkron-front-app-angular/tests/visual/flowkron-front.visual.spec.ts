import { expect, test } from '@playwright/test';

const baseUrl = process.env['BASE_URL'] ?? 'http://127.0.0.1:8081';

test.describe('Flowkron app visual smoke', () => {
  test('login screen renders without blank screens', async ({ page }) => {
    await page.goto(baseUrl);
    await expect(page).toHaveURL(/\/login$/);

    await page.evaluate(() => localStorage.setItem('theme', 'light'));
    await page.goto(`${baseUrl}/login`);
    await expect(page.getByRole('heading', { name: /bienvenido/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /accede con tu correo electronico/i })).toBeVisible();
    await page.screenshot({ path: 'visual-test-results/login.png', fullPage: true });
  });
});
