import pytest
import psutil
from pathlib import Path
from unittest.mock import MagicMock
import systemmonitoring

DOCKER_TEST_ROOT = Path("/tmp/mcp_test_env")

@pytest.fixture
def docker_env_setup():
    """тут емулюються функції з main.py для ініціаліхзації systemmonitoring"""
    mock_logger = MagicMock()
    
    def real_norm_path(p):
        return Path(p).resolve()
    
    # Емулюємо дозвіл доступу лише в межах тестової директорії Docker
    async def real_within_allowed(path: Path, ctx):
        try:
            path.resolve().relative_to(DOCKER_TEST_ROOT.resolve())
            return True
        except ValueError:
            return False

    systemmonitoring._init_systemmonitoring(mock_logger, real_norm_path, real_within_allowed)
    return DOCKER_TEST_ROOT

@pytest.mark.asyncio
async def test_integration_read_standard_log(docker_env_setup):
    target_file = str(DOCKER_TEST_ROOT / "logs/standard.log")
    mock_ctx = MagicMock()

    # Перевірка читання останніх N рядків реального файлу
    result = await systemmonitoring.read_log_file(target_file, lines=5, ctx=mock_ctx)
    
    assert "Log line 50" in result
    assert len(result.splitlines()) == 5

@pytest.mark.asyncio
async def test_integration_security_pem_file(docker_env_setup):
    target_file = str(DOCKER_TEST_ROOT / "secrets/key.pem")
    mock_ctx = MagicMock()

    result = await systemmonitoring.read_log_file(target_file, ctx=mock_ctx)
    
    # Файл існує фізично, але має блокуватися на рівні логіки (R2.6)
    assert "Security Error" in result
    assert "sensitive file type" in result

@pytest.mark.asyncio
async def test_integration_read_empty_file(docker_env_setup):
    target_file = str(DOCKER_TEST_ROOT / "logs/empty.log")
    mock_ctx = MagicMock()

    result = await systemmonitoring.read_log_file(target_file, ctx=mock_ctx)
    assert result == ""

def test_integration_psutil_real(mocker):
    # Spy дозволяє виконати реальний код, але відстежити параметри виклику
    spy_cpu = mocker.spy(psutil, 'cpu_percent')
    
    result = systemmonitoring.get_cpu_usage()
    
    assert isinstance(result, float)
    assert 0.0 <= result <= 100.0
    # Перевіряємо, чи дотримано контракт (interval=1 критичний для точності)
    spy_cpu.assert_called_once_with(interval=1)

    
