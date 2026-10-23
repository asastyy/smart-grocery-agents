# Документация

[На главную](../README.md)

## Запуск и разработка

| Документ | Когда открыть |
|---|---|
| [Быстрый запуск](../README.md#быстрый-запуск) | Docker или Python |
| [Архитектура](ARCHITECTURE.md) | Процесс и ответственность модулей |
| [Контракты](CONTRACTS.md) | Форматы запросов и ответов |
| [Данные](DATA_NOTES.md) | Источник и подготовка каталога |
| [Критик](CRITIC.md) | Настройка Gemini и проверка рекомендаций |
| [Работа с репозиторием](../CONTRIBUTING.md) | Ветки, проверки и PR |

## Защита MVP

| Материал | Содержание |
|---|---|
| [Google Slides](https://docs.google.com/presentation/d/1QU-fQJcm-VKNGzv8_Ejyq7r1cKUuGAjGJn_jeBWml0M/edit) | Рабочая версия команды |
| [Презентация PPTX](Smart_Grocery_Agents_Project_Proposal.pptx) | Локальная копия |
| [Сценарий](PRESENTATION_SCRIPT.txt) | Речь по слайдам и распределение участников |
| [Подготовка и вопросы](PROJECT_PROPOSAL.md) | Демонстрация и технические ответы |
| [Требования](COURSE_REQUIREMENTS_AUDIT.md) | Сопоставление с критериями курса |
| [Протокол](ROLE_4_VALIDATION.md) | Проверка тестов, Docker и Gemini от 23 октября 2026 |

## Реализация по ролям

Документы ниже описывают отдельные части и историю интеграции. Для текущего
запуска используйте README в корне проекта.

- Данные и поиск: [DATA_NOTES.md](DATA_NOTES.md).
- Планировщик: [ROLE_2.md](ROLE_2.md).
- Корзина и проверка: [ROLE_3.md](ROLE_3.md), [интеграция Food.com](ROLE_3_FOODCOM.md).
- Интерфейс и интеграция: [ROLE_4.md](ROLE_4.md).
- Распределение работ: [TEAM_PLAN.md](TEAM_PLAN.md).
- Ревью корзины и критика: [REVIEW_ROLE_3.md](REVIEW_ROLE_3.md).

## Автоматические проверки

[`github-tests.yml`](github-tests.yml) — шаблон GitHub Actions. Он хранится здесь,
поскольку у использованного токена нет права `workflow`. Участник с нужными
правами может перенести файл в `.github/workflows/tests.yml`. Сейчас проверки
запускаются локально.
