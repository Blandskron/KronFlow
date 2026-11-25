import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { LucideMessageSquare } from '@lucide/angular';
import { ConversationsApiService } from '@domains/conversations/data-access/conversations-api.service';
import { Conversation, HandoffHistoryPage } from '@domains/conversations/domain/conversation.model';
import { PaginatedResponse } from '@shared/types/api.types';
import { Subject, catchError, combineLatest, distinctUntilChanged, map, of, shareReplay, startWith, switchMap } from 'rxjs';

type NotificationView = { view: 'pending'; offset: number } | { view: 'history'; beforeId?: number };
type ReadyState = { status: 'pending'; page: PaginatedResponse<Conversation> }
  | { status: 'history'; page: HandoffHistoryPage };
type NotificationState = ReadyState | { status: 'loading' } | { status: 'error'; forbidden: boolean };

function positiveInteger(value: string | null, max = Number.MAX_SAFE_INTEGER): number | undefined {
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 && id <= max ? id : undefined;
}

@Component({
  selector: 'kronflow-notifications-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, LucideMessageSquare],
  templateUrl: './notifications-page.component.html',
  styleUrl: './notifications-page.component.css'
})
export class NotificationsPageComponent {
  private readonly conversationsApi = inject(ConversationsApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly reload = new Subject<void>();
  private readonly view$ = this.route.queryParamMap.pipe(
    map((params): NotificationView => params.get('view') === 'history'
      ? { view: 'history', beforeId: positiveInteger(params.get('before_id'), 2147483647) }
      : { view: 'pending', offset: positiveInteger(params.get('offset')) ?? 0 }),
    distinctUntilChanged((a, b) => a.view === 'history'
      ? b.view === 'history' && a.beforeId === b.beforeId
      : b.view === 'pending' && a.offset === b.offset),
    shareReplay({ bufferSize: 1, refCount: true })
  );
  readonly activeView = toSignal(this.view$, { requireSync: true });
  readonly state = toSignal(combineLatest([this.view$, this.reload.pipe(startWith(undefined))]).pipe(
    switchMap(([view]) => {
      const page = view.view === 'history'
        ? this.conversationsApi.handoffHistory(view.beforeId).pipe(map((page): ReadyState => ({ status: 'history', page })))
        : this.conversationsApi.listConversations({ requires_human: true, limit: 25, offset: view.offset })
          .pipe(map((page): ReadyState => ({ status: 'pending', page })));
      return page.pipe(
        catchError((error: HttpErrorResponse) => of<NotificationState>({ status: 'error', forbidden: error.status === 403 })),
        startWith<NotificationState>({ status: 'loading' })
      );
    })
  ), { requireSync: true });

  refresh(): void { this.reload.next(); }
  previousOffset(offset: number, limit: number): number | null { return offset > limit ? offset - limit : null; }
}
