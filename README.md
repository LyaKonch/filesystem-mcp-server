# MCP Filesystem Server

Сервер Model Context Protocol (MCP), який надає контрольований доступ до файлової системи, інструменти системного моніторингу та керування дозволеними root-директоріями.

## Архітектура та структурні елементи

Проєкт включає:
- **Application server:** Python + FastMCP (`main.py`) з інструментами файлової системи та моніторингу.
- **Web/server transport layer:** `stdio`, `sse` або `http` (налаштовується через `--transport`).
- **Файлове сховище:** локальна файлова система (операції читання/запису в межах `ALLOWED_ROOTS`).
- **Сервіс кешування (опційно):** Redis для persistent auth/session storage.
- **База даних:** не використовується в поточній архітектурі (стан зберігається в Disk/Redis storage).
- **Інші компоненти:** middleware для auth/access control, модулі логування, CI workflow.

```mermaid
flowchart LR
    C[MCP Client\nClaude/Cursor/etc] --> T{Transport\nstdio/sse/http}
    T --> S[FastMCP Server\nmain.py]

    S --> A[Auth Layer\nauth/*]
    S --> F[Filesystem Tools\ntools/filesystem.py]
    S --> M[Monitoring Tools\ntools/monitoring.py]
    S --> R[Server Management\ntools/server_management.py]

    A --> DS[(Disk Storage)]
    A --> RS[(Redis, optional)]
    F --> FS[(Allowed Roots\nLocal File System)]
```

## Вимоги до середовища

- Git
- Python 3.13+
- `pip` або `uv`
- (Опційно) Redis 7+ для persistent storage

## Швидкий старт

```
git clone https://github.com/LyaKonch/filesystem-mcp-server
cd filesystem-mcp-server

uv sync
# прослідкуйте щоб віртуальне середовище було активовано

python main.py --allow-cwd --no-auth
```

Без uv:
```bash
git clone <repository-url>
cd filesystem-mcp-server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
cp .env.example .env
# .env файл потрібно налаштувати під себе
python main.py --allow-cwd --no-auth --transport stdio
```

```powershell
git clone <repository-url>
cd filesystem-mcp-server
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
Copy-Item .env.example .env
# .env файл потрібно налаштувати під себе
python .\main.py --allow-cwd --no-auth --transport stdio
```

## Налаштування конфігурації

