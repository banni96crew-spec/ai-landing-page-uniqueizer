import asyncio
import httpx
from pathlib import Path
# Импортируем твою новую функцию
from backend.worker.module_scraper import download_google_fonts

async def test():
    fonts_dir = Path("./volumes/test_fonts")
    fonts_dir.mkdir(parents=True, exist_ok=True)

    # Прямая ссылка на CSS шрифта из Google Fonts
    css_url = "https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap"

    print(f"Начинаем скачивание из {css_url}...")

    async with httpx.AsyncClient() as client:
        result_css = await download_google_fonts(
            css_url=css_url,
            fonts_dir=fonts_dir,
            client=client,
            job_id=999
        )

    print("\n=== Итоговый CSS (пути должны быть заменены) ===")
    print(result_css)
    print("=================================================")
    print(f"Проверь папку: {fonts_dir.absolute()}")

if __name__ == "__main__":
    asyncio.run(test())