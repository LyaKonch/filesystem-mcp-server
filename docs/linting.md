# Linting in filesystem-mcp-server

## Обраний лінтер та причини вибору

Для проєкту обрано **Ruff**.

Причини вибору:
- дуже висока швидкість перевірки великих Python-проєктів;
- підтримка багатьох категорій правил в одному інструменті;
- наявність автоматичних виправлень (`--fix`);
- проста інтеграція через `pyproject.toml`;
- зручно використовувати в локальній розробці та CI.

## Базові правила та пояснення

Поточна конфігурація Ruff у `pyproject.toml`:

- `line-length = 100` — обмеження довжини рядка.
- `target-version = "py313"` — орієнтація на Python 3.13.
- `exclude = ["__pycache__", ".pytest_cache", ".venv", "tests"]` — каталоги/файли, які не перевіряються.

`[tool.ruff.lint]`:
- `select = ["E", "F", "I", "UP", "B"]`
  - `E` — стильові помилки (pycodestyle);
  - `F` — логічні помилки (pyflakes), зокрема невикористані імпорти/змінні;
  - `I` — порядок імпортів (isort);
  - `UP` — рекомендації з оновлення синтаксису Python;
  - `B` — потенційно небезпечні або підозрілі конструкції (bugbear).
- `ignore = ["E501"]` — ігнорується перевищення довжини рядка.

`[tool.ruff.lint.per-file-ignores]`:
- `"__init__.py" = ["F401"]` — дозволяє реекспорт імпортів в `__init__.py`.

## Інструкція з запуску лінтера

1. Перейти в корінь проєкту і активувати віртуальне середовище:

```powershell
.\.venv\Scripts\Activate.ps1
```

2. Запустити перевірку:

```powershell
python -m ruff check .
```

3. Отримати статистику за типами порушень:

```powershell
python -m ruff check . --statistics
```

4. Автоматично виправити те, що підтримується:

```powershell
python -m ruff check . --fix
```

5. (Опційно) застосувати unsafe-виправлення:

```powershell
python -m ruff check . --fix --unsafe-fixes
```

6. Перевірити, що після виправлень не з'явились нові порушення:

```powershell
python -m ruff check . --statistics
```

## Git hooks

Для автоматичного запуску перевірок перед комітом додано конфігурацію `.pre-commit-config.yaml`.
Вона запускає:
- `ruff-check --fix`
- `ruff-format`
- `mypy`

Налаштування хуків локально:

```powershell
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

стандартно pre-commit запускається перед створенням коміту

## Інтеграція з процесом збірки

Лінтинг і перевірки інтегровано у CI через GitHub Actions файл `.github/workflows/quality.yml`.
Pipeline виконує послідовно:
1. `ruff check .`
2. `ruff format . --check`
3. `mypy .`

Це гарантує, що у процес збирання та перевірки змін потрапляє тільки код, який проходить лінтинг і статичну типізацію.

## Статична типізація

Для проєкту додано `mypy` та базову конфігурацію в `pyproject.toml` (`[tool.mypy]`).
Базовий запуск:

```powershell
python -m mypy .
```

`mypy` використовується як локально (через pre-commit), так і автоматично у CI при кожному push або pull request.
