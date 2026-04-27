export function getRequiredPublicEnv(name: string): string {
  // Явный маппинг переменных, чтобы сборщик Next.js мог их корректно подставить
  const envMap: Record<string, string | undefined> = {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL,
  };

  const val = envMap[name];

  if (!val) {
    // Жесткий фоллбэк для локальной разработки, чтобы UI не падал
    if (name === "NEXT_PUBLIC_API_URL") return "http://127.0.0.1:8000";
    if (name === "NEXT_PUBLIC_WS_URL") return "ws://127.0.0.1:8000";

    if (typeof window !== "undefined") {
      throw new Error(`Missing required env var: ${name}`);
    }
  }

  return val || "";
}