Основні параметри задаються як через `.env`:
- `MCP_HOST`, `MCP_PORT`, `TRANSPORT`
- `AUTH_ENABLED`
- `ALLOWED_ROOTS`
- `USE_PERSISTENT_STORAGE`, `USE_REDIS`, `REDIS_HOST`, `REDIS_PORT`
- `LOG_LEVEL`, `LOG_JSON`, `LOG_FILE`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`
- `ERROR_LOCALE` (`uk` або `en`) для локалізації користувацьких повідомлень про помилки
- `ERROR_REPORTS_FILE` (шлях до JSONL-файлу звітів про помилки від користувачів)
- `ALERT_WEBHOOK_URL`, `ALERT_WEBHOOK_TIMEOUT_SEC` (вебхук для оповіщень про `CRITICAL` помилки)


Так і через CLI прапорці:
| Аргумент | Опис |
| --- | --- |
| `roots` | Шляхи до дозволених директорій (наприклад `python --roots main.py /path/to/dir`). |
| `--allow-cwd` | Дозволити доступ до поточної робочої директорії. |
| `--no-auth` | Рекомендовано. Вимикає аутентифікацію (корисно, якщо виникають помилки з токенами). |
| `--transport` | Тип транспорту: `stdio` (за замовчуванням), `http` або `sse`. |
| `--host`, `--port` | Хост та порт для HTTP/SSE (за замовчуванням `127.0.0.1:8000`). |
| `--persist` | Зберігати стан сервера (дозволені клієнти) між перезапусками. |
| `--debug` | Увімкнути детальне логування для розробки. |
| `--log-level` | Мінімальний рівень логування: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `--log-json` | Увімкнути JSON-формат логів (консоль + файл). |

## Логування та обробка помилок

- Логування налаштовано централізовано через `logging.config.dictConfig` (`utilities/logging.py`).
- Мінімальний рівень логування можна змінити без перекомпіляції через `.env` (`LOG_LEVEL`) або CLI (`--log-level`).
- Логи пишуться в:
  - `stdout` для `DEBUG/INFO`
  - `stderr` для `WARNING/ERROR/CRITICAL`
  - файл `LOG_FILE` через `RotatingFileHandler`
- Ротація логів: `LOG_MAX_BYTES` (макс. розмір файлу) + `LOG_BACKUP_COUNT` (кількість бекапів).
- Підтримується контекст логування: `request_id`, `user_id`, `operation`.
- Для необроблених винятків встановлено глобальні hooks (`sys.excepthook`, `threading.excepthook`) з `error_id` (UUID).
- Для критичних помилок сервера у `main.py` записується `error_id`, який можна дати користувачу для діагностики.
- Для tool-викликів помилки проходять через єдиний error-boundary: користувач отримує локалізоване повідомлення, `Error ID`, короткі кроки відновлення та підказку повідомити ID у підтримку.
- Для `CRITICAL` логів підтримано опційні webhook-оповіщення (якщо задано `ALERT_WEBHOOK_URL`).
- Додано механізм збору технічних даних від користувача через tool `submit_error_report` (summary, error_id, кроки відтворення, system info, attachments) зі збереженням у `ERROR_REPORTS_FILE`.

Для локальної розробки рекомендований режим:
- `--no-auth`
- `--allow-cwd`
- `--transport stdio`

Приклад команди для запуску в режимі http server:
```bash
python main.py --transport http --host 127.0.0.1 --port 8000 --persist
```

## Доступні інструменти (Tools)

Нижче — перелік реальних інструментів, які експортуються з коду сервера (груповано за функціональністю). Кожен інструмент захищений політиками доступу — перед використанням перевіряйте права та обмеження.

### Файлова система
- `list_files` — Переглядає вміст директорії (фільтри, рекурсія, розміри).
- `get_path_info` — Детальна інформація та метадані про файл/папку.
- `read_file` — Читання файлу (опція включення опису зображень, обмеження за розміром).
- `write_file` — Створення / перезапис / додавання до файлу.
- `edit_file` — Безпечна заміна текстового блоку в файлі.
- `create_directory` — Створення директорії.
- `move_file` — Переміщення / перейменування файлу або папки.
- `search_files` — Пошук тексту в файлах каталогу.
- `delete_path` — Видалення файлу або (за рекурсією) папки.

### Процеси
- `run_admin_shell` — (Адмін) виконати сиру shell-команду.
- `start_process` — Запустити процес з аргументами.
- `get_available_commands` — Повертає перелік дозволених команд.
- `kill_process` — Завершити процес (з підтвердженням).
- `suspend_process` — Призупинити процес.
- `resume_process` — Відновити процес.
- `kill_process_tree` — Завершити процес і його нащадків.
- `list_processes` — Повертає короткі резюме запущених процесів.
- `get_current_username` — Ім'я користувача, від якого запущений сервіс.
- `get_process_info` — Розширена інформація про процес.
- `get_detailed_process_info` — Глибока діагностика процесу (дерево, з'єднання, відкриті файли).
- `get_process_connections` — Мережеві з'єднання процесу.
- `get_process_tree` — Дерево процесів.
- `get_process_open_files` — Файли, відкриті процесом.

### Моніторинг
- `get_system_resource_usage` — CPU/RAM у реальному часі.
- `get_disk_status` — Статус і простір дисків.
- `get_system_info` — Статична інформація про систему та аптайм.

### Служби (Windows)
- `list_services` — Пошук/фільтрація сервісів.
- `get_service_status` — Статус одного сервісу.
- `start_service` / `stop_service` / `restart_service` — Керування сервісом.
- `stop_service_with_deps` — Зупинити сервіс з залежностями.
- `change_service_startup_type` / `change_service_config` — Змінити конфіг/тип запуску.
- `get_service_logs` — Отримати події з журналу додатків для сервісу.
- `create_service` / `delete_service` — Створення/видалення сервісу.
- `wrap_script_as_service` — Загорнути скрипт як Windows service.

### Реєстр (Windows)
- `list_registry_key` — Перегляд підключів і значень ключа.
- `read_registry_key` — Прочитати конкретне значення.
- `write_registry_key` — Записати значення (вимагає підтвердження).
- `delete_registry_key` — Видалити значення.
- `get_registry_value_types` — Повернути допустимі типи значень.
- `get_registry_hive_path` — Отримати відповідність hive-namespace.
- `check_key_exists` — Перевірити наявність ключа.

### Система / Змінні середовища (Windows)
- `get_variable` — Отримати значення змінної оточення (PROCESS/USER/SYSTEM).
- `list_variables` — Перелік змінних для вказаного scope.
- `set_variable` — Встановити змінну (PROCESS/USER/SYSTEM).
- `delete_variable` — Видалити змінну.
- `create_windows_restore_point` — Створити restore point (потрібні права адміністратора).

### Керування сервером
- `get_server_status` — Статус MCP-сервера та клієнтські features.
- `list_allowed_roots` — Показати дозволені root-директорії.
- `add_allowed_root` / `update_roots` / `remove_root` — Керування whitelist-ом коренів.
- `submit_error_report` — Надіслати технічний звіт (з `error_id`).


## Налаштування MCP Клієнта (Claude Desktop / Cursor)

### Рекомендована конфігурація (STDIO)

Найпростіший спосіб без проблем з портами та токенами.

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "python",
      "args": [
        "absolute/path/to/main.py",
        "--allow-cwd",
        "--no-auth"
      ]
    }
  }
}
```

