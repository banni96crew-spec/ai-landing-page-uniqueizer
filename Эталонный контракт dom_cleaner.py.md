Назначение
dom_cleaner.py это отдельный файл, но не отдельный pipeline-step.
Он является внутренним helper-этапом внутри module_scraper.py и отвечает только за:

чтение raw/index.html
санитарную очистку HTML (PRD §3.3 / M2.4–M2.7)
формирование self-contained cleaned/
возврат статистики очистки и списка абсолютных URL CSS Google Fonts (для последующего скачивания в module_scraper)
Он не:

не пишет done-маркеры
не меняет jobs.status
не знает ничего о pipeline progression
не мутирует CSS/JS классы
не делает AI rewrite
не выполняет сетевые запросы (скачивание шрифтов — в google_fonts / module_scraper)
Позиция в пайплайне
Контракт предполагает такую цепочку внутри Module 1:

Playwright scrape
rewrite/download ассетов в raw/
запись raw/index.html
вызов dom_cleaner.py
получение cleaned/
только после этого Module 1 считается успешным
Публичный контракт
from dataclasses import dataclass, field
from pathlib import Path
@dataclass(frozen=True)
class DomCleanStats:
    removed_tracker_scripts: int
    removed_tracker_iframes: int
    removed_noscripts: int
    removed_csp_meta: int
    removed_html_comments: int
    removed_google_font_links: int
    removed_font_imports: int
    removed_bdo_cite: int
@dataclass(frozen=True)
class DomCleanResult:
    cleaned_dir: Path
    index_html_path: Path
    stats: DomCleanStats
    google_font_css_urls: tuple[str, ...] = field(default_factory=tuple)
async def clean_job_html(job_id: int, raw_dir: Path, *, base_url: str | None = None) -> DomCleanResult:
    """Read raw/index.html, create cleaned/, return cleaned_dir + stats."""
Вход
Обязательный вход:

job_id: int
raw_dir: Path
Опционально:

base_url: разрешение относительных src/href для сопоставления с TRACKER_DOMAINS и fonts.googleapis.com; при None используется первый тег `<base href>` из HTML, иначе fallback `https://127.0.0.1/`
Ожидаемые инварианты входа:

raw_dir == get_job_dir(job_id) / "raw"
raw_dir / "index.html" существует
raw_dir уже содержит локальные ассеты, на которые HTML ссылается как ./assets/...
Выход
Функция обязана вернуть:

cleaned_dir = get_job_dir(job_id) / "cleaned"
index_html_path = cleaned_dir / "index.html"
stats: DomCleanStats
google_font_css_urls: абсолютные URL удалённых `<link rel="stylesheet" href="https://fonts.googleapis.com/...">`
Инварианты выхода:

raw/ не изменён
cleaned/ self-contained
cleaned/index.html отражает правила PRD (см. ниже)
Module 2 может читать только из cleaned/, не заглядывая в raw/
Директории и файловый контракт
Эталонный вариант:

копировать весь raw/ в cleaned/
затем перезаписывать cleaned/index.html
обработать все cleaned/**/*.css: удалить правила @import, указывающие на fonts.googleapis.com
Почему это лучший контракт:

сохраняет raw/ как дебажный артефакт
не привязывает cleaner к знанию конкретных подпапок
автоматически переносит assets/, secondary/ и будущие вложения
делает cleaned/ полноценным входом для следующего модуля
То есть cleaner не должен мыслить “скопировать только assets/”.
Правильнее: клонировать raw -> cleaned целиком.

Что именно удаляется / меняется
По PRD (TRACKER_DOMAINS — точный список из PRD.md §3.3):

удалять только `<script src="...">`, если после нормализации (urljoin с base_url) хост совпадает с доменом из TRACKER_DOMAINS (`hostname == domain` или `hostname.endswith("." + domain)`); inline `<script>` без src не трогать
удалять только `<iframe src="...">` по той же логике трекерных хостов; iframe без src или с не-трекерным src сохранять
все `<noscript>`
все `<meta http-equiv="Content-Security-Policy" ...>` с case-insensitive сравнением по http-equiv
все HTML-комментарии
теги `<bdo>` и `<cite>`: unwrap дочерних узлов (контент сохраняется)
`<link rel="stylesheet" ... href="...fonts.googleapis.com...">`: удалить тег, URL сохранить в google_font_css_urls
inline event handlers (`on*`) не удалять — часть бизнес-логики лендингов
Что не входит в dom_cleaner.py
Не включать сюда:

удаление/переписывание CSS классов
rename id/class
JS паттерн-замены
DOM noise injection
HTTP-скачивание шрифтов (только сбор URL и очистка HTML/CSS)
запись pipeline marker
прямую работу со статусами jobs
Это зона module_scraper.py, asset_rewriter.py, google_fonts.py, module_dom_mutator.py, pipeline.py.

Логирование
Эталонно cleaner не пишет в БД сам.
Он возвращает stats, а логирование делает module_scraper.py.

Рекомендуемые log message из module_scraper.py после вызова cleaner (info):

dom_cleaner: removed tracker scripts: N
dom_cleaner: removed tracker iframes: N
dom_cleaner: removed noscript tags: N
dom_cleaner: removed CSP meta tags: N
dom_cleaner: removed HTML comments: N
dom_cleaner: removed Google Fonts link tags: N
dom_cleaner: stripped Google Fonts @import rules: N
dom_cleaner: unwrapped bdo/cite tags: N

Асинхронность
Все blocking/cpu-bound части обязаны идти через asyncio.to_thread():

чтение HTML с диска
BeautifulSoup(..., "lxml")
обход/модификация DOM
копирование raw -> cleaned
запись cleaned/index.html
обход и перезапись CSS под cleaned/
Снаружи API cleaner должен быть async, внутри тяжёлая работа синхронная, завернутая в to_thread().

Ошибки и failure semantics
Если cleaner падает:

исключение не глотается
оно пробрасывается вверх в module_scraper.py
далее job падает по обычной логике пайплайна
То есть cleaner не делает собственный recovery layer.
Это часть Module 1, а не “best-effort helper”.

Постусловия для соседних модулей
После интеграции этого контракта нужно заморозить два правила:

Выход Module 1 концептуально = cleaned/
Вход Module 2 = cleaned/, а не raw/
Это главный стык между cleaner и mutator.

Минимальный тестовый контракт
Для dom_cleaner.py обязательные сценарии:

Удаляет только трекерные script src / iframe src по TRACKER_DOMAINS
Сохраняет inline script и не-трекерные iframe
Удаляет noscript, CSP meta, HTML-комментарии
Разворачивает bdo/cite
Удаляет link на fonts.googleapis.com и возвращает URL в google_font_css_urls
Снимает @import на fonts.googleapis.com из CSS под cleaned/
Не снимает on* атрибуты
Не меняет raw/index.html
Создаёт self-contained cleaned/
Возвращает корректные счётчики в stats
Короткая формула контракта
dom_cleaner.py = pure-ish async wrapper around HTML/CSS sanitization:

input: raw/index.html + опциональный base_url
output: cleaned/index.html + очищенные CSS + stats + google_font_css_urls
side effect: формирует cleaned/ как полную копию raw/ с перезаписью index и правками CSS
return: cleaned_dir + stats
logging/status/progress: не его ответственность
