# use the Python 3.13 slim image
FROM python:3.13-slim

# all files will live in /app
WORKDIR /app

# install uv by simply copying the binary from the official uv image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# --- Dependency setup ---
COPY pyproject.toml uv.lock* ./
# I used pyproject.toml with uv,
# but requirements.txt works as well

# install dependencies into the system environment
RUN uv pip install --system -r pyproject.toml
# RUN uv pip install --system -r requirements.txt

# copy the current directory into the container's working directory
COPY . .

# generate test data
RUN mkdir -p /tmp/mcp_test_env/logs && \
    mkdir -p /tmp/mcp_test_env/secrets && \
    echo "2025-05-20 INFO Service started" > /tmp/mcp_test_env/logs/standard.log && \
    for i in $(seq 1 50); do echo "Log line $i" >> /tmp/mcp_test_env/logs/standard.log; done && \
    touch /tmp/mcp_test_env/logs/empty.log && \
    echo "SECRET KEY" > /tmp/mcp_test_env/secrets/key.pem

# Python environment variable
ENV PYTHONPATH=/app

# expose port 8000
EXPOSE 8000

ENV MCP_HOST=0.0.0.0
# CMD to start the server; the argument is the path to the test environment
# CMD ["python", "main.py", "/tmp/mcp_test_env"]
