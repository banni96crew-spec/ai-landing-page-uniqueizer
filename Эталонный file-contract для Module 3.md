Эталонный file-contract для Module 3
Назначение
Module 3 получает готовое self-contained дерево mutated/, извлекает текст из index.html, выполняет AI rewrite и формирует новое self-contained дерево rewritten/.

Его задача:

взять mutated/ как замороженный вход
скопировать это дерево в rewritten/
переписать только текст в rewritten/index.html
оставить прочие файлы консистентными и локальными
Его задача не:

не работать с raw/
не работать с cleaned/
не мутировать CSS/JS/class/id
не изменять изображения
не паковать артефакт
1. Жёсткий входной контракт
Обязан читать
Module 3 обязан читать только:

{job_dir}/mutated/index.html
при необходимости настройки из БД/конфига:
ai_provider
openai_api_key
anthropic_api_key
openai_model
anthropic_model
Не имеет права читать как файловый input
{job_dir}/raw/**
{job_dir}/cleaned/**
{job_dir}/rewritten/** до формирования своего output
Минимальная гарантия входа
Модуль вправе считать гарантированным только:

существует {job_dir}/mutated/
существует {job_dir}/mutated/index.html
mutated/ уже self-contained
все локальные ассеты, нужные HTML, уже лежат внутри mutated/
2. Допустимые допущения про структуру mutated/
Допустимо предполагать
mutated/ это self-contained root
главный HTML-файл для rewrite — это mutated/index.html
текстовые ноды для AI берутся только из index.html
локальные ассеты, secondary pages и прочие файлы уже готовы и не требуют участия AI rewriter
Недопустимо предполагать
Нельзя жёстко зашивать, что обязательно существуют:

mutated/assets/images/
mutated/assets/css/
mutated/assets/js/
mutated/assets/fonts/
Также нельзя требовать наличие secondary pages как обязательной части контракта.

Правильный уровень абстракции:

Module 3 работает от self-contained tree + index.html
а не от фиксированной схемы подпапок
3. Что именно Module 3 должен читать внутри HTML
Обязан
Извлекать текст только из mutated/index.html, из заранее разрешённого набора узлов, например по PRD:

h1–h6
p
button
li
span
Не должен
переписывать атрибуты href/src/class/id/style
переписывать inline JS/CSS
переписывать secondary HTML-страницы, если это не зафиксировано отдельным расширением контракта
Важный инвариант
Module 3 меняет только текстовый контент узлов, а не структуру дерева файлов.

4. Жёсткий выходной контракт
Обязан писать
Module 3 обязан создать:

{job_dir}/rewritten/
{job_dir}/rewritten/index.html
Эталонная стратегия записи
Правильный контракт такой:

скопировать всё дерево mutated/ в rewritten/
затем перезаписать только:
rewritten/index.html
Это ключевой invariant.

Почему именно так
Потому что:

rewritten/ должен быть self-contained
Module 4 должен работать только с rewritten/
Module 5 должен паковать только rewritten/
никакие файлы из mutated/ не должны оставаться “живыми dependencies” после Module 3
5. Что Module 3 обязан сохранить без изменений
После копирования mutated -> rewritten и rewrite текста модуль обязан сохранить без изменений:

локальные asset-файлы
CSS-файлы
JS-файлы
шрифты
изображения
secondary HTML-файлы
любые прочие файлы внутри дерева
То есть единственный обязательный изменяемый файл в MVP-контракте:

rewritten/index.html
6. Что Module 3 не имеет права делать
Не должен
модифицировать mutated/ in-place
читать cleaned/ или raw/
менять бинарные файлы
менять CSS/JS
реструктурировать директории
полагаться на подпапки assets/css|js|images|fonts
создавать зависимости на внешние URL
Не должен даже при ошибках
частично переписывать mutated/
использовать mutated/ как output
смешивать rewrite-output с input-tree
7. Инварианты после завершения Module 3
После успешного завершения должны быть верны условия:

raw/ не изменён
cleaned/ не изменён
mutated/ не изменён
rewritten/ существует
rewritten/ self-contained
rewritten/index.html существует
rewritten/index.html содержит AI-rewritten текст
все остальные файлы в rewritten/ соответствуют содержимому mutated/, если они не подлежат rewrite
Module 4 может работать, зная только rewritten/
8. Поведение при AI-ошибках и file-contract
Если batch упал
При batch-level ошибках file-contract должен оставаться стабильным:

rewritten/ всё равно формируется как копия mutated/
проблемные текстовые ноды сохраняют оригинальный текст
output-tree остаётся валидным и self-contained
Если exceeded threshold / fail-fast / fatal error
Если модуль должен завершиться failed по бизнес-логике:

не должно оставаться состояния, где mutated/ частично испорчен
rewritten/ может либо не существовать, либо быть пересоздан заново при следующем запуске
главное: input-tree mutated/ остаётся неизменным
9. Минимальная сигнатура контракта
async def module_ai_rewriter(job_id: int) -> Path:
    """
    Input root:  {job_dir}/mutated/
    Output root: {job_dir}/rewritten/
    Returns: rewritten_dir
    """
Внутренние инварианты:

читает только mutated/
пишет только rewritten/
не меняет входное дерево
текстовые изменения ограничены rewritten/index.html
10. Краткая формула для команды
Module 3 получает mutated/ как immutable self-contained input-root и обязан выдать rewritten/ как immutable output-root для следующих стадий.
Он копирует всё дерево mutated -> rewritten, после чего меняет только текстовый слой в rewritten/index.html.
Он не должен знать ничего о raw/ или cleaned/.

11. Сверхкороткая эталонная версия
reads: mutated/index.html + settings/provider config
writes: полная копия mutated/ -> rewritten/, затем перезапись только rewritten/index.html
must not read: raw/, cleaned/
must not mutate in place: mutated/
must not assume: фиксированные подпапки assets/*
may assume only: mutated/ self-contained, mutated/index.html exists
stable invariant: Module 4 и Module 5 знают только rewritten/