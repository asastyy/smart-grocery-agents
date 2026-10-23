# Smart Grocery Agents

MVP планирует обеды и ужины по запасам, бюджету, числу людей и времени
приготовления. Поиск работает на подготовленных данных Food.com: 150 рецептов,
503 нормализованных ингредиента и демонстрационные цены в условных единицах CU.

## Проблема и зачем здесь LLM

Пользователю трудно вручную сопоставить запасы, бюджет, ограничения питания,
время приготовления и десятки подходящих рецептов. Обычные фильтры хорошо
отсекают неподходящие варианты, но не составляют связное меню и не умеют
пересматривать выбор по содержательным замечаниям.

Проект использует Google Gemini `gemini-3.5-flash-lite` в двух ролях. Meal
Planner выбирает меню только из найденных рецептов, а Critic объясняет нарушения
и формирует рекомендации для следующей попытки. LLM не считает стоимость и не
решает, валидно ли меню: количества, pantry, цены, единицы и бюджет проверяет
детерминированный Python-код. Такое разделение использует сильную сторону LLM —
выбор и текстовое объяснение — и оставляет проверяемую арифметику инструментам.

## Участники

| Роль | Участник | GitHub | Зона ответственности |
|---|---|---|---|
| Data & Recipe Search | Максим — уточнить полное ФИО | [@jeweller9](https://github.com/jeweller9) | данные и поиск рецептов |
| Meal Planner | Рита — уточнить полное ФИО | [@marritau](https://github.com/marritau) | LLM-планировщик |
| Shopping & Validator | Александра Федорова | [@fedorova-av](https://github.com/fedorova-av) | корзина, Python-проверка и LLM-критик |
| Integration & UI | Анастасия Сергеева | [@asastyy](https://github.com/asastyy) | workflow, Streamlit, Docker и тестирование |

## Как работает MVP

`search_recipes → LLM planner → Python validator → LLM critic → повторное планирование`

- Поиск фильтрует рецепты по диете и времени приготовления.
- Планировщик выбирает только ID из найденных кандидатов.
- Python масштабирует количества, вычитает запасы, считает корзину и проверяет
  бюджет, единицы, цены, диету и заполненность меню.
- При нарушениях отдельный критик формирует рекомендации. Он не меняет расчёты.
- Цикл ограничен двумя попытками; интерфейс показывает обе оценки.

По умолчанию включён `MOCK_LLM=true`: приложение полностью работает офлайн и
не обращается к внешней модели. Mock нужен для разработки и автотестов. Полный
live-цикл с Gemini проверен 23 октября 2026; протокол находится в
[docs/ROLE_4_VALIDATION.md](docs/ROLE_4_VALIDATION.md).

## Локальный запуск

Нужен Python 3.11 или новее. Из корня репозитория:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m streamlit run app.py
```

В Windows PowerShell используйте `\.venv\Scripts\Activate.ps1` и
`Copy-Item .env.example .env`. Откройте http://localhost:8501.

## Gemini

Получите ключ в [Google AI Studio](https://aistudio.google.com/apikey) и
измените только локальный `.env`:

```dotenv
MOCK_LLM=false
LLM_API_KEY=YOUR_LOCAL_GEMINI_KEY
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-3.5-flash-lite
CRITIC_MODEL=gemini-3.5-flash-lite
```

Ключ нельзя добавлять в Git. `CRITIC_MODEL` можно оставить пустым: тогда критик
использует `LLM_MODEL`. После изменения `.env` перезапустите приложение.
Подробности и smoke-тест описаны в [docs/CRITIC.md](docs/CRITIC.md).

## Docker

Запустите Docker Desktop, затем:

```bash
cp .env.example .env
docker compose up --build
```

Проверка: `curl --fail http://localhost:8501/_stcore/health`.
Остановка: `docker compose down`.

## Проверки

```bash
python -m pytest -q
python scripts/check_data.py
python scripts/run_foodcom.py
```

Шаблон GitHub Actions лежит в `docs/github-tests.yml`. Чтобы включить CI, его
нужно перенести в `.github/workflows/tests.yml` с GitHub-токеном, имеющим право
`workflow`.

## Ограничения данных

Цены в CU синтетические и не являются ценами магазинов. Исходный набор не
содержит инструкций приготовления. Часть количеств обозначена `pcs`, поэтому
интерфейс явно показывает единицы и предупреждение о качестве данных. Если цены
или единицы несовместимы, итоговая стоимость остаётся неизвестной, а Python
возвращает отдельное нарушение.

Контракты: [docs/CONTRACTS.md](docs/CONTRACTS.md). Интеграция роли 4:
[docs/ROLE_4.md](docs/ROLE_4.md). Сценарий Project Proposal:
[docs/PROJECT_PROPOSAL.md](docs/PROJECT_PROPOSAL.md). Готовая презентация:
[docs/Smart_Grocery_Agents_Project_Proposal.pptx](docs/Smart_Grocery_Agents_Project_Proposal.pptx).
Проверка требований:
[docs/COURSE_REQUIREMENTS_AUDIT.md](docs/COURSE_REQUIREMENTS_AUDIT.md). Требования курса:
https://github.com/AlgazinovAleksandr/LLM-Agents-Course/blob/main/GROUP_PROJECT.md
