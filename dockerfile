# беремо образ з Python 3.13 slim
FROM python:3.13-slim

# всі файли будуть в /app
WORKDIR /app 

# встановлення uv, просто копіюємо виконуваний файл з офіційного образу uv 
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# --- Налаштування залежностей ---
COPY pyproject.toml uv.lock* ./
# я використовував pyproject.toml з uv
# але можна використовувати requirements.txt

# Встановлюємо залежності в системне оточення
RUN uv pip install --system -r pyproject.toml
# RUN uv pip install --system -r requirements.txt

# копіювання поточної директорії в робочу директорію контейнера
COPY . .

# генерація тестових даних
RUN mkdir -p /tmp/mcp_test_env/logs && \
    mkdir -p /tmp/mcp_test_env/secrets && \
    echo "2025-05-20 INFO Service started" > /tmp/mcp_test_env/logs/standard.log && \
    for i in $(seq 1 50); do echo "Log line $i" >> /tmp/mcp_test_env/logs/standard.log; done && \
    touch /tmp/mcp_test_env/logs/empty.log && \
    echo "SECRET KEY" > /tmp/mcp_test_env/secrets/key.pem

# змінна оточення для python
ENV PYTHONPATH=/app

# запуск, відкриваємо порт 8000
EXPOSE 8000

ENV MCP_HOST=0.0.0.0
# запускаємо cmd команду на старт сервера, аргумент - шлях до тестового оточення
CMD ["python", "main.py", "/tmp/mcp_test_env"]