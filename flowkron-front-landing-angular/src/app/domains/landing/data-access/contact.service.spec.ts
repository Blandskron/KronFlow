import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '@env/environment';
import { ContactPayload, ContactService } from './contact.service';

describe('ContactService', () => {
  let service: ContactService;
  let httpMock: HttpTestingController;
  const baseUrl = environment.contactApiBaseUrl.replace(/\/$/, '');

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });

    service = TestBed.inject(ContactService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('fetches CSRF token and posts contact message with X-CSRFToken header', () => {
    const payload: ContactPayload = {
      name: 'Ada Lovelace',
      email: 'ada@example.com',
      company: 'Analytical Engine',
      phone: '+56 9 1234 5678',
      message: 'Me interesa conocer Flowkron.',
      accept_terms: true
    };

    let responseData: { id: number; created_at: string } | undefined;
    service.send(payload).subscribe((data) => (responseData = data));

    const csrfReq = httpMock.expectOne(`${baseUrl}/api/v1/contact/csrf/`);
    expect(csrfReq.request.method).toBe('GET');
    expect(csrfReq.request.withCredentials).toBe(true);
    csrfReq.flush({ success: true, data: { csrfToken: 'csrf-abc' } });

    const postReq = httpMock.expectOne(`${baseUrl}/api/v1/contact/messages/`);
    expect(postReq.request.method).toBe('POST');
    expect(postReq.request.withCredentials).toBe(true);
    expect(postReq.request.headers.get('X-CSRFToken')).toBe('csrf-abc');
    expect(postReq.request.body).toEqual(payload);
    postReq.flush({ success: true, data: { id: 101, created_at: '2026-11-23T00:00:00Z' } });

    expect(responseData).toEqual({ id: 101, created_at: '2026-11-23T00:00:00Z' });
  });
});
