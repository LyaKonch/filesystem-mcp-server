import pytest
import asyncio
import logging
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
import tests.systemmonitoring as systemmonitoring
import os

logger = logging.getLogger("test_systemmonitoring")
# --- Фікстури (Налаштування) ---

@pytest.fixture
def mock_deps():
    """Імітація залежностей з main.py"""
    mock_logger = MagicMock()
    
    # Імітуємо norm_path: просто повертає Path об'єкт
    def fake_norm_path(p):
        return Path(p)
    
    # Імітуємо withinAllowed: це async функція
    # За замовчуванням повертає True (дозволено)
    mock_within_allowed = AsyncMock(return_value=True)

    return mock_logger, fake_norm_path, mock_within_allowed

@pytest.fixture(autouse=True)
def setup_module(mock_deps):
    """Ініціалізуємо модуль перед кожним тестом"""
    logger, norm_path, within_allowed = mock_deps
    systemmonitoring._init_systemmonitoring(logger, norm_path, within_allowed)
    return logger, norm_path, within_allowed

# --- Тести CPU (R1.1) ---

@patch('psutil.cpu_percent')
def test_get_cpu_usage_valid(mock_cpu):
    """
    Перевіряє, чи функція повертає коректне число (float),
    і чи викликається psutil з правильними параметрами.
    """
    # Налаштовуємо мок, щоб він повернув типове значення
    mock_cpu.return_value = 42.5
    
    result = systemmonitoring.get_cpu_usage()
    logger.info("cpu_usage_valid: result=%s", result)
    
    # Перевірка типу
    assert isinstance(result, float), f"Очікував float, отримав {type(result)} зі значенням {result}"
    # Перевірка діапазону (логічна перевірка)
    assert 0.0 <= result <= 100.0, f"CPU % поза межами 0..100: {result}"
    # Перевірка правильності виклику бібліотеки
    mock_cpu.assert_called_with(interval=1)

@patch('psutil.cpu_percent')
def test_get_cpu_usage_error(mock_cpu, setup_module):
    """Перевіряє обробку помилок (logging + return -1.0)"""
    logger, _, _ = setup_module
    # Імітуємо помилку бібліотеки psutil
    mock_cpu.side_effect = Exception("Hardware error")
    
    result = systemmonitoring.get_cpu_usage()
    logger.info("cpu_usage_error: result=%s", result)
    
    assert result == -1.0, "При помилці очікуємо -1.0"
    # Перевіряємо, що помилка була залогована
    logger.error.assert_called_once()

# --- Тести безпеки шляхів (Async) (R1.3, R2.6) ---

@pytest.mark.asyncio
async def test_validate_path_success(setup_module):
    """Позитивний сценарій: шлях дозволений"""
    _, _, mock_within_allowed = setup_module
    mock_ctx = MagicMock()
    
    # залежно від ОС використовуємо відповідний шлях
    if os.name == "nt":
        path_str = "\\var\\log\\syslog"
    else:
        path_str = "/var/log/syslog"
    result = await systemmonitoring.validate_path(path_str, mock_ctx)
    
    logger.info("validate_path_success: input=%s resolved=%s", path_str, result)
    assert isinstance(result, Path), f"Очікував Path, отримав {type(result)}"
    assert str(result) == path_str, f"Шлях після нормалізації змінився: {result}"

@pytest.mark.asyncio
async def test_validate_path_access_denied(setup_module):
    """Негативний сценарій: шлях не в allowed roots (R1.3)"""
    _, _, mock_within_allowed = setup_module
    mock_ctx = MagicMock()
    
    # Імітуємо, щоб не пройшло функцію перевірки дозволених директорій 
    mock_within_allowed.return_value = False
    
    with pytest.raises(PermissionError) as exc:
        await systemmonitoring.validate_path("/etc/shadow", mock_ctx)
    logger.info("validate_path_access_denied: exc=%s", exc.value)
    assert "not in allowed roots" in str(exc.value), f"Отримано інше повідомлення: {exc.value}"

@pytest.mark.asyncio
async def test_validate_path_sensitive_extension(setup_module):
    """Негативний сценарій: чутливе розширення файлу (R2.6)"""
    mock_ctx = MagicMock()
    
    with pytest.raises(PermissionError) as exc:
        await systemmonitoring.validate_path("/var/log/secret.pem", mock_ctx)
    logger.info("validate_path_sensitive_ext: exc=%s", exc.value)
    assert "sensitive file type" in str(exc.value), f"Отримано інше повідомлення: {exc.value}"

# --- Тести читання логів (R1.2, R2.3) ---

@pytest.mark.asyncio
async def test_read_log_file_success(setup_module):
    """Тест успішного читання файлу"""
    mock_ctx = MagicMock()
    
    # імітуємо методи Path всередині systemmonitoring
    # оскільки ми не можемо легко зімітувати об'єкт Path, створений всередині функції,
    # то будемо мокати системні виклики через patch
    
    with patch('pathlib.Path.exists', return_value=True), \
         patch('pathlib.Path.is_file', return_value=True), \
         patch('pathlib.Path.read_text', return_value="Line 1\nLine 2\nLine 3"):
        
        result = await systemmonitoring.read_log_file("/tmp/test.log", lines=2, ctx=mock_ctx)
        logger.info("read_log_success: result=%s", result)
        
        assert result == "Line 2\nLine 3", f"Невірний зріз рядків: {result}"

@pytest.mark.asyncio
async def test_read_log_file_not_found():
    """Тест R2.3: Файл не знайдено (Reliability)"""
    mock_ctx = MagicMock()
    
    with patch('pathlib.Path.exists', return_value=False):
        result = await systemmonitoring.read_log_file("/tmp/missing.log", ctx=mock_ctx)
        logger.info("read_log_not_found: result=%s", result)
        
        assert "Error: File" in result, "Очікувано повідомлення про відсутній файл"
        assert "not found" in result, f"Отримано інше повідомлення: {result}"

@pytest.mark.asyncio
async def test_read_log_negative_lines():
    """Тест крайового випадку: від'ємна кількість рядків"""
    mock_ctx = MagicMock()
    
    with patch('pathlib.Path.exists', return_value=True), \
         patch('pathlib.Path.is_file', return_value=True), \
         patch('pathlib.Path.read_text', return_value="content"):
         
        result = await systemmonitoring.read_log_file("/tmp/test.log", lines=-5, ctx=mock_ctx)
        logger.info("read_log_negative_lines: result=%s", result)
        assert "cannot be negative" in result, f"Очікували попередження про від'ємні рядки, отримали: {result}"