import { Component } from '@angular/core';
import { ThemeToggleComponent } from '@shared/ui/theme-toggle.component';

@Component({
  selector: 'flowkron-auth-layout',
  standalone: true,
  imports: [ThemeToggleComponent],
  templateUrl: '../auth-layout/auth-layout.component.html',
  styleUrl: '../auth-layout/auth-layout.component.css'
})
export class AuthLayoutComponent {}
