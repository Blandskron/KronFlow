import { DatePipe, Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterLink } from '@angular/router';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { Contact, ContactsApiService } from '@domains/contacts/data-access/contacts-api.service';
import { PaginatedResponse } from '@shared/types/api.types';
import { EmptyStateComponent, PageHeaderComponent, SkeletonComponent } from '@shared/ui';
import { Subject, catchError, combineLatest, distinctUntilChanged, filter, map, of, shareReplay, startWith, switchMap } from 'rxjs';

type DirectoryState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; page: PaginatedResponse<Contact> };

@Component({
  selector: 'kronflow-contacts-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, EmptyStateComponent, PageHeaderComponent, SkeletonComponent],
  templateUrl: './contacts-page.component.html',
  styleUrl: './contacts-page.component.css'
})
export class ContactsPageComponent {
  private readonly contacts = inject(ContactsApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly location = inject(Location);
  private readonly refresh = new Subject<void>();
  readonly auth = inject(AuthService);

  private readonly filters$ = this.router.events.pipe(
    filter((event) => event instanceof NavigationEnd),
    startWith(null),
    map(() => {
      const params = this.route.snapshot.queryParamMap;
      const offset = Number(params.get('offset'));
      const state = this.location.getState() as { contactSearch?: unknown } | null;
      return {
        query: typeof state?.contactSearch === 'string' ? state.contactSearch.slice(0, 120) : '',
        source: (params.get('source') ?? '').slice(0, 120),
        offset: Number.isSafeInteger(offset) && offset >= 0 ? offset : 0
      };
    }),
    distinctUntilChanged((a, b) => a.query === b.query && a.source === b.source && a.offset === b.offset),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  readonly filters = toSignal(this.filters$, { requireSync: true });
  readonly sources = toSignal(this.contacts.sources().pipe(catchError(() => of([]))), { initialValue: [] });

  readonly directory = toSignal(combineLatest([this.filters$, this.refresh.pipe(startWith(undefined))]).pipe(
    switchMap(([{ query, source, offset }]) => this.contacts.list(query, source, 25, offset).pipe(
      map((page): DirectoryState => ({ status: 'ready', page })),
      catchError((error: HttpErrorResponse) => of<DirectoryState>({
        status: 'error',
        message: error.status === 403
          ? 'No tienes permiso para consultar los contactos de esta empresa.'
          : 'No pudimos consultar los contactos.'
      })),
      startWith<DirectoryState>({ status: 'loading' })
    ))
  ), { requireSync: true });

  search(query: string, source: string): void {
    this.navigate(query.trim(), source.trim(), 0);
  }

  loadPage(offset: number): void {
    const { query, source } = this.filters();
    this.navigate(query, source, Math.max(0, offset));
  }

  retry(): void {
    this.refresh.next();
  }

  private navigate(query: string, source: string, offset: number): void {
    const current = this.filters();
    if (current.query === query && current.source === source && current.offset === offset) {
      this.retry();
      return;
    }
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { source: source || null, offset: offset || null },
      state: { contactSearch: query },
      onSameUrlNavigation: 'reload'
    });
  }
}
