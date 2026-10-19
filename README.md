# Smart Grocery Agents

Планирование меню и списка покупок по запасам, бюджету и ограничениям питания.
MVP связывает поиск рецептов, LLM-планировщик, Python-калькулятор и отдельного
LLM-критика через ограниченный workflow со Streamlit-интерфейсом.

## Участники

| Роль | ФИО | GitHub |
|---|---|---|
| Data & Recipe Search | TODO — заполнить команде | TODO |
| Meal Planner | TODO — заполнить команде | TODO |
| Shopping & Validator | TODO — заполнить команде | TODO |
| Integration & UI | TODO — заполнить команде | TODO |

## Текущий статус

Работает локальный offline MVP с тремя демонстрационными рецептами, условными
ценами и двумя попытками планирования. В этой ветке подключена реализация
роли 3 из `feature/budget` / PR #1. Интеграция и UI описаны в
[docs/ROLE_4.md](docs/ROLE_4.md).

Реальный провайдер и модель ещё не утверждены командой. Подготовлен вариант
Google Gemini `gemini-3.1-flash-lite` через OpenAI-compatible API; настройка
ниже. Планировщик выбирает ID из найденных рецептов и пересматривает выбор
по feedback. Отдельный критик объясняет найденные Python нарушения и советует
изменения. Цены, количества и решение о валидности вычисляются Python.
`MOCK_LLM=true` не вызывает модель, использует фиксированное меню и не является
демонстрацией LLM-функции для proposal. Живой вызов и успешный цикл с провайдером
пока не подтверждены.

## Локальный запуск

Python 3.11 или новее. Команды из корня репозитория:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m streamlit run app.py
```

Windows PowerShell: вместо `source` выполнить `.\.venv\Scripts\Activate.ps1`,
а вместо `cp` — `Copy-Item .env.example .env`.
Открыть http://localhost:8501. `.env` загружается автоматически; экспортированные
переменные окружения имеют приоритет. UI показывает запрос, меню по дням,
корзину, стоимость, ошибки и историю обеих попыток; результат можно скачать JSON.

## Docker

Установить и запустить Docker Desktop / Docker Engine. Сначала создать `.env`:

```bash
cp .env.example .env
docker compose up --build
```

Открыть http://localhost:8501. Остановка: `docker compose down`.
Альтернатива без Compose:

```bash
docker build -t smart-grocery .
docker run --rm -p 127.0.0.1:8501:8501 --env-file .env smart-grocery
```

Проверка сервера: `curl --fail http://localhost:8501/_stcore/health`.
Контейнер запускается без root; `.env`, Git и `.venv` не входят в образ.

## Настройка настоящей модели

Создать ключ в [Google AI Studio](https://aistudio.google.com/apikey) и заполнить
**локальный** `.env`, не добавляя ключ в Git:

```dotenv
MOCK_LLM=false
LLM_API_KEY=YOUR_LOCAL_GEMINI_KEY
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-3.1-flash-lite
CRITIC_MODEL=gemini-3.1-flash-lite
```

Это предложенная конфигурация; команда может выбрать другой совместимый
провайдер. `CRITIC_MODEL` необязателен и по умолчанию равен `LLM_MODEL`.
[Google описывает совместимость SDK](https://ai.google.dev/gemini-api/docs/openai)
и [тарифы и free tier](https://ai.google.dev/gemini-api/docs/pricing).
После изменения `.env` перезапустить процесс / контейнер. План живой проверки
и критерии успешности — в [docs/ROLE_4.md](docs/ROLE_4.md).

## Тесты и примеры

```bash
python -m pytest -q
python scripts/run_demo.py fixtures/request_basic.json
python scripts/run_demo.py fixtures/request_over_budget.json
```

Базовый пример: меню `omelette`, `rice_bowl`, стоимость 3.50 EUR, `valid=true`.
Нулевой бюджет: `valid=false`, причина `Budget exceeded`, рекомендации критика,
две попытки. CLI возвращает код 0 только для валидного итога, 1 для ошибки
workflow / невалидного итога, 2 для неправильного входного JSON.

Интеграционные тесты проверяют пересмотр, передачу feedback, неизвестный ID,
отсутствие рецептов, пропущенные цены, сбои модулей и сохранение истории.
Streamlit AppTest проверяет интерфейс. Шаблон GitHub Actions в `docs/github-tests.yml` запускает тесты,
сборку контейнера и HTTP health check. Для включения CI перенести его в
`.github/workflows/tests.yml` через доступ с правом workflow. Сейчас CI
не активирован: текущий GitHub-токен не разрешает создавать workflows.

## Архитектура и границы

`search_recipes → propose_menu → validate_plan → [feedback → propose_menu → validate_plan]`

- `src/smart_grocery/schemas/models.py` и `docs/CONTRACTS.md`: действующие общие схемы.
- `tools/recipes.py`: поиск, роль 1.
- `agents/planner.py`: планировщик, роль 2.
- `tools/budget.py`, `agents/validator.py`, `agents/critic.py`: роль 3.
- `workflow/runner.py`, `app.py`, Docker, CI: роль 4.

`run_workflow` сохраняет `PlanningResult`. Отдельный `run_workflow_with_trace`
даёт UI результат с историей без изменения общих схем. LangGraph для одного
ограниченного цикла не требуется. Сбой настоящей модели не переключает UI
на mock и не показывает предыдущий невалидный план как принятый.

Текущий каталог использует EUR и условные portions. Pantry означает доступность
продукта без ограничения количества. Масштабирование на нескольких человек
калькулятором пока не поддерживается; UI фиксирует одного человека. Это учебная
оценка, не реальные магазинные цены. Расширение данных до 30–100 рецептов,
согласование модели, живой прогон и заполнение участников остаются задачами
владельцев модулей / команды перед proposal.

Курс и требования: https://github.com/AlgazinovAleksandr/LLM-Agents-Course/blob/main/GROUP_PROJECT.md
