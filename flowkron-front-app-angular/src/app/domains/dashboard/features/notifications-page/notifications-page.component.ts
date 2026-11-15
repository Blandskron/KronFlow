import { Component } from '@angular/core';
import { LucideCheckCircle2, LucideMessageSquare, LucideWorkflow } from '@lucide/angular';

@Component({
  selector: 'flowkron-notifications-page',
  standalone: true,
  imports: [LucideCheckCircle2, LucideMessageSquare, LucideWorkflow],
  templateUrl: './notifications-page.component.html',
  styleUrl: './notifications-page.component.css'
})
export class NotificationsPageComponent {
  readonly notifications: { icon: string; title: string; message: string; time: string }[] = [];
}
