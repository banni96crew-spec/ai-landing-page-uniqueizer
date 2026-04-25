Эталонный file-contract для Module 2
Назначение
Module 2 получает полностью self-contained дерево cleaned/, применяет DOM/CSS/JS мутации и создаёт новое self-contained дерево mutated/.

Его задача:

переименовать class/id по selector map
обновить HTML
обновить CSS
обновить JS только по разрешённым паттернам
добавить DOM noise
Его задача не:

скачивать ассеты
чистить трекеры/script/iframe
читать raw/
писать в rewritten/
1. Жёсткий входной контракт
Обязан читать
Module 2 обязан читать только:

{job_dir}/cleaned/index.html
локальные файлы внутри {job_dir}/cleaned/, которые реально нужны для мутаций:
CSS-файлы
JS-файлы
при необходимости другие текстовые файлы, если позже это будет явно добавлено в контракт
Не имеет права читать
Module 2 не должен читать:

{job_dir}/raw/**
{job_dir}/mutated/** до начала собственной работы
{job_dir}/rewritten/**
внешние URL / сеть
Минимальная гарантия входа
Единственное, что модуль вправе считать гарантированным:

существует директория {job_dir}/cleaned/
существует файл {job_dir}/cleaned/index.html
HTML внутри cleaned/index.html уже ссылается на локальные ресурсы, если upstream смог их локализовать
2. Допустимые допущения про структуру cleaned/
Допустимо предполагать
cleaned/ это self-contained root
все файлы, которые надо мутировать, находятся внутри дерева cleaned/
index.html является главным входом
локальные пути в HTML/CSS/JS указывают на файлы внутри того же job tree
Недопустимо предполагать
Нельзя жёстко зашивать, что обязательно существуют:

cleaned/assets/css/
cleaned/assets/js/
cleaned/assets/images/
cleaned/assets/fonts/
Почему: текущий код пока не гарантирует такую иерархию; upstream уже сейчас мыслится как “self-contained tree”, а не как фиксированная типизированная раскладка.

Правильное допущение
Правильный уровень абстракции такой:

Module 2 работает не от схемы папок, а от набора файлов внутри cleaned/
HTML берётся из cleaned/index.html
CSS/JS находятся по дереву, а не по заранее вбитым подпапкам
3. Как Module 2 должен находить файлы
Обязан
считать cleaned/index.html главным источником истины
строить selector map на основе:
HTML (class, id) из index.html
CSS-файлов внутри cleaned/
Может
искать CSS/JS рекурсивно по расширениям внутри cleaned/
либо идти от ссылок из HTML, если это будет выбранной стратегией
Не должен
зависеть только от конкретного пути вида cleaned/assets/*.css
ломаться, если CSS/JS лежат глубже или в другой вложенности
4. Жёсткий выходной контракт
Обязан писать
Module 2 обязан создать:

{job_dir}/mutated/
{job_dir}/mutated/index.html
И сформировать mutated/ как полное self-contained дерево, пригодное как вход для Module 3.

Рекомендуемая стратегия
Эталонно:

скопировать всё дерево cleaned/ в mutated/
затем перезаписать только изменённые файлы:
mutated/index.html
изменённые CSS
изменённые JS
Это лучший контракт, потому что:

сохраняется self-contained output
не теряются неизвестные/будущие файлы
модуль не зависит от знания всех подпапок заранее
Не должен писать
в cleaned/
в raw/
в rewritten/
5. Какие файлы Module 2 обязан мутировать
Обязан
mutated/index.html
все релевантные локальные CSS-файлы внутри mutated/
все релевантные локальные JS-файлы внутри mutated/, но только по утверждённым паттернам
Может не трогать
бинарные файлы
шрифты
изображения
secondary HTML, если вы заранее зафиксируете, что MVP мутирует только index.html
Важно заранее зафиксировать
Самый безопасный контракт для MVP:

HTML mutation only for index.html
CSS/JS mutation for локальные файлы внутри self-contained tree
secondary HTML копируются как есть
6. Инварианты после завершения Module 2
После успешного завершения должны быть верны условия:

raw/ не изменён
cleaned/ не изменён
mutated/ существует
mutated/ self-contained
mutated/index.html существует
все ссылки, которые были локальными в cleaned/, остаются локальными в mutated/
Module 3 может читать только mutated/, не зная ничего о cleaned/ и raw/
7. Ошибки и допустимое поведение
Модуль должен падать целиком, если
нет cleaned/index.html
не удалось сформировать mutated/
произошла критическая ошибка при основной HTML-мутации
Модуль может продолжать работу пофайлово, если
отдельный CSS-файл не распарсился regex-логикой
отдельный JS-файл не содержит поддерживаемых паттернов
отдельный файл не удалось модифицировать, но это не разрушает основной output-contract
То есть good practice:

HTML failure = fatal
per-file CSS parse failure = warn + skip that file
unsupported JS cases = skip silently or warn, по вашему правилу логирования
8. Минимальная сигнатура контракта
Концептуально я бы зафиксировал так:

async def module_dom_mutator(job_id: int) -> Path:
    """
    Input root:  {job_dir}/cleaned/
    Output root: {job_dir}/mutated/
    Returns: mutated_dir
    """
Внутренние инварианты:

читает только cleaned/
пишет только mutated/
не модифицирует входное дерево
9. Краткая “запретительная” формулировка для команды
Module 2 не имеет права знать о raw/.
Он получает на вход только cleaned/ как self-contained root и обязан выдать только mutated/ как self-contained root.
Любые предположения о фиксированных подпапках внутри cleaned/ запрещены, кроме гарантии существования cleaned/index.html.

10. Самая короткая эталонная версия
reads: cleaned/index.html + локальные CSS/JS рекурсивно внутри cleaned/
writes: полная копия cleaned/ -> mutated/, затем перезапись изменённых HTML/CSS/JS
must not read: raw/
must not mutate in place: cleaned/
must not assume: assets/css, assets/js, assets/images, assets/fonts
may assume only: cleaned/ self-contained, cleaned/index.html exists