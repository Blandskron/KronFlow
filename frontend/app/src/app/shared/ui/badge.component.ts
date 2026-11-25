import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type BadgeTone = 'primary' | 'success' | 'info' | 'warning' | 'danger' | 'neutral';

@Component({
  selector: 'kronflow-badge',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span [class]="badgeClass()"><ng-content /></span>`
})
export class BadgeComponent {
  readonly tone = input<BadgeTone>('neutral');
  readonly badgeClass = computed(() => `badge badge-${this.tone()}`);
}
