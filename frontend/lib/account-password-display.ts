/** Plain password used only for Account page visibility toggle; cleared on logout. */

const STORAGE_KEY = "ai_lpu_account_password_display_v1";

export function setStoredPasswordForAccountDisplay(password: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    localStorage.setItem(STORAGE_KEY, password);
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearStoredPasswordForAccountDisplay(): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function getStoredPasswordForAccountDisplay(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}
