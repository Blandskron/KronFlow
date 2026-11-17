import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { LucideMessageSquare } from '@lucide/angular';
import { ConversationsApiService } from '@domains/conversations/data-access/conversations-api.service';
import { Conversation } from '@domains/conversations/domain/conversation.model';

@Component({
  selector: 'flowkron-notifications-page',
  standalone: true,
  imports: [DatePipe, RouterLink, LucideMessageSquare],
  templateUrl: './notifications-page.component.html',
  styleUrl: './notifications-page.component.css'
})
export class NotificationsPageComponent implements OnInit {
  private readonly conversationsApi = inject(ConversationsApiService);
  private readonly destroyRef = inject(DestroyRef);
  readonly conversations = signal<Conversation[]>([]);
  readonly loading = signal(false);
  readonly failed = signal(false);
  readonly total = signal(0);

  ngOnInit(): void { this.refresh(); }

  refresh(): void {
    if (this.loading()) return;
    this.loading.set(true);
    this.failed.set(false);
    this.conversationsApi.listConversations({ requires_human: true, limit: 25 })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ items, total }) => {
          this.conversations.set(items);
          this.total.set(total);
          this.loading.set(false);
        },
        error: () => {
          this.failed.set(true);
          this.loading.set(false);
        }
      });
  }
}