Не забудьте вказати повний шлях до python (наприклад `.venv/Scripts/python`), якщо використовуєте віртуальне середовище.

### Конфігурація через HTTP (SSE)

Якщо ви запускаєте сервер окремо (`python main.py --transport http --port 8000 --persist`).

```json
{
  "mcpServers": {
    "filesystem-http": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://127.0.0.1:8000/mcp"
      ]
    }
  }
}
```

Зверніть увагу на `/mcp` в кінці URL.

## Налаштування авторизації (GitHub OAuth)

Для налаштування мехінізму авторизації дивіться офіційний гайд:
https://gofastmcp.com/integrations/github

Рекомендовано створити файл `.env` в корені сервера. `config.py` автоматично підтягне всі змінні.

Нюанси налаштування:
- Потрібен GitHub OAuth App з коректним callback URL згідно гайду.
- Заповніть `FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID` та `FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET` у `.env`.
- Встановіть `FASTMCP_SERVER_AUTH_GITHUB_BASE_URL` на базовий URL сервера (для локального тесту зазвичай `http://127.0.0.1:8000`).
- Для персистентної авторизації потрібні `JWT_SIGNING_KEY` та `STORAGE_ENCRYPTION_KEY` і запуск з `--persist`.
- Якщо використовуєте Redis( не стабільне, не протестовано), задайте параметром `--redis` і задай `REDIS_HOST`/`REDIS_PORT`.
- Для локального dev можна( і бажано ) запускати з `--no-auth`, якщо виникають помилки токенів.

## Вирішення проблем

### 🔑 Проблеми з аутентифікацією (Invalid Token / Client Not Registered)

Якщо ви бачите помилки `invalid_token` або `Client Not Registered`:

1. Зупиніть сервер.
2. Запустіть його з прапорцем `--no-auth`.
3. Оновіть конфіг клієнта, щоб він не очікував auth-flow.

Інколи буває, що інструмент mcp-remote кешує client-id в своїх конфігах, а на сервері цього користувача не впізнають, так як токени авторизації у сховищі були втрачені або змінені. В таких випадках єдиним виходом є очищення кешу mcp-remote, як правило за шляхом `~/.mcp-auth/mcp-remote-<version>`.

Для траблшутінгу інших незазначених проблем переходьте за посиланням:
`https://docs.scalekit.com/authenticate/mcp/troubleshooting/`  

Аутентифікація через GitHub зараз знаходиться в стадії активної розробки. Для стабільної роботи локально рекомендується її вимикати.

### 🌐 Помилка "Connection Refused" або 404

Переконайтеся, що ви вказуєте правильний порт і шлях. За замовчуванням сервер слухає порт 8000 і шлях `/mcp`.

