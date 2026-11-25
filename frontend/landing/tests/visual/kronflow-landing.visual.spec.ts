import { expect, test } from '@playwright/test';

const baseUrl = process.env['BASE_URL'] ?? 'http://127.0.0.1:8080';
const appUrl = process.env['APP_PUBLIC_URL'] ?? 'http://localhost:8081';

test.describe('KronFlow landing visual smoke', () => {
  test('landing renders and points to app auth routes', async ({ page }) => {
    await page.goto(baseUrl);
    await expect(page.getByRole('heading', { name: /smart conversations/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /iniciar sesi[oó]n/i })).toHaveAttribute('href', `${appUrl}/login`);
    await expect(page.getByRole('link', { name: /explorar funciones/i }).first()).toHaveAttribute('href', '#platform');
    await expect(page.locator('html')).toHaveClass(/dark/);
    await page.screenshot({ path: 'visual-test-results/landing-dark.png', fullPage: true });

    await page.getByRole('button', { name: /activar modo claro/i }).click();
    await expect(page.locator('html')).not.toHaveClass(/dark/);
    await page.screenshot({ path: 'visual-test-results/landing.png', fullPage: true });
  });
});
