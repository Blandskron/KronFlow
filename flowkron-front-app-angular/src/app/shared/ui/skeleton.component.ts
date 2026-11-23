import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'flowkron-skeleton',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="fk-skeleton" [style.height]="height()" [style.width]="width()" aria-hidden="true"></div>
  `,
  styles: `
    .fk-skeleton {
      border-radius: var(--radius-md);
      background: linear-gradient(
        90deg,
        var(--muted) 25%,
        color-mix(in srgb, var(--border) 65%, var(--muted)) 50%,
        var(--muted) 75%
      );
      background-size: 200% 100%;
      animation: fk-shimmer 1.4s ease-in-out infinite;
    }

    @keyframes fk-shimmer {
      0% {
        background-position: 200% 0;
      }
      100% {
        background-position: -200% 0;
      }
    }
  `
})
export class SkeletonComponent {
  readonly width = input<string>('100%');
  readonly height = input<string>('72px');
}
