import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from '@core/config/api.config';
import { AuthService } from './auth-api.service';

describe('AuthService MFA enrollment', () => {
  it('calls MFA setup and confirm endpoints cleanly', () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });
    const service = TestBed.inject(AuthService);
    const httpMock = TestBed.inject(HttpTestingController);

    let setupResult: { secret: string; otpauth_uri: string } | undefined;
    service.setupMfa().subscribe((res) => (setupResult = res));
    const setupReq = httpMock.expectOne(`${API_BASE_URL}/auth/mfa/setup/`);
    expect(setupReq.request.method).toBe('POST');
    setupReq.flush({ data: { secret: 'JBSWY3DPEHPK3PXP', otpauth_uri: 'otpauth://totp/KronFlow?secret=JBSWY3DPEHPK3PXP' } });
    expect(setupResult?.secret).toBe('JBSWY3DPEHPK3PXP');

    let confirmResult: { confirmed: boolean; recovery_codes: string[] } | undefined;
    service.confirmMfa('123456').subscribe((res) => (confirmResult = res));
    const confirmReq = httpMock.expectOne(`${API_BASE_URL}/auth/mfa/confirm/`);
    expect(confirmReq.request.method).toBe('POST');
    expect(confirmReq.request.body).toEqual({ code: '123456' });
    confirmReq.flush({ data: { confirmed: true, recovery_codes: ['REC-1', 'REC-2'] } });
    expect(confirmResult?.confirmed).toBe(true);
    expect(confirmResult?.recovery_codes).toEqual(['REC-1', 'REC-2']);

    httpMock.verify();
  });
});
