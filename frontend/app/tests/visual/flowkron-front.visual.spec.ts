import { expect, test } from '@playwright/test';

const baseUrl = process.env['BASE_URL'] ?? 'http://127.0.0.1:8081';

test.describe('Flowkron app visual smoke', () => {
  test('contact activity opens leads and saves changes with the expected versions', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const timestamp = '2026-01-01T12:00:00Z';
    let fullName = 'Contacto inicial';
    let stage = 'nuevo';
    let detailUnavailable = true;
    let relatedUnavailable = true;
    let renameConflict = true;
    let conversationReads = 0;
    const patches: unknown[] = [];
    const leadFilters: string[] = [];
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type',
        'Access-Control-Allow-Methods': 'GET, PATCH, OPTIONS'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) return respond({
        user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
        tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
        permissions: ['users.read', 'crm.manage'], roles: [], subscription: null
      });
      if (url.pathname.endsWith('/contacts/1')) {
        if (request.method() === 'PATCH') {
          const data = request.postDataJSON();
          patches.push(data);
          if (renameConflict) {
            renameConflict = false;
            fullName = 'Contacto editado por otro usuario';
            return route.fulfill({ status: 409, headers });
          }
          fullName = data.full_name;
        } else if (detailUnavailable) {
          detailUnavailable = false;
          return route.fulfill({ status: 503, headers });
        }
        return respond({ id: 1, full_name: fullName, email: null, phone: '9 1234 5678', source: 'web', created_at: timestamp });
      }
      const lead = () => ({ id: 2, full_name: fullName, lifecycle_status: stage, updated_at: timestamp });
      if (url.pathname.endsWith('/leads/2') && request.method() === 'PATCH') {
        const data = request.postDataJSON();
        patches.push(data);
        stage = data.lifecycle_status;
        return respond(lead());
      }
      if (url.pathname.endsWith('/leads')) {
        leadFilters.push(url.search);
        if (relatedUnavailable) {
          relatedUnavailable = false;
          return route.fulfill({ status: 503, headers });
        }
        return respond({ items: [lead()], total: 1, limit: Number(url.searchParams.get('limit')), offset: 0 });
      }
      if (url.pathname.endsWith('/conversations')) {
        conversationReads++;
        return respond({
          items: [{
            id: 3, lead_name: fullName, last_message_at: timestamp, updated_at: timestamp,
            channel: 'whatsapp', status: 'new', no_leidos: 0
          }], total: 7, limit: 5, offset: 0
        });
      }
      return route.fulfill({ status: 404, headers });
    });

    await page.goto(`${baseUrl}/app/contacts/1`);
    await expect(page.getByRole('alert')).toHaveText('No pudimos consultar este contacto.');
    await page.getByRole('button', { name: 'Reintentar', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Contacto inicial' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('9 1234 5678', { exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Conversaciones vinculadas' })
      .locator('a[href="/app/conversations?conversation=3"]')).toBeVisible();
    await page.getByRole('button', { name: 'Reintentar leads' }).click();
    await expect(page.getByText('Lead #2 · Nuevo')).toBeVisible();
    expect(conversationReads).toBe(1);
    await page.getByRole('textbox', { name: 'Nombre del contacto' }).fill('Contacto actualizado');
    await page.getByRole('button', { name: 'Guardar nombre' }).click();
    await expect(page.getByRole('alert')).toContainText('El nombre cambió en otra sesión.');
    await expect(page.getByRole('button', { name: 'Guardar nombre' })).toBeDisabled();
    await page.getByRole('button', { name: 'Recargar ficha' }).click();
    await expect(page.getByRole('textbox', { name: 'Nombre del contacto' })).toHaveValue('Contacto editado por otro usuario');
    await page.getByRole('textbox', { name: 'Nombre del contacto' }).fill('Contacto actualizado');
    await page.getByRole('button', { name: 'Guardar nombre' }).click();
    await expect(page.getByRole('heading', { name: 'Contacto actualizado' })).toBeVisible();
    await page.getByRole('link', { name: 'Ver seguimiento de leads' }).click();
    await expect(page.getByRole('heading', { name: 'Seguimiento de leads' })).toBeVisible();
    await page.getByRole('combobox', { name: 'Estado' }).selectOption('open');
    await page.getByRole('searchbox', { name: 'Buscar lead' }).fill('actualizado');
    await page.getByRole('button', { name: 'Buscar', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Contacto actualizado' })).toBeVisible();
    await page.getByRole('combobox', { name: 'Etapa' }).selectOption('contactado');
    await page.getByRole('button', { name: 'Guardar etapa' }).click();
    await expect(page.getByText('Etapa guardada.')).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Etapa' })).toHaveValue('contactado');
    expect(patches).toEqual([
      { full_name: 'Contacto actualizado', expected_full_name: 'Contacto inicial' },
      { full_name: 'Contacto actualizado', expected_full_name: 'Contacto editado por otro usuario' },
      { lifecycle_status: 'contactado', expected_updated_at: timestamp }
    ]);
    expect(leadFilters.some((params) => ['contact_id=1', 'q=actualizado', 'status_group=open'].every((part) => params.includes(part)))).toBe(true);
    await page.getByRole('link', { name: 'Volver a la ficha' }).click();
    await page.getByRole('link', { name: 'Ver todas las conversaciones' }).click();
    await expect(page).toHaveURL(/\/conversations\?contact_id=1$/);
    await page.getByRole('button', { name: 'Ver todos los contactos' }).click();
    await expect(page).toHaveURL(/\/conversations$/);
  });

  test('lead filters survive navigation and stage conflicts recover the latest page', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const initialVersion = '2026-01-01T12:00:00Z';
    const newerVersion = '2026-01-01T12:01:00Z';
    let listUnavailable = true;
    let stage = 'nuevo';
    let version = initialVersion;
    const patches: unknown[] = [];
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type',
        'Access-Control-Allow-Methods': 'GET, PATCH, OPTIONS'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) return respond({
        user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
        tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
        permissions: ['users.read', 'crm.manage'], roles: [], subscription: null
      });
      const lastLead = () => ({ id: 26, full_name: 'Lead página dos', lifecycle_status: stage, updated_at: version });
      if (url.pathname.endsWith('/leads/26') && request.method() === 'PATCH') {
        patches.push(request.postDataJSON());
        if (version === initialVersion) {
          stage = 'contactado';
          version = newerVersion;
          return route.fulfill({ status: 409, headers });
        }
        stage = request.postDataJSON().lifecycle_status;
        return respond(lastLead());
      }
      if (!url.pathname.endsWith('/leads')) return route.fulfill({ status: 404, headers });
      if (listUnavailable) {
        listUnavailable = false;
        return route.fulfill({ status: 503, headers });
      }
      if (!url.searchParams.has('contact_id')) return route.fulfill({ status: 403, headers });
      const offset = Number(url.searchParams.get('offset'));
      const query = url.searchParams.get('q');
      const total = query ? 1 : stage === 'ganado' ? 25 : 26;
      const firstLead = { id: 1, full_name: query ? 'Coincidencia sintética' : 'Lead página uno',
        lifecycle_status: 'nuevo', updated_at: initialVersion };
      const items = offset === 0 ? [firstLead] : offset < total ? [lastLead()] : [];
      return respond({ items, total, limit: 25, offset });
    });

    const secondPage = /\/leads\?contact_id=7&status_group=open&offset=25$/;
    const firstPage = /\/leads\?contact_id=7&status_group=open$/;
    await page.goto(`${baseUrl}/app/leads?contact_id=7&status_group=open&offset=25`);
    await expect(page.getByRole('alert')).toHaveText('No pudimos consultar los leads.');
    await page.getByRole('button', { name: 'Reintentar' }).click();
    await expect(page.getByRole('heading', { name: 'Lead página dos' })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Estado' })).toHaveValue('open');
    await page.getByRole('searchbox').fill('coincidencia privada');
    await page.getByRole('searchbox').press('Enter');
    await expect(page.getByRole('heading', { name: 'Coincidencia sintética' })).toBeVisible();
    await expect(page).toHaveURL(firstPage);
    await page.reload();
    await expect(page.getByRole('searchbox')).toHaveValue('coincidencia privada');
    await page.goBack();
    await expect(page).toHaveURL(secondPage);
    await expect(page.getByRole('searchbox')).toHaveValue('');

    const stageControl = page.getByRole('combobox', { name: 'Etapa' });
    await stageControl.selectOption('ganado');
    await page.getByRole('button', { name: 'Guardar etapa' }).click();
    await expect(page.getByRole('alert')).toContainText('El lead cambió en otra sesión.');
    await expect(stageControl).toHaveValue('contactado');
    expect(patches).toEqual([{ lifecycle_status: 'ganado', expected_updated_at: initialVersion }]);

    await stageControl.selectOption('ganado');
    await page.getByRole('button', { name: 'Guardar etapa' }).click();
    await expect(page.getByText('Etapa guardada.')).toBeVisible();
    await expect(page).toHaveURL(firstPage);
    await expect(page.getByRole('heading', { name: 'Lead página uno' })).toBeVisible();
    expect(patches[1]).toEqual({ lifecycle_status: 'ganado', expected_updated_at: newerVersion });

    await page.getByRole('button', { name: 'Quitar filtro de contacto' }).click();
    await expect(page).toHaveURL(/\/leads\?status_group=open$/);
    await expect(page.getByRole('alert')).toHaveText('No tienes permiso para consultar los leads de esta empresa.');
    await page.goBack();
    await expect(page).toHaveURL(firstPage);
    await expect(page.getByRole('link', { name: 'Volver a la ficha' })).toHaveAttribute('href', '/app/contacts/7');
  });

  test('contacts directory filters, restores navigation and opens contact details', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const requests: { q: string | null; source: string | null; offset: string | null }[] = [];
    const contact = {
      id: 1, email: 'Contact+web@EXAMPLE.TEST', phone: '+56 9 1234 5678', source: 'web', created_at: '2026-01-01T12:00:00Z'
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
      if (url.pathname.endsWith('/contacts/1')) return respond({
        ...contact, full_name: 'Contacto buscado', normalized_email: 'Contact+web@example.test', normalized_phone: '+56912345678'
      });
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
    await expect(page.getByText('Contact+web@example.test', { exact: true })).toBeVisible();
    await expect(page.getByText('+56912345678', { exact: true })).toBeVisible();
    await page.getByRole('link', { name: 'Volver a Contactos' }).click();
    await expect(page.getByRole('searchbox')).toHaveValue('Buscado');
    await expect(page.getByRole('link', { name: 'Contacto buscado' })).toBeVisible();
  });

  test('manual contacts can retry an uncertain create and recover changed contact data', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const createdAt = '2026-01-01T12:00:00Z';
    const name = 'Contacto de prueba manual';
    let email: string | null = 'Alpha@example.test';
    let phone = '+56912345678';
    let contactExists = false;
    let otherTab = true;
    const requests: unknown[] = [];
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type',
        'Access-Control-Allow-Methods': 'GET, POST, PATCH, OPTIONS'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) return respond({
        user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
        tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
        permissions: ['users.read', 'crm.manage'], roles: [], subscription: null
      });
      const contact = () => ({ id: 7, full_name: name, email, phone, normalized_email: email, normalized_phone: phone,
        source: 'crm_manual', created_at: createdAt });
      if (url.pathname.endsWith('/contacts/sources')) return respond(['crm_manual']);
      if (url.pathname.endsWith('/contacts')) {
        if (request.method() === 'POST') {
          const draft = request.postDataJSON();
          requests.push(draft);
          if (draft.phone === '912345678') return route.fulfill({ status: 422, headers });
          if (!contactExists) {
            contactExists = true;
            return route.fulfill({ status: 503, headers });
          }
          return respond({ created: false, contact: contact() });
        }
        return respond({ items: contactExists ? [contact()] : [], total: contactExists ? 1 : 0, limit: 25, offset: 0 });
      }
      if (url.pathname.endsWith('/contacts/7/points')) {
        const draft = request.postDataJSON();
        requests.push(draft);
        if (otherTab) {
          otherTab = false;
          phone = '+56900000000';
          return route.fulfill({ status: 409, headers });
        }
        email = draft.email;
        phone = draft.phone;
        return respond(contact());
      }
      if (url.pathname.endsWith('/contacts/7')) return respond(contact());
      if (url.pathname.endsWith('/leads') || url.pathname.endsWith('/conversations')) {
        return respond({ items: [], total: 0, limit: 5, offset: 0 });
      }
      return route.fulfill({ status: 404, headers });
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${baseUrl}/app/contacts?source=crm_manual`);
    await page.getByRole('link', { name: 'Nuevo contacto' }).click();
    await page.getByRole('textbox', { name: 'Nombre', exact: true }).fill(name);
    await page.getByRole('textbox', { name: 'Correo electrónico (opcional)' }).fill('Alpha@EXAMPLE.TEST');
    const newPhone = page.getByRole('textbox', { name: 'Teléfono (opcional)' });
    await newPhone.fill('912345678');
    await page.getByRole('button', { name: 'Crear contacto' }).click();
    await expect(page.getByRole('alert')).toContainText('prefijo internacional');
    await newPhone.fill('+56 9 1234 5678');
    await page.getByRole('button', { name: 'Crear contacto' }).click();
    await expect(page.getByRole('alert')).toContainText('No pudimos confirmar el alta');
    await expect(newPhone).toHaveAttribute('readonly', '');
    await page.getByRole('button', { name: 'Reintentar alta' }).click();
    await expect(page).toHaveURL(/\/contacts\/7\?source=crm_manual$/);
    await expect(page.getByRole('heading', { name })).toBeVisible();
    expect(requests[1]).toEqual(requests[2]);

    const emailInput = page.getByRole('textbox', { name: 'Correo del contacto' });
    await emailInput.fill('');
    await page.getByRole('button', { name: 'Guardar datos de contacto' }).click();
    await expect(page.getByRole('alert')).toContainText('Los datos cambiaron en otra sesión');
    await expect(page.getByRole('button', { name: 'Guardar datos de contacto' })).toBeDisabled();
    await page.getByRole('button', { name: 'Recargar datos de contacto' }).click();
    await expect(page.getByRole('textbox', { name: 'Teléfono del contacto' })).toHaveValue('+56900000000');
    await emailInput.fill('');
    await page.getByRole('button', { name: 'Guardar datos de contacto' }).click();
    await expect(page.getByText('Datos de contacto guardados.')).toBeVisible();
    await expect(page.getByText('Sin correo', { exact: true })).toBeVisible();
    expect(requests[4]).toEqual({ email: null, phone: '+56900000000', expected_email: 'Alpha@example.test', expected_phone: '+56900000000' });
    await expect(page.getByRole('button', { name: 'Iniciar seguimiento' })).toBeVisible();
    await page.getByRole('link', { name: 'Volver a Contactos' }).click();
    await expect(page).toHaveURL(/\/contacts\?source=crm_manual$/);
    await expect(page.getByRole('link', { name })).toBeVisible();
  });

  test('manual lead workflow starts from a contact and preserves qualification history', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const name = 'Contacto QA sin lead';
    const createdAt = '2026-01-01T12:00:00Z';
    const version2 = '2026-01-01T12:01:00Z';
    const version3 = '2026-01-01T12:02:00Z';
    let permissions = ['users.read', 'crm.manage', 'audit.read'];
    let started = false;
    let stage = 'nuevo';
    let temperature = 'cold';
    let version = createdAt;
    let historyReads = 0;
    let historyUnavailable = true;
    const patches: unknown[] = [];
    const events = [{ id: 1, kind: 'created', created_at: createdAt, previous: null as string | null, value: null as string | null }];
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type',
        'Access-Control-Allow-Methods': 'GET, POST, PATCH, OPTIONS'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) return respond({
        user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
        tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
        permissions, roles: [], subscription: null
      });
      if (url.pathname.endsWith('/contacts/1')) return respond({ id: 1, full_name: name, email: 'qa@example.test',
        phone: null, source: 'qa_manual', created_at: createdAt });
      const lead = () => ({ id: 2, contact_id: 1, full_name: name, email: 'qa@example.test', phone: '', source: 'qa_manual',
        lifecycle_status: stage, temperature, score: 0, updated_at: version });
      if (url.pathname.endsWith('/contacts/1/lead') && request.method() === 'POST') {
        const created = !started;
        started = true;
        return respond({ created, lead: lead() });
      }
      if (url.pathname.endsWith('/leads/2/activity')) {
        historyReads++;
        if (historyUnavailable) {
          historyUnavailable = false;
          return route.fulfill({ status: 503, headers });
        }
        return respond(events);
      }
      if (url.pathname.endsWith('/leads/2')) {
        if (request.method() === 'PATCH') {
          const change = request.postDataJSON();
          patches.push(change);
          if (version === createdAt) {
            stage = 'en_proceso';
            version = version2;
            return route.fulfill({ status: 409, headers });
          }
          stage = change.lifecycle_status ?? stage;
          temperature = change.temperature ?? temperature;
          version = version3;
          events.unshift({ id: 2, kind: 'temperature', created_at: version3, previous: 'cold', value: temperature });
        }
        return respond(lead());
      }
      if (url.pathname.endsWith('/leads')) {
        const matches = started && (!url.searchParams.has('temperature') || url.searchParams.get('temperature') === temperature);
        return respond({ items: matches ? [lead()] : [], total: matches ? 1 : 0, limit: 25, offset: 0 });
      }
      if (url.pathname.endsWith('/conversations')) return respond({ items: [], total: 0, limit: 5, offset: 0 });
      return route.fulfill({ status: 404, headers });
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${baseUrl}/app/contacts/1`);
    await page.getByRole('button', { name: 'Iniciar seguimiento' }).click();
    await expect(page).toHaveURL(/\/app\/leads\/2$/);
    await expect(page.getByRole('heading', { name })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Abrir ficha del contacto' })).toHaveAttribute('href', '/app/contacts/1');
    await page.getByRole('button', { name: 'Reintentar historial' }).click();
    await expect(page.getByText(/Seguimiento iniciado/)).toBeVisible();
    const stageControl = page.getByRole('combobox', { name: 'Etapa' });
    const temperatureControl = page.getByRole('combobox', { name: 'Temperatura' });
    await stageControl.selectOption('contactado');
    await page.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(page.getByRole('alert')).toContainText('El lead cambió en otra sesión.');
    await expect(stageControl).toHaveValue('en_proceso');
    await temperatureControl.selectOption('warm');
    await page.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(page.getByText('Cambios guardados.')).toBeVisible();
    await expect(page.getByText(/Temperatura: Frío → Tibio/)).toBeVisible();
    expect(patches).toEqual([
      { lifecycle_status: 'contactado', expected_updated_at: createdAt },
      { temperature: 'warm', expected_updated_at: version2 }
    ]);

    await page.getByRole('link', { name: 'Volver a seguimiento' }).click();
    await page.getByRole('searchbox').fill('QA sin lead');
    await page.getByRole('combobox', { name: 'Temperatura' }).selectOption('warm');
    await page.getByRole('button', { name: 'Buscar', exact: true }).click();
    await expect(page).toHaveURL(/\/app\/leads\?temperature=warm$/);
    await page.getByRole('link', { name }).click();
    await expect(page).toHaveURL(/\/app\/leads\/2\?temperature=warm$/);
    await page.getByRole('link', { name: 'Volver a seguimiento' }).click();
    await expect(page.getByRole('searchbox')).toHaveValue('QA sin lead');

    permissions = ['users.read'];
    const historyBeforeViewer = historyReads;
    await page.goto(`${baseUrl}/app/leads/2`);
    await expect(page.getByRole('heading', { name })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Guardar cambios' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Historial del lead' })).toHaveCount(0);
    expect(historyReads).toBe(historyBeforeViewer);
  });

  test('WhatsApp consent loads on request and paginates evidence without changing current authorization', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    let permissions = ['users.read', 'audit.read'];
    const requests: Array<string | null> = [];
    const grant = '2026-01-01T12:03:00Z';
    const withdrawal = '2026-01-01T12:02:00Z';
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type',
        'Access-Control-Allow-Methods': 'GET, OPTIONS'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) return respond({
        user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
        tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
        permissions, roles: [], subscription: null
      });
      if (url.pathname.endsWith('/contacts/12')) return respond({
        id: 12, full_name: 'Contacto sintético', email: null, phone: null, source: 'whatsapp_directo', created_at: grant
      });
      if (url.pathname.endsWith('/leads') || url.pathname.endsWith('/conversations')) {
        return respond({ items: [], limit: 5, offset: 0, total: 0 });
      }
      if (url.pathname.endsWith('/contacts/12/whatsapp-consent')) {
        const cursor = url.searchParams.get('before_id');
        requests.push(cursor);
        if (requests.length === 1) return route.fulfill({ status: 503, headers });
        const event = cursor === null
          ? { id: 30, kind: 'prior_withdrawal', accepted: null, effective_at: withdrawal, source: null }
          : { id: 20, kind: 'decision', accepted: true, effective_at: grant, source: 'whatsapp_message' };
        return respond({
          channel: 'whatsapp', state: 'granted', decision_at: grant, authorized_from: grant, policy_version: 'v1.0',
          items: [{ ...event, recorded_at: '2026-01-02T12:00:00Z', policy_version: null }],
          next_before_id: cursor === null ? 30 : null
        });
      }
      return route.fulfill({ status: 404, headers });
    });

    await page.goto(`${baseUrl}/app/contacts/12`);
    const open = page.getByRole('button', { name: 'Consultar consentimiento' });
    await expect(open).toBeVisible();
    expect(requests).toEqual([]);
    await open.click();
    await expect(page.getByRole('alert')).toContainText('No pudimos consultar el consentimiento');
    await page.getByRole('button', { name: 'Reintentar consulta' }).click();
    await expect(page.getByText('Baja de un periodo anterior')).toBeVisible();
    await expect(page.getByText('Autorización vigente', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Ver eventos anteriores' }).click();
    await expect(page.getByText('Autorización registrada')).toBeVisible();
    await expect(page.getByText('Autorización vigente', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Más recientes' }).click();
    await expect(page.getByText('Baja de un periodo anterior')).toBeVisible();
    expect(requests).toEqual([null, null, '30', null]);

    permissions = ['users.read'];
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Contacto sintético' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Consentimiento de WhatsApp' })).toHaveCount(0);
    expect(requests).toHaveLength(4);
  });

  test('notifications separates live pending work from persistent handoff history', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const date = '2026-01-01T12:00:00Z';
    let failHistory = true;
    let denyPending = false;
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) return respond({
        user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
        tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
        permissions: ['users.read'], roles: [], subscription: null
      });
      if (url.pathname.endsWith('/conversations/handoff-history')) {
        if (failHistory) {
          failHistory = false;
          return route.fulfill({ status: 503, headers });
        }
        if (url.searchParams.get('before_id') === '40') return respond({
          items: [{ id: 39, kind: 'inbound_handoff', occurred_at: date, contact_name: null, lead_id: null, conversation_id: null }],
          next_before_id: null
        });
        return respond({
          items: [
            { id: 41, kind: 'whatsapp_turn', occurred_at: date, contact_name: 'Conversación histórica', lead_id: 10, conversation_id: 5 },
            { id: 40, kind: 'inbound_handoff', occurred_at: date, contact_name: 'Lead histórico', lead_id: 11, conversation_id: null }
          ], next_before_id: 40
        });
      }
      if (url.pathname.endsWith('/conversations')) {
        if (denyPending) return route.fulfill({ status: 403, headers });
        expect(url.searchParams.get('requires_human')).toBe('true');
        const offset = Number(url.searchParams.get('offset'));
        return respond({
          items: [{ id: offset ? 8 : 7, lead_name: offset ? 'Pendiente de otra página' : 'Pendiente actual',
            last_message_at: date, updated_at: date }], total: 26, limit: 25, offset
        });
      }
      return route.fulfill({ status: 404, headers });
    });

    await page.setViewportSize({ width: 360, height: 780 });
    await page.goto(`${baseUrl}/app/notifications`);
    const views = page.getByRole('navigation', { name: 'Vistas de notificaciones' });
    await expect(views.getByRole('link', { name: 'Pendientes' })).toHaveAttribute('aria-current', 'page');
    await expect(page.getByRole('link', { name: 'Pendiente actual' })).toHaveAttribute('href', '/app/conversations?status=waiting&conversation=7');
    await page.getByRole('link', { name: 'Siguiente' }).click();
    await expect(page).toHaveURL(/notifications\?offset=25$/);
    await expect(page.getByRole('link', { name: 'Pendiente de otra página' })).toBeVisible();
    await page.getByRole('link', { name: 'Anterior' }).click();
    await expect(page.getByRole('link', { name: 'Pendiente actual' })).toBeVisible();

    await views.getByRole('link', { name: 'Historial' }).press('Enter');
    await expect(page.getByRole('alert')).toHaveText('No pudimos consultar las notificaciones.');
    await page.getByRole('button', { name: 'Reintentar' }).click();
    await expect(views.getByRole('link', { name: 'Historial' })).toHaveAttribute('aria-current', 'page');
    await expect(page.getByRole('link', { name: 'Abrir conversación' })).toHaveAttribute('href', '/app/conversations?conversation=5');
    await expect(page.getByRole('link', { name: 'Abrir lead' })).toHaveAttribute('href', '/app/leads/11');
    await page.getByRole('link', { name: 'Ver anteriores' }).click();
    await expect(page).toHaveURL(/notifications\?view=history&before_id=40$/);
    await page.reload();
    await expect(page.getByText('Registro vinculado no disponible')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Abrir lead' })).toHaveCount(0);
    await page.getByRole('link', { name: 'Más recientes' }).click();
    await expect(page.getByText('Conversación histórica')).toBeVisible();

    denyPending = true;
    await views.getByRole('link', { name: 'Pendientes' }).click();
    await expect(page.getByRole('alert')).toContainText('No tienes permiso');
    await expect(page.getByRole('button', { name: 'Reintentar' })).toHaveCount(0);
  });

  test('audit history filters opaque correlations and keeps navigation scoped to the active filters', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const correlation = '0d79c43a-9916-4a49-8354-eb2445481d72';
    const date = '2026-11-23T12:00:00Z';
    let hasPermission = true;
    let reads = 0;
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) return respond({
        user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
        tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
        permissions: hasPermission ? ['audit.read'] : [], roles: [], subscription: null
      });
      if (url.pathname.endsWith('/audit-events')) {
        reads++;
        const requested = url.searchParams.get('correlation_id');
        const before = url.searchParams.get('before_id');
        const eventType = url.searchParams.get('event_type');
        if (requested) expect(requested).toBe(correlation);
        if (before) expect(eventType).toBe('lead.stage.changed');
        return respond({
          items: [{ event_id: before ? 'operational:19' : 'operational:20', event_type: 'lead.stage.changed', occurred_at: date,
            correlation_id: before ? 'operational:19' : correlation, data: { lead_id: 7, previous_stage: 'nuevo', stage: 'contactado' } }],
          next_before_id: before || requested ? null : 20
        });
      }
      return route.fulfill({ status: 404, headers });
    });

    await page.goto(`${baseUrl}/app/settings/audit-events`);
    await expect(page.getByRole('heading', { name: 'Cambio de etapa' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Abrir lead' })).toHaveAttribute('href', '/app/leads/7');
    await page.getByRole('combobox', { name: 'Evento' }).selectOption('lead.stage.changed');
    await page.getByRole('button', { name: 'Aplicar filtros' }).click();
    await page.getByRole('link', { name: 'Ver anteriores' }).click();
    await expect(page).toHaveURL(/event_type=lead.stage.changed&before_id=20$/);
    await expect(page.getByText('Sin correlación HTTP registrada')).toBeVisible();
    await page.getByRole('link', { name: 'Más recientes' }).click();
    await page.getByRole('textbox', { name: 'ID de correlación' }).fill(correlation);
    await page.getByRole('button', { name: 'Aplicar filtros' }).click();
    await expect(page).toHaveURL(new RegExp(`correlation_id=${correlation}$`));
    await expect(page.getByRole('link', { name: 'Ver anteriores' })).toHaveCount(0);

    hasPermission = false;
    const previousReads = reads;
    await page.reload();
    await expect(page.getByRole('alert')).toContainText('No tienes permiso');
    expect(reads).toBe(previousReads);
  });

  test('privacy requests require confirmation and expose read-only views by role', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    let permissions = ['users.read', 'audit.read', 'crm.manage'];
    let state = 'pendiente';
    const changes: unknown[] = [];
    const requestedAt = '2026-11-01T12:00:00Z';
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type',
        'Access-Control-Allow-Methods': 'GET, PATCH, OPTIONS'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) return respond({
        user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
        tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
        permissions, roles: [], subscription: null
      });
      const entry = () => ({ id: 1, kind: 'acceso', state, requested_at: requestedAt, due_at: '2026-12-01T12:00:00Z',
        completed_at: state === 'completada' ? '2026-11-23T12:00:00Z' : null });
      if (url.pathname.endsWith('/privacy-cases/1') && request.method() === 'PATCH') {
        const change = request.postDataJSON();
        changes.push(change);
        state = change.state;
        return respond(entry());
      }
      if (url.pathname.endsWith('/privacy-cases')) {
        const filter = url.searchParams.get('state');
        const items = !filter || filter === state ? [entry()] : [];
        return respond({ items, total: items.length, limit: 25, offset: 0 });
      }
      return route.fulfill({ status: 404, headers });
    });

    await page.goto(`${baseUrl}/app/settings/privacy`);
    await expect(page.getByRole('heading', { name: 'Solicitud #1 · Acceso' })).toBeVisible();
    await page.getByRole('button', { name: 'Iniciar revisión' }).click();
    await expect(page.getByText('No hay solicitudes para este filtro.')).toBeVisible();
    await page.getByRole('combobox', { name: 'Estado' }).selectOption('en_proceso');
    await page.getByRole('button', { name: 'Aplicar filtro' }).click();
    const close = page.getByRole('button', { name: 'Registrar cierre' });
    await close.click();
    expect(changes).toEqual([{ expected_state: 'pendiente', state: 'en_proceso', confirmed: false }]);
    await page.getByRole('checkbox', { name: 'Confirmo que la solicitud fue atendida' }).check();
    await close.click();
    await expect(page.getByText('No hay solicitudes para este filtro.')).toBeVisible();
    await page.getByRole('combobox', { name: 'Estado' }).selectOption('completada');
    await page.getByRole('button', { name: 'Aplicar filtro' }).click();
    await expect(page.getByText(/Cierre registrado/)).toBeVisible();
    expect(changes[1]).toEqual({ expected_state: 'en_proceso', state: 'completada', confirmed: true });

    state = 'pendiente';
    permissions = ['users.read', 'audit.read'];
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Solicitud #1 · Acceso' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Iniciar revisión' })).toHaveCount(0);
  });

  test('analytics separates zero activity, partial days and invalid filters', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('flowkron.access_token', 'synthetic-test-session');
      localStorage.setItem('flowkron.tenant_id', '1');
    });
    const dates = ['2026-10-01', '2026-10-02'];
    const zero = { contacts_created: 0, leads_created: 0, inbound_messages: 0, outbound_messages: 0 };
    let filters: Record<string, string> = {};
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url());
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, x-tenant-id, x-correlation-id, content-type'
      };
      const respond = (data: object) => route.fulfill({ headers, json: { success: true, data } });
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      if (url.pathname.endsWith('/auth/me/')) return respond({
        user: { id: 1, email: 'operator@example.test', first_name: 'Operador' },
        tenant: { id: 1, name: 'Empresa sintética', status: 'active', slug: 'test' },
        permissions: ['users.read'], roles: [], subscription: null
      });
      if (url.pathname.endsWith('/analytics/summary')) return respond({
        total_leads: 0, cold_leads: 0, warm_leads: 0, hot_leads: 0, open_conversations: 0,
        requires_human: 0, messages_today: 0, messages_last_7_days: 0
      });
      if (url.pathname.endsWith('/analytics/activity')) {
        filters = Object.fromEntries(url.searchParams);
        if (filters.time_zone === 'Invalid/Zone') return route.fulfill({ status: 422, headers });
        const custom = filters.start_date === dates[0];
        return respond({
          ...filters, as_of: '2026-10-02T15:00:00Z', partial_day: custom ? null : filters.end_date,
          totals: zero, days: (custom ? dates : [filters.start_date]).map((day) => ({ day, ...zero }))
        });
      }
      return route.fulfill({ status: 404, headers });
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${baseUrl}/app/analytics`);
    await expect(page.getByRole('heading', { name: 'Leads por temperatura' })).toBeVisible();
    await expect(page.getByText('Sin base', { exact: true })).toHaveCount(3);
    await expect(page.getByText(/Día parcial/)).toBeVisible();
    const table = page.getByRole('table');
    await expect(table.getByRole('row', { name: 'Total del intervalo 0 0 0 0' })).toBeVisible();

    await page.getByLabel('Desde', { exact: true }).fill(dates[0]);
    await page.getByLabel('Hasta', { exact: true }).fill(dates[1]);
    const zone = page.getByRole('textbox', { name: 'Zona horaria' });
    await zone.fill('Invalid/Zone');
    await page.getByRole('button', { name: 'Consultar actividad' }).click();
    await expect(page.getByRole('alert')).toContainText('Revisa la zona horaria y el intervalo.');
    await expect(table).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Leads por temperatura' })).toBeVisible();
    await zone.fill('America/Santiago');
    await zone.press('Enter');
    await expect(table.getByRole('row', { name: `${dates[1]} 0 0 0 0` })).toBeVisible();
    await expect(page.getByText(/Día parcial/)).toHaveCount(0);
    expect(filters).toEqual({ start_date: dates[0], end_date: dates[1], time_zone: 'America/Santiago' });
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
        if (url.searchParams.get('requires_human') === 'true') return respond({ items: [pending], total: 26, limit: 25, offset: 0 });
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
    await page.getByRole('link', { name: 'Ver pendientes en Bandeja' }).click();
    await expect(page).toHaveURL(/\/conversations\?status=waiting$/);
    await expect(page.getByRole('button', { name: 'Necesitan atención' })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: /Contacto antiguo/ })).toBeVisible();
  });
});
