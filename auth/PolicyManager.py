import json
import logging
from pathlib import Path
from typing import Any

import psutil

from config import settings
from utilities.dependencies import is_path_within_scope
from utilities.error_handling import ToolOperationError


class PolicyManager:
    def __init__(self, config_path: str | None = None):
        config_file = config_path or str(
            getattr(settings, "POLICY_CONFIG_PATH", "./auth/policy.json")
        )
        self.path = Path(config_file)
        self.logger = logging.getLogger("PolicyManager")
        self.policy = self._load()

    def _load(self):
        if not self.path.exists():
            return {"roles": {"guest": {"permissions": [], "constraints": {}}}, "users": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get_user_role(self, user_id, username="unknown"):
        user_id = str(user_id)
        self.policy = self._load()  # reload to get latest changes
        if user_id not in self.policy["users"]:
            # auto-registering
            self.policy["users"][user_id] = {"role": "guest", "username": username}
            self.path.write_text(json.dumps(self.policy, indent=2, encoding="utf-8"))
        return self.policy["users"][user_id]["role"]

    def check_access(self, user_id, permission, username="unknown") -> bool:
        role_name = self.get_user_role(user_id, username)
        role = self.policy["roles"].get(role_name, {})
        perms = role.get("permissions", [])
        return "*" in perms or permission in perms

    def get_constraints(self, user_id, permission, username="unknown") -> dict:
        role_name = self.get_user_role(user_id, username)
        return self.policy["roles"].get(role_name, {}).get("constraints", {}).get(permission, {})

    def check_constraint(self, constraints: dict | None, key: str, value_to_check: Any) -> bool:
        if not constraints:
            return True  # no constraints - allow

        limit = constraints.get(key)
        if limit is None:
            return True

        if key == "allowed_paths":
            return is_path_within_scope(value_to_check, limit)

        if key in ["allowed_hives", "allowed_scopes", "allowed_extensions", "allowed_services"]:
            return str(value_to_check).upper() in [str(h).upper() for h in limit]

        if key == "allowed_keys":
            import fnmatch

            return any(
                fnmatch.fnmatch(value_to_check.lower(), ak.lower())
                or value_to_check.lower().startswith(ak.replace("*", "").lower())
                for ak in limit
            )

        if key in ["max_read_size", "max_write_size", "max_timeout", "max_depth"]:
            return int(value_to_check) <= int(limit)

        if key == "require_own_process" and limit is True:
            try:
                current_user = psutil.Process().username()
                return value_to_check == current_user
            except Exception as e:
                raise ToolOperationError(
                    "unexpected", "Error checking process ownership constraint"
                ) from e

        if key == "protected_processes":
            return str(value_to_check) not in [str(p) for p in limit]

        if key == "allowed_patterns":
            import fnmatch

            return any(fnmatch.fnmatch(value_to_check.upper(), pat.upper()) for pat in limit)

        return True


if settings.AUTH_ENABLED and settings.POLICY_CONFIG_PATH:
    policy_manager = PolicyManager(settings.POLICY_CONFIG_PATH)
