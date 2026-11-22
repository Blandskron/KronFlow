import { expect, test } from '@playwright/test';

const baseUrl = process.env['BASE_URL'] ?? 'http://127.0.0.1:8081';

test.describe('Flowkron app visual smoke', () => {
  test('contacts directory filters, restores navigation and opens contact details', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const requests: { q: string | null; source: string | null; offset: string | null }[] = [];
    const contact = {
      id: 1, email: 'contact@example.test', phone: '+56 9 1234 5678', source: 'web', created_at: '2026-01-01T12:00:00Z'
    };
    let fail = true;
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type',
        'Access-Control-Allow-Methods': 'GET, OPTIONS'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) {
        return respond({
          user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
          tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
          permissions: ['users.read'], roles: [], subscription: null
        });
      }
      if (url.pathname.endsWith('/contacts/sources')) return respond(['web', 'whatsapp_directo']);
      if (url.pathname.endsWith('/contacts/1')) return respond({ ...contact, full_name: 'Contacto buscado' });
      if (!url.pathname.endsWith('/contacts')) return route.fulfill({ status: 404, headers });
      const q = url.searchParams.get('q');
      const source = url.searchParams.get('source');
      const offset = url.searchParams.get('offset');
      requests.push({ q, source, offset });
      if (fail) {
        fail = false;
        return route.fulfill({ status: 503, headers });
      }
      return respond({
        items: [{
          ...contact, full_name: q ? 'Contacto buscado' : offset === '25' ? 'Contacto página dos' : 'Contacto inicial'
        }],
        total: q ? 1 : 26, limit: 25, offset: Number(offset)
      });
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${baseUrl}/app/contacts`);
    await expect(page.getByRole('link', { name: 'Contactos' })).toHaveAttribute('aria-current', 'page');
    await expect(page.getByRole('alert')).toContainText('No pudimos consultar los contactos');
    await page.getByRole('button', { name: 'Reintentar' }).click();
    await expect(page.getByText('Contacto inicial')).toBeVisible();
    await page.getByRole('button', { name: 'Siguiente' }).click();
    await expect(page.getByText('Contacto página dos')).toBeVisible();
    await expect(page).toHaveURL(/\/contacts\?offset=25$/);
    await page.reload();
    await expect(page.getByText('Contacto página dos')).toBeVisible();

    await page.getByLabel('Origen', { exact: true }).fill('web');
    await page.getByRole('button', { name: 'Buscar', exact: true }).click();
    await expect(page).toHaveURL(/\/contacts\?source=web$/);
    await expect(page.getByText('Contacto inicial')).toBeVisible();

    await page.getByRole('searchbox').fill('Buscado');
    await page.getByRole('button', { name: 'Buscar', exact: true }).click();
    await expect(page.getByText('Contacto buscado')).toBeVisible();
    await expect(page).toHaveURL(/\/contacts\?source=web$/);
    expect(requests).toContainEqual({ q: null, source: null, offset: '25' });
    expect(requests).toContainEqual({ q: 'Buscado', source: 'web', offset: '0' });

    await page.getByRole('link', { name: 'Contacto buscado' }).click();
    await expect(page.getByRole('heading', { name: 'Contacto buscado' })).toBeVisible();
    await expect(page.getByText('contact@example.test', { exact: true })).toBeVisible();
    await page.getByRole('link', { name: 'Volver a Contactos' }).click();
    await expect(page.getByRole('searchbox')).toHaveValue('Buscado');
    await expect(page.getByRole('link', { name: 'Contacto buscado' })).toBeVisible();
  });

  test('login screen renders without blank screens', async ({ page }) => {
    await page.goto(baseUrl);
    await expect(page).toHaveURL(/\/login$/);

    await page.evaluate(() => localStorage.setItem('theme', 'light'));
    await page.goto(`${baseUrl}/login`);
    await expect(page.getByRole('heading', { name: 'Iniciar sesión' })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Correo electrónico' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Iniciar sesión', exact: true })).toBeVisible();
    await page.screenshot({ path: 'visual-test-results/login.png', fullPage: true });
  });

  test('WhatsApp distinguishes waiting, retry and relink, and removes expired QR images', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const at = new Date().toISOString();
    const defaults = {
      status_changed_at: at,
      retry_attempts: 0,
      retry_limit: 5,
      retry_exhausted: false
    };
    let snapshot: object = {
      status: 'disconnected',
      diagnostics: { ...defaults, next_action: 'wait', disconnect_cause: 'temporary', next_retry_at: at }
    };
    let attempts = 0;
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
      };
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) {
        return route.fulfill({ headers, json: { success: true, data: {
          user: { id: 1, email: 'operator@example.test', first_name: 'Operador', last_name: 'Prueba' },
          tenant: { id: 1, name: 'Empresa de prueba', status: 'active', slug: 'test' },
          roles: ['TENANT_OWNER'], permissions: ['whatsapp.connect'], subscription: null
        } } });
      }
      if (url.pathname.endsWith('/tenants/1/whatsapp/')) {
        if (route.request().method() === 'POST') {
          attempts++;
          snapshot = { status: 'connecting', diagnostics: { ...defaults, next_action: 'wait' } };
        }
        return route.fulfill({ headers, json: { success: true, data: snapshot } });
      }
      return route.fulfill({ status: 404, headers });
    });
    await page.goto(`${baseUrl}/app/whatsapp`);
    await expect(page.getByText('Reconexión programada', { exact: true })).toBeVisible();
    await expect(page.getByText(/Próximo intento 1 de 5/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Reintentar conexión' })).toHaveCount(0);

    snapshot = {
      status: 'disconnected',
      diagnostics: { ...defaults, next_action: 'retry', retry_attempts: 5, retry_exhausted: true }
    };
    const retry = page.getByRole('button', { name: 'Reintentar conexión' });
    await expect(retry).toBeVisible();
    await retry.click();
    await expect(page.getByText('Preparando la conexión…', { exact: true })).toBeVisible();
    expect(attempts).toBe(1);

    snapshot = {
      status: 'pairing_required',
      diagnostics: { ...defaults, next_action: 'relink', disconnect_cause: 'signed_out' }
    };
    await expect(page.getByRole('button', { name: 'Restablecer vínculo' })).toBeVisible();
    await expect(page.getByText('Se cerró la sesión en WhatsApp.')).toBeVisible();

    snapshot = {
      status: 'qr_pending',
      qr: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXfcAAAAASUVORK5CYII=',
      diagnostics: { ...defaults, next_action: 'scan', qr_expires_at: new Date(Date.now() + 4200).toISOString() }
    };
    const qr = page.getByRole('img', { name: /código QR para vincular/i });
    await expect(qr).toBeVisible();
    await expect(qr).toHaveCount(0);
    await expect(page.getByText('Esperando un código nuevo', { exact: true })).toBeVisible();
  });

  test('inbox searches and pages on the server and marks the rendered thread read', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const at = new Date().toISOString();
    const contact = (id: number, name: string, unread: number) => ({
      id, lead_name: name, channel: 'whatsapp', status: 'new', requires_human: false,
      last_message: 'Mensaje de prueba', updated_at: at, no_leidos: unread
    });
    const recent = contact(100, 'Contacto reciente', 0);
    const previous = contact(1, 'Contacto antiguo', 2);
    const listRequests: { query: string | null; before: string | null }[] = [];
    const marks: object[] = [];
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) {
        return respond({
          user: { id: 1, email: 'operator@example.test', first_name: 'Operador', last_name: 'Prueba' },
          tenant: { id: 1, name: 'Empresa de prueba', status: 'active', slug: 'test' },
          roles: ['TENANT_OWNER'], permissions: ['crm.manage'], subscription: null
        });
      }
      if (url.pathname.endsWith('/conversations')) {
        const pending = { ...previous, status: 'waiting', requires_human: true };
        if (url.searchParams.get('requires_human') === 'true') return respond({ items: [pending], total: 26 });
        if (url.searchParams.get('status') === 'waiting') return respond({ items: [pending], total: 1 });
        const query = url.searchParams.get('q');
        const before = url.searchParams.get('before_id');
        listRequests.push({ query, before });
        return respond(query || before
          ? { items: [previous], total: 1, next_cursor: null }
          : { items: [recent], total: 2, next_cursor: { before_at: at, before_id: recent.id } });
      }
      if (url.pathname.endsWith('/conversations/1/messages')) {
        const outbound = (id: number, body: string, delivery_status: string, delivery_failure_reason?: string) =>
          ({ id, body, sender_type: 'agent', sent_at: at, delivery_status, delivery_failure_reason });
        return respond({
          items: [
            outbound(205, 'Respuesta leída', 'read'),
            outbound(204, 'Respuesta entregada', 'delivered'),
            outbound(203, 'Respuesta rechazada', 'failed', 'account_restricted'),
            outbound(202, 'Respuesta histórica', 'unknown'),
            { id: 201, body: 'Mensaje visible', sender_type: 'lead', sent_at: at }
          ],
          total: 5,
          pending_replies: [{ inbound_message_id: 201, status: 'queued' }]
        });
      }
      if (url.pathname.endsWith('/conversations/1/read')) {
        marks.push(route.request().postDataJSON());
        return respond({ no_leidos: 0 });
      }
      return route.fulfill({ status: 404, headers });
    });
    await page.goto(`${baseUrl}/app/conversations`);
    await expect(page.getByText('Contacto reciente', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Ver más conversaciones' }).click();
    await expect(page.getByText('Contacto antiguo', { exact: true })).toBeVisible();
    expect(listRequests).toContainEqual({ query: null, before: '100' });

    await page.getByRole('searchbox', { name: 'Buscar conversaciones' }).fill('Contacto antiguo');
    await expect(page.getByText('Contacto reciente', { exact: true })).toHaveCount(0);
    await expect(page.getByLabel('2 mensajes sin leer')).toBeVisible();
    expect(listRequests).toContainEqual({ query: 'Contacto antiguo', before: null });
    expect(marks).toHaveLength(0);

    await page.getByRole('button', { name: /Contacto antiguo/ }).click();
    await expect(page.getByText('Mensaje visible')).toBeVisible();
    await expect(page.getByLabel('2 mensajes sin leer')).toHaveCount(0);
    expect(marks).toEqual([{ through_message_id: 205 }]);
    await expect(page.getByText('Respuesta en cola', { exact: true })).toBeVisible();
    await expect(page.getByText('Leído', { exact: true })).toBeVisible();
    await expect(page.getByText('Entregado', { exact: true })).toBeVisible();
    await expect(page.getByText('Entrega desconocida', { exact: true })).toBeVisible();
    await expect(page.getByText('WhatsApp restringió el envío desde esta cuenta.')).toBeVisible();

    await page.getByRole('link', { name: 'Notificaciones' }).click();
    await page.getByRole('link', { name: 'Ver todas las pendientes' }).click();
    await expect(page).toHaveURL(/\/conversations\?status=waiting$/);
    await expect(page.getByRole('button', { name: 'Necesitan atención' })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: /Contacto antiguo/ })).toBeVisible();
  });
});
