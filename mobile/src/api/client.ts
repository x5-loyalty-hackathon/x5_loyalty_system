/**
 * Адрес backend на Mac. `localhost` не подходит: для приложения на iPhone это сам
 * iPhone. Подставь адрес из `ipconfig getifaddr en0`.
 */
import { assertVersion } from '../domain/mealFlow.ts';

export const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000';

const TIMEOUT_MS = 3500;

export class ApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
    if (!response.ok) {
      throw new ApiError(`Сервер ответил ${response.status}`, response.status);
    }
    const data = await response.json();
    if (data && typeof data === 'object' && 'contract_version' in data) {
      assertVersion(data);
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof Error && error.message.startsWith('Нужен backend')) throw error;
    if ((error as Error).name === 'AbortError') {
      throw new ApiError('Backend не ответил за 3,5 секунды');
    }
    throw new ApiError(`Нет связи с ${API_BASE_URL}`);
  } finally {
    clearTimeout(timer);
  }
}
