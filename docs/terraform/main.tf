terraform {
  required_version = ">= 1.5.0"

  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

variable "project_root" {
  type        = string
  description = "Absolute path to project root on target host"
}

variable "app_host" {
  type        = string
  description = "Application host binding"
  default     = "0.0.0.0"
}

variable "app_port" {
  type        = number
  description = "Application port"
  default     = 8000
}

resource "local_file" "deployment_env" {
  filename = "${var.project_root}/.env.generated"
  content  = <<-EOT
MCP_HOST=${var.app_host}
MCP_PORT=${var.app_port}
TRANSPORT=http
AUTH_ENABLED=true
USE_PERSISTENT_STORAGE=true
EOT
}

output "generated_env_file" {
  value = local_file.deployment_env.filename
}
