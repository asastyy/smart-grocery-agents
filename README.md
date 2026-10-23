<p align="center">
  <img src="docs/assets/banner.svg" alt="Smart Grocery Agents — меню и покупки с учётом ваших условий" width="100%">
</p>

<p align="center">
  <a href="#быстрый-запуск"><strong>Запустить</strong></a> ·
  <a href="#как-это-работает"><strong>Архитектура</strong></a> ·
  <a href="docs/README.md"><strong>Документация</strong></a> ·
  <a href="https://docs.google.com/presentation/d/1QU-fQJcm-VKNGzv8_Ejyq7r1cKUuGAjGJn_jeBWml0M/edit"><strong>Презентация</strong></a>
</p>

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-1f6f5b?style=flat">
  <img alt="Streamlit" src="https://img.shields.io/badge/UI-Streamlit-1f6f5b?style=flat">
  <img alt="Google Gemini" src="https://img.shields.io/badge/LLM-Google%20Gemini-1f6f5b?style=flat">
  <a href="LICENSE"><img alt="Лицензия MIT" src="https://img.shields.io/badge/License-MIT-1f6f5b?style=flat"></a>
</p>

**Smart Grocery Agents** составляет меню и список покупок по домашним запасам,
бюджету, ограничениям питания и времени приготовления. Gemini выбирает блюда
и предлагает исправления, Python рассчитывает корзину и проверяет условия.

> **Учебный MVP.** Приложение запускается локально. Цены демонстрационные,
> в условных единицах CU. Общедоступная версия на сервере пока не опубликована.

## Возможности

| Вы задаёте | Получаете |
|---|---|
| Продукты, которые уже есть дома | Покупки с учётом запасов |
| Число дней и людей | Обеды и ужины с расчётом порций |
| Бюджет, диету и время | Подбор допустимых рецептов и проверку меню |
| Изменённые ограничения | Повторный расчёт и историю попыток |

**Запасы и параметры**

![Smart Grocery Agents: домашние запасы и параметры меню](docs/assets/app-preview.png)

**Меню по дням**

![Smart Grocery Agents: карточки блюд и полное меню таблицей](docs/assets/app-menu.png)

## Быстрый запуск

Нужны Git и запущенный Docker Desktop. Подготовленные данные включены
в репозиторий; для первого запуска API-ключ не требуется.

```bash
git clone https://github.com/asastyy/smart-grocery-agents.git
cd smart-grocery-agents
cp .env.example .env
docker compose up --build
```

