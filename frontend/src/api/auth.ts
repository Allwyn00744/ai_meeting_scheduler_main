import { api } from "./client";
import type { TokenResponse, User } from "@/types";

const baseURL = import.meta.env.VITE_API_URL ?? "";

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  timezone?: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export const authApi = {
  register: (payload: RegisterPayload) =>
    api.post<User>("/auth/register", payload).then((r) => r.data),

  login: (payload: LoginPayload) =>
    api.post<TokenResponse>("/auth/login", payload).then((r) => r.data),

  me: () => api.get<User>("/auth/me").then((r) => r.data),

  /**
   * Full-page redirect to Google's consent screen for "Sign in with
   * Google" (GET /auth/google/login) - unlike googleApi
   * .connectRedirectUrl(), this needs no token: the visitor has no
   * session yet, that's the whole point of this flow.
   */
  googleLoginRedirectUrl: () => `${baseURL}/auth/google/login`,
};
