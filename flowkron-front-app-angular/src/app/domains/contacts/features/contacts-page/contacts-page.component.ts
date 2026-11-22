import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Contact, ContactsApiService } from '@domains/contacts/data-access/contacts-api.service';
import { PaginatedResponse } from '@shared/types/api.types';
import { BehaviorSubject, catchError, map, of, startWith, switchMap } from 'rxjs';

type DirectoryState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; page: PaginatedResponse<Contact> };

@Component({
  selector: 'flowkron-contacts-page',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './contacts-page.component.html',
  styleUrl: './contacts-page.component.css'
})
export class ContactsPageComponent {
  private readonly contacts = inject(ContactsApiService);
  private readonly request = new BehaviorSubject({ query: '', offset: 0 });

  readonly directory = toSignal(this.request.pipe(
    switchMap(({ query, offset }) => this.contacts.list(query, 25, offset).pipe(
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

  search(query: string): void {
    this.request.next({ query: query.trim(), offset: 0 });
  }

  loadPage(offset: number): void {
    this.request.next({ query: this.request.value.query, offset });
  }

  retry(): void {
    this.request.next(this.request.value);
  }
}
