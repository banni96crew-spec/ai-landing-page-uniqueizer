Эталонный file-contract для Module 4 и 5
Общая модель цепочки
Финальная цепочка должна быть зафиксирована так:

raw/ = immutable debug snapshot
cleaned/ = self-contained output Module 1
mutated/ = self-contained output Module 2
rewritten/ = self-contained output Module 3
artifact = zip, собранный только из rewritten/
Ключевой инвариант:

Module 4 работает только внутри rewritten/
Module 5 читает только rewritten/
ни один из них не должен обращаться к raw/, cleaned/, mutated/
Module 4: Media Uniqueizer
Назначение
Module 4 получает rewritten/ как готовое self-contained дерево и in-place изменяет только поддерживаемые изображения.

Это единственный модуль в цепочке, которому разрешено in-place менять output предыдущего шага, потому что по архитектуре он подготавливает финальное дерево для упаковки.

Жёсткий входной контракт
Module 4 обязан читать только:

{job_dir}/rewritten/
Минимальные гарантии:

существует {job_dir}/rewritten/
существует {job_dir}/rewritten/index.html
дерево self-contained
локальные image-файлы, если они есть, уже лежат внутри rewritten/
Допустимые допущения
Можно предполагать только:

изображения находятся где-то внутри rewritten/
определение “изображение” делается по расширению/формату
Нельзя предполагать:

что обязательно есть rewritten/assets/images/
что все изображения лежат в одной папке
что картинки есть вообще
Что Module 4 обязан читать
Эталонно:

рекурсивно сканировать rewritten/
выбирать только поддерживаемые image-файлы
Поддерживаемые форматы:

.jpg
.jpeg
.png
.webp
Неподдерживаемые:

.gif
.svg
и всё прочее
Что Module 4 обязан писать
Он пишет только in-place в уже существующее дерево:

изменяет сами image-файлы внутри rewritten/
не создаёт новый root (media/, final/ и т.п.)
не должен менять index.html, CSS, JS, secondary HTML
Что Module 4 не имеет права делать
не читать raw/, cleaned/, mutated/
не перемещать файлы между папками
не менять HTML ссылки
не менять бинарные файлы, не являющиеся поддерживаемыми изображениями
не создавать новую директорию-выход поверх rewritten/
Инварианты после Module 4
После успешного завершения:

raw/, cleaned/, mutated/ не изменены
rewritten/ существует
структура rewritten/ не изменилась
изменены только поддерживаемые изображения
все остальные файлы byte-for-byte те же, что после Module 3
Ошибки Module 4
corrupt/unsupported image: warn + skip file
отсутствие изображений: не ошибка
критический I/O failure: валит модуль целиком
Минимальная сигнатура
async def module_media_uniqueizer(job_id: int) -> Path:
    """
    Input/output root: {job_dir}/rewritten/
    Returns: rewritten_dir
    """
Module 5: Packer
Назначение
Module 5 получает финальное дерево rewritten/, упаковывает его целиком в ZIP и регистрирует артефакт в БД.

Жёсткий входной контракт
Module 5 обязан читать только:

{job_dir}/rewritten/
и инфраструктурные зависимости:

ARTIFACTS_DIR
путь артефакта для job
таблицу artifacts
Минимальные гарантии:

существует {job_dir}/rewritten/
дерево self-contained
это финальное содержимое, которое нужно отдать пользователю
Что Module 5 обязан писать
ZIP-файл в ARTIFACTS_DIR
запись в artifacts
опционально cleanup {job_dir} после успешной упаковки, если это зафиксировано как политика пайплайна
Что именно пакуется
Эталонно:

всё дерево rewritten/ целиком
относительные пути внутри zip считаются от корня rewritten/
То есть в архив входят:

index.html
все локальные assets
secondary HTML, если они есть
любые прочие файлы внутри self-contained tree
Что Module 5 не имеет права делать
не должен читать raw/, cleaned/, mutated/
не должен собирать архив из смеси разных root-директорий
не должен модифицировать rewritten/ перед упаковкой
не должен переименовывать/перекладывать файлы внутри rewritten/
Выходной контракт артефакта
После успешного завершения должны существовать:

zip-файл по артефактному пути
запись в artifacts:
job_id
file_path
file_size
hash
И дальше job может считаться done.

Cleanup-контракт
Безопасный вариант:

cleanup {job_dir} выполняется только после успешного pack + успешной записи artifact metadata
Нельзя:

удалять workdir до подтверждённого успеха упаковки
удалять rewritten/ до сохранения zip и metadata
Ошибки Module 5
недостаточно места / ошибка записи zip: fatal
ошибка при вычислении hash / stat / DB insert: fatal
если артефакт уже существует по вашей бизнес-логике: либо idempotent-return existing, либо fail-fast, но это должно быть единым правилом
Минимальная сигнатура
async def module_packer(job_id: int) -> Path:
    """
    Input root:  {job_dir}/rewritten/
    Output file: {artifact_path}
    Returns: artifact_path
    """
Сводный контракт всей цепочки
File roots по модулям
Module 1: raw/ -> cleaned/
Module 2: cleaned/ -> mutated/
Module 3: mutated/ -> rewritten/
Module 4: rewritten/ -> rewritten/ in-place only for supported images
Module 5: rewritten/ -> artifact.zip
Кто что читает
Module 1 может читать сеть и пишет job tree
Module 2 читает только cleaned/
Module 3 читает только mutated/
Module 4 читает только rewritten/
Module 5 читает только rewritten/
Кто что не имеет права читать
Module 2+ не читают raw/
Module 3+ не читают cleaned/
Module 4/5 не читают mutated/
Module 5 не читает ничего, кроме rewritten/ и artifact/db infra
Жёсткие инварианты проекта
raw/ — только debug snapshot, никогда не input для Module 2+.
cleaned/, mutated/, rewritten/ — self-contained trees.
Каждый модуль пишет либо новый root, либо in-place только там, где это явно разрешено.
Единственное разрешённое in-place исключение в цепочке — Module 4 внутри rewritten/.
Module 5 пакует только rewritten/ целиком.
Самая короткая эталонная версия
Module 4 reads: rewritten/ recursively

Module 4 writes: supported images in rewritten/ in-place

Module 4 must not assume: rewritten/assets/images/ exists

Module 5 reads: rewritten/ only

Module 5 writes: zip artifact + artifacts row

Module 5 packs: whole rewritten/ tree

Module 5 must not read: raw/, cleaned/, mutated/