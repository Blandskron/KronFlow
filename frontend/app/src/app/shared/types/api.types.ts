export interface ApiResponse<T> {
  success: boolean;
  status?: {
    code: number;
    message: string;
  };
  data: T;
  meta?: Record<string, unknown>;
  links?: Record<string, string>;
}

export interface ApiErrorBody {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  error_code?: string;
  errors?: unknown[];
  meta?: Record<string, unknown>;
  success?: false;
  code?: string;
  message?: string;
  details?: unknown;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