Откройте **[localhost:8501](http://localhost:8501)**. По умолчанию включён
демонстрационный режим (`MOCK_LLM=true`). Остановка: `docker compose down`.

<details>
<summary><strong>Запуск без Docker · Python 3.11+</strong></summary>

Из корня скачанного репозитория:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m streamlit run app.py
```

В Windows PowerShell активация: `.\.venv\Scripts\Activate.ps1`.
Для копирования настроек используйте `Copy-Item .env.example .env`.
Та же команда копирования подходит для Docker в Windows.

</details>

### Подключить Gemini

Получите ключ в [Google AI Studio](https://aistudio.google.com/apikey)
и заполните локальный `.env`. Текущая конфигурация команды использует
Google Gemini `gemini-3.5-flash-lite` через совместимый с OpenAI API интерфейс.

```dotenv
MOCK_LLM=false
LLM_API_KEY=YOUR_LOCAL_GEMINI_KEY
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-3.5-flash-lite
CRITIC_MODEL=
```

Пустой `CRITIC_MODEL` означает ту же модель, что у планировщика. После изменения
`.env` перезапустите Streamlit или контейнер (`docker compose up --force-recreate`).
Экспортированные переменные окружения имеют приоритет над `.env`.

Ключ хранится только локально. `.env` исключён из Git, `.env.example` содержит
шаблон. [Настройка и проверка критика →](docs/CRITIC.md)

## Как это работает

```mermaid
flowchart LR
    U["Запасы и ограничения"] --> S["Поиск рецептов"]
    S --> P["Планировщик · Gemini"]
    P --> V["Корзина и проверка · Python"]
    V -->|"Условия выполнены"| R["Меню и покупки"]
    V -->|"Нарушения"| C["Критик · Gemini"]
    C -->|"Одна повторная попытка"| P
    V -->|"Лимит попыток"| E["Результат с нарушениями"]
```

1. **Поиск** отбирает рецепты по диете и времени.
2. **Планировщик** выбирает ID из кандидатов. Ответ проверяется по схеме.
3. **Python** рассчитывает порции, вычитает запасы, проверяет стоимость,
   единицы, бюджет и заполненность меню.
4. **Критик** получает нарушения и рекомендует изменить выбор. Цикл ограничен
   двумя попытками; обе видны в истории.

### Зачем здесь LLM

Фильтры находят допустимые рецепты. LLM составляет меню из кандидатов
и пересматривает его по текстовым замечаниям. Планировщик и критик выполняют
разные роли; расчёты и итог проверки принадлежат Python.

Для короткого цикла достаточно обычного Python.
[Модули, границы ответственности и обработка сбоев →](docs/ARCHITECTURE.md)

## Данные и границы MVP

| Рецепты Food.com | Нормализованные ингредиенты | Демонстрационные цены |
|:---:|:---:|:---:|
| **150** | **503** | **503** |

- Цены в CU синтетические и не отражают цены магазинов.
- Часть количеств задана в штуках (`pcs`). Пошаговых инструкций приготовления
  в исходном наборе нет.
- Неизвестные цены и несовместимые единицы дают отдельное нарушение.
  Неполная стоимость отображается явно.
- В демонстрационном режиме API не вызывается. Для показа LLM-функции
  включите Gemini.

[Источник, подготовка и пересборка данных →](docs/DATA_NOTES.md)

## Структура проекта

```text
smart-grocery-agents/
├── app.py                 # интерфейс Streamlit
├── src/smart_grocery/
│   ├── agents/            # планировщик, проверка, критик
│   ├── tools/             # поиск и расчёт корзины
│   ├── schemas/           # модели данных
│   └── workflow/          # цикл планирования и проверки
├── data/                  # подготовленные рецепты, ингредиенты и цены
├── fixtures/              # запросы и ответы для проверок
├── tests/                 # модульные и интеграционные тесты
├── scripts/               # подготовка данных и запуск сценариев
├── examples/              # небольшие примеры данных
├── docs/                  # документация и материалы защиты
├── Dockerfile
├── compose.yaml
└── .env.example
```

## Проверки

После установки Python-зависимостей из корня проекта:

```bash
python -m pytest -q
python scripts/check_data.py
MOCK_LLM=true python scripts/run_foodcom.py
```

Последняя подтверждённая проверка к защите: **91 тест**, запуск Docker
и настоящий цикл Gemini. [Протокол →](docs/ROLE_4_VALIDATION.md)

Шаблон автоматических проверок: [`docs/github-tests.yml`](docs/github-tests.yml).
GitHub Actions пока не включён: для публикации workflow нужно соответствующее
право GitHub-токена.

## Команда

| Участник | GitHub | Ответственность |
|---|---|---|
| Афонин Максим Константинович | [@jeweller9](https://github.com/jeweller9) | Данные и поиск рецептов |
| Уразметова Маргарита Руслановна | [@marritau](https://github.com/marritau) | LLM-планировщик меню |
| Федорова Александра Вадимовна | [@fedorova-av](https://github.com/fedorova-av) | Корзина, проверка и LLM-критик |
| Сергеева Анастасия Вадимовна | [@asastyy](https://github.com/asastyy) | Интеграция, интерфейс, Docker и тестирование |

## Документация и защита

| Материал | Содержание |
|---|---|
| [Навигатор документации](docs/README.md) | Все инструкции по разделам |
| [Архитектура](docs/ARCHITECTURE.md) | Процесс и принятые решения |
| [Контракты](docs/CONTRACTS.md) | Форматы данных между модулями |
| [Google Slides](https://docs.google.com/presentation/d/1QU-fQJcm-VKNGzv8_Ejyq7r1cKUuGAjGJn_jeBWml0M/edit) | Рабочая презентация команды |
| [Презентация PPTX](docs/Smart_Grocery_Agents_Project_Proposal.pptx) | Копия для скачивания |
| [Сценарий выступления](docs/PRESENTATION_SCRIPT.txt) | Кто выступает и что говорит |
| [Требования курса](https://github.com/AlgazinovAleksandr/LLM-Agents-Course/blob/main/GROUP_PROJECT.md) | Критерии проекта и защиты |

Хотите внести изменение? [Порядок работы с репозиторием →](CONTRIBUTING.md)

Код проекта распространяется по [лицензии MIT](LICENSE). Источник данных
и сведения об их подготовке приведены отдельно в документации.
