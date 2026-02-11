import os
import sys
import psutil
from pathlib import Path
from typing import List
from fastmcp import Context

# will be imported from main
logger = None
norm_path = None
withinAllowed = None

def _init_systemmonitoring(logger_instance, norm_path_func, withinAllowed_func):
    """Initialize system monitoring with imports from main."""
    global logger, norm_path, withinAllowed
    logger = logger_instance
    norm_path = norm_path_func
    withinAllowed = withinAllowed_func

SENSITIVE_EXTENSIONS = {'.pem', '.key', '.shadow', '.env', '.id_rsa'}

async def validate_path(path_str: str, ctx: Context) -> Path:
    """
    Перевіряє шлях на відповідність вимозі безпеки
    Викидає виключення, якщо шлях небезпечний.
    """
    try:
        # Нормалізація шляху
        target_path = norm_path(path_str)
    except Exception as e:
        raise ValueError(f"Invalid path syntax: {e}")

    #  (R1.3)
    is_allowed = await withinAllowed(target_path, ctx)
    
    if not is_allowed:
        # JSON error for client (R2.3)
        raise PermissionError(f"Access denied: Path '{path_str}' is not in allowed roots.")

    # (R2.6)
    if target_path.suffix in SENSITIVE_EXTENSIONS:
        raise PermissionError(f"Access denied: Access to sensitive file type '{target_path.suffix}' is prohibited.")

    return target_path

def get_cpu_usage() -> float:
    """
    [R1.1] Повертає поточне завантаження процесора у відсотках.
    """
    try:
        # interval=1 забезпечує точність вимірювання (блокуючий виклик)
        return psutil.cpu_percent(interval=1)
    except Exception as e:
        logger.error(f"Error getting CPU usage: {e}")
        return -1.0
    
def get_memory_usage() -> dict:
    """Повертає інформацію про використання оперативної пам'яті."""
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "percent": mem.percent
    }

async def read_log_file(path: str, lines: int = 100, ctx: Context = None) -> str:
    """
    [R1.2] Читає останні N рядків з лог-файлу.
    
    Args:
        path: Абсолютний шлях до файлу.
        lines: Кількість останніх рядків для читання (default: 100).
    """
    try:
        # (R1.3, R2.6)
        target_path = await validate_path(path, ctx)

        if not target_path.exists():
            return f"Error: File '{path}' not found." # R2.3 Reliability
        
        if not target_path.is_file():
            return f"Error: '{path}' is not a file."

        # (спрощена реалізація tail)
        # поки що читання повного файлу + зріз
        try:
            content = target_path.read_text(encoding='utf-8', errors='replace')
            all_lines = content.splitlines()
            
            # (Test Case D_06)
            if lines < 0:
                return "Error: Lines count cannot be negative."
                
            last_lines = all_lines[-lines:] if lines > 0 else []
            
            return "\n".join(last_lines)
            
        except Exception as read_err:
            return f"Error reading file content: {read_err}"

    except PermissionError as pe:
        return f"Security Error: {str(pe)}"
    except Exception as e:
        return f"System Error: {str(e)}"

def register_tools(mcp):
    """Register all system monitoring tools with the MCP instance."""
    mcp.tool()(get_cpu_usage)
    mcp.tool()(get_memory_usage)
    mcp.tool()(read_log_file)