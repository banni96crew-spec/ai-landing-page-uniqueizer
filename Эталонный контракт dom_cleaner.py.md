Назначение
dom_cleaner.py это отдельный файл, но не отдельный pipeline-step.
Он является внутренним helper-этапом внутри module_scraper.py и отвечает только за:

чтение raw/index.html
санитарную очистку HTML
формирование self-contained cleaned/
возврат статистики очистки
Он не:

не пишет done-маркеры
не меняет jobs.status
не знает ничего о pipeline progression
не мутирует CSS/JS классы
не делает AI rewrite
Позиция в пайплайне
Контракт предполагает такую цепочку внутри Module 1:

Playwright scrape
rewrite/download ассетов в raw/
запись raw/index.html
вызов dom_cleaner.py
получение cleaned/
только после этого Module 1 считается успешным
Публичный контракт
from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True)
class DomCleanStats:
    removed_scripts: int
    removed_noscripts: int
    removed_iframes: int
    removed_csp_meta: int
    removed_inline_handlers: int
@dataclass(frozen=True)
class DomCleanResult:
    cleaned_dir: Path
    index_html_path: Path
    stats: DomCleanStats
async def clean_job_html(job_id: int, raw_dir: Path) -> DomCleanResult:
    """Read raw/index.html, create cleaned/, return cleaned_dir + stats."""
Вход
Обязательный вход:

job_id: int
raw_dir: Path
Ожидаемые инварианты входа:

raw_dir == get_job_dir(job_id) / "raw"
raw_dir / "index.html" существует
raw_dir уже содержит локальные ассеты, на которые HTML ссылается как ./assets/...
Выход
Функция обязана вернуть:

cleaned_dir = get_job_dir(job_id) / "cleaned"
index_html_path = cleaned_dir / "index.html"
stats: DomCleanStats
Инварианты выхода:

raw/ не изменён
cleaned/ self-contained
cleaned/index.html не содержит удалённых сущностей
Module 2 может читать только из cleaned/, не заглядывая в raw/
Директории и файловый контракт
Эталонный вариант:

копировать весь raw/ в cleaned/
затем перезаписывать только cleaned/index.html
Почему это лучший контракт:

сохраняет raw/ как дебажный артефакт
не привязывает cleaner к знанию конкретных подпапок
автоматически переносит assets/, secondary/ и будущие вложения
делает cleaned/ полноценным входом для следующего модуля
То есть cleaner не должен мыслить “скопировать только assets/”.
Правильнее: клонировать raw -> cleaned целиком.

Что именно удаляется
Обязательный минимум:

все <script>
все <noscript>
все <iframe>
все <meta http-equiv="Content-Security-Policy" ...>
с case-insensitive сравнением по http-equiv
все inline event handlers: любые атрибуты, имя которых начинается с on без учёта регистра
Примеры:

onclick
onload
onerror
onmouseover
Что не входит в dom_cleaner.py
Не включать сюда:

удаление/переписывание CSS классов
rename id/class
JS паттерн-замены
DOM noise injection
скачивание ассетов
переписывание src/href/srcset
запись pipeline marker
прямую работу со статусами jobs
Это зона module_scraper.py, asset_rewriter.py, module_dom_mutator.py, pipeline.py.

Логирование
Эталонно cleaner не пишет в БД сам.
Он возвращает stats, а логирование делает module_scraper.py.

Почему:

cleaner остаётся чистым transform-модулем
меньше связность с sqlite3
проще unit-тесты
лучше укладывается в SRP
Рекомендуемые log message из module_scraper.py после вызова cleaner:

dom_cleaner: removed script tags: N
dom_cleaner: removed noscript tags: N
dom_cleaner: removed iframe tags: N
dom_cleaner: removed CSP meta tags: N
dom_cleaner: removed inline event handlers: N
Уровень: info.

Асинхронность
Все blocking/cpu-bound части обязаны идти через asyncio.to_thread():

чтение HTML с диска
BeautifulSoup(..., "lxml")
обход/модификация DOM
копирование raw -> cleaned
запись cleaned/index.html
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
Для dom_cleaner.py я бы считал обязательными такие сценарии:

Удаляет script, noscript, iframe
Удаляет CSP meta по http-equiv
Удаляет все on* атрибуты
Не меняет raw/index.html
Создаёт self-contained cleaned/
Возвращает корректные счётчики в stats
Короткая формула контракта
dom_cleaner.py = pure-ish async wrapper around HTML sanitization:

input: raw/index.html
output: cleaned/index.html
side effect: формирует cleaned/ как полную копию raw/
return: cleaned_dir + stats
logging/status/progress: не его ответственность