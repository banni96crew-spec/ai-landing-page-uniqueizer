export function getRequiredPublicEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    // Next.js может prerender'ить Client Components на сервере во время build.
    // В этом случае мы НЕ валим билд, а отдаём пустую строку и показываем ошибку уже в браузере.
    if (typeof window !== "undefined") {
      throw new Error(`Missing required env var: ${name}`);
    }
    return "";
  }
  return value;
}

