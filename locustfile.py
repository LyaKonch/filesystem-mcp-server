from locust import HttpUser, task, between
import logging

class MCPServerUser(HttpUser):
    wait_time = between(1, 2) # Пауза між діями юзера від 1 до 2 секунд
    
    command_endpoint = None
    post_headers = {
        "Content-Type": "application/json"
    }

    def on_start(self):
        """Емуляція підключення до SSE для отримання Session ID"""
        try:
            # stream=True важливий для читання SSE потоку
            with self.client.get("/sse", stream=True, name="SSE Handshake", catch_response=True) as response:
                
                if response.status_code != 200:
                    response.failure(f"SSE connection failed: {response.status_code}")
                    return

                # Парсинг потоку для пошуку event: endpoint
                current_event = None
                for line in response.iter_lines():
                    if not line: continue 
                    decoded_line = line.decode('utf-8')
                    
                    if decoded_line.startswith("event:"):
                        current_event = decoded_line.split(":", 1)[1].strip()
                    
                    if decoded_line.startswith("data:") and current_event == "endpoint":
                        # Зберігаємо персональний URL сесії
                        self.command_endpoint = decoded_line.split(":", 1)[1].strip()
                        response.success()
                        break # ID отримано, виходимо з потоку
                        
        except Exception as e:
            logging.error(f"Error during SSE handshake: {e}")

    @task(3)
    def get_cpu(self):
        """Легка задача: запит CPU"""
        if not self.command_endpoint: return

        payload = {
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": "get_cpu_usage", "arguments": {}}, "id": 1
        }
        self.client.post(self.command_endpoint, json=payload, headers=self.post_headers)

    @task(1)
    def read_logs(self):
        """Важка задача: читання файлу"""
        if not self.command_endpoint: return

        payload = {
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {
                "name": "read_log_file",
                "arguments": {"path": "/tmp/mcp_test_env/logs/standard.log", "lines": 5}
            }, "id": 2
        }
        self.client.post(self.command_endpoint, json=payload, headers=self.post_headers, name="Read Log File")