- Неправильно: `http://127.0.0.1/`
- Правильно: `http://127.0.0.1:8000/mcp`

### 🔒 Access Denied / Path not allowed

Сервер дозволяє доступ тільки до тек, вказаних при запуску або доданих динамічно.

- Використовуйте `list_allowed_roots()`, щоб побачити, куди є доступ.
- Використовуйте `add_allowed_root("/path/to/dir")`, щоб надати доступ.


### Перевірка конфігурації

Після налаштування mcp.json:

1. **Перезапустіть MCP клієнт** (Claude Desktop, Cursor тощо)
2. **Перевірте підключення:**
   - Використайте інструмент `get_client_features()` для перевірки можливостей
   - Викличте `get_allowed_roots()` для перевірки доступних директорій
3. **Протестуйте базові операції:**
   - `list_files(".")` - перегляд файлів
   - `read_file("README.md")` - читання файлу

### Налагодження конфігурації

#### Проблема: Сервер не запускається
**Рішення:**
- Перевірте правильність шляхів в `command` та `args`
- Переконайтеся, що Python та залежності встановлені
- Перевірте права доступу до файлів

#### Проблема: "No allowed roots specified"  
**Рішення:**
- Додайте директорії в `args` або використайте `--allow-cwd`
- Переконайтеся, що шляхи існують і доступні

#### Проблема: "Path is not within allowed roots"
**Рішення:**
- Перевірте список дозволених коренів через `get_allowed_roots()`
- Додайте необхідні директорії в конфігурацію


## Підтримка

Якщо у вас виникли питання або проблеми:
1. Перевірте розділ "Вирішення проблем" вище
2. Відвідайте [документацію FastMCP](https://gofastmcp.com) для детальної інформації
3. Створіть issue в репозиторії

---

**Примітка:** Цей сервер призначений для використання в безпечному середовищі. Завжди перевіряйте права доступу та обмежуйте доступ тільки до необхідних директорій.

## Документація для DevOps та експлуатації

- [Production deployment guide](docs/deployment.md)
- [Update and rollback guide](docs/update.md)
- [Backup and restore guide](docs/backup.md)
- [Automation scripts](docs/scripts)

## Розширена технічна документація

- [Технічне бачення та взаємодія компонентів](docs/technical_design.md)
- [Лінтинг і статичні перевірки](docs/linting.md)
- ["Жива" документація через тести (Test-Driven Documentation)](docs/test_driven_documentation.md)
- [Автоматична публікація документації (CI/CD + GitHub Pages)](docs/docs_publishing.md)
- [Інструкція генерації документації](docs/generate_docs.md)
## Container та інфраструктурні конфіги

- `dockerfile`
- `docker-compose.yml`
- `docs/k8s/`
- `docs/terraform/`
- `.github/workflows/quality.yml`

## Політика документування в проєкті

- `README.md` описує onboarding розробника та основні операційні кроки.
- `docs/*.md` містять експлуатаційні інструкції для DevOps.
- Зміни в конфігурації або процесах деплою мають супроводжуватися оновленням відповідних файлів у `docs/`.

### Стандарт документування коду

У проєкті використовується **Google Style docstring** для Python-коду.

Обов'язково документуємо:

- публічні функції;
- публічні методи;
- публічні класи;
- фабрики/реєстратори інструментів (наприклад `register(...)`, `create_...(...)`).

Мінімальна структура docstring:

```python
"""Короткий опис дії.

Args:
  arg1: Що це за параметр.

Returns:
  Тип: Що повертає функція.
"""
```

Рекомендації:

- Перший рядок — коротка дія в наказовому стилі (наприклад: "Get ...", "Create ...", "Validate ...").
- Для асинхронних функцій формат такий самий, як для звичайних.
- Якщо функція може кидати важливі винятки, додавайте секцію `Raises`.
- Якщо docstring вже існує не в Google Style, його треба **оновити**, а не дублювати.

### Правило для внесків у репозиторій

Кожен PR, що змінює публічний API, має також:

1. Оновити/додати docstring у Google Style.
2. Оновити опис у `README.md`/`docs/*.md`, якщо змінилась поведінка або контракти API.