async def _force_dark_mode(page: object) -> None:
    """
    Append 'dark' and 'x5a96' classes to both <html> and <body>.
    This ensures CSS dark-mode rules and sprite sheets activate correctly.
    """
    await page.evaluate(
        """() => {
            const root = document.documentElement;
            const body = document.body;

            // Добавляем необходимые классы для темной темы и спрайтов
            const classes = ['dark', 'x5a96'];
            classes.forEach(cls => {
                if (!root.classList.contains(cls)) root.classList.add(cls);
                if (body && !body.classList.contains(cls)) body.classList.add(cls);
            });

            root.setAttribute('data-theme', 'dark');
            root.setAttribute('data-color-scheme', 'dark');
            if (body) {
                body.setAttribute('data-theme', 'dark');
                body.setAttribute('data-color-scheme', 'dark');
            }
        }"""
    )


async def _scroll_to_bottom_for_lazy_load(page: object, job_id: int) -> None:
    """
    Scroll using requestAnimationFrame to bypass Chromium background throttling
    and reliably trigger IntersectionObservers for lazy-loaded elements.
    """
    scroll_js = """async () => {
        await new Promise(resolve => {
            let currentScroll = 0;
            const stepPx = 150; // Оптимальный шаг для срабатывания триггеров

            const scrollStep = () => {
                const totalHeight = document.body.scrollHeight;
                window.scrollBy(0, stepPx);
                currentScroll += stepPx;

                if (currentScroll < totalHeight) {
                    requestAnimationFrame(scrollStep);
                } else {
                    // Возвращаемся наверх, чтобы не ломать скриншоты или парсинг
                    window.scrollTo(0, 0);
                    resolve();
                }
            };
            requestAnimationFrame(scrollStep);
        });
    }"""

    await page.evaluate(f"({scroll_js})()")

    # Даем браузеру время обработать запросы картинок после скролла
    from backend.worker.module_scraper import LAZY_LOAD_WAIT_MS, NETWORKIDLE_TIMEOUT_MS # Не забудь импорты
    import logging
    logger = logging.getLogger(__name__)

    await page.wait_for_timeout(LAZY_LOAD_WAIT_MS)
    try:
        await page.wait_for_load_state("networkidle", timeout=NETWORKIDLE_TIMEOUT_MS)
    except Exception:
        logger.warning("scraper: networkidle timeout after lazy-load scroll (job_id=%s)", job_id)