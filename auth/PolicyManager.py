import json
import logging
from pathlib import Path
from typing import Any

from config import settings
from utilities.dependencies import is_path_within_scope


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
            return (
                True  # no constraints - allow (or change to False to deny by default if you prefer)
            )

        limit = constraints.get(key)
        if limit is None:
            return True

        # logic based on key type
        if key == "allowed_paths":
            return is_path_within_scope(value_to_check, limit)

        if key in ["max_read_size", "max_write_size"]:
            return int(value_to_check) <= int(limit)

        if key == "allowed_extensions":
            ext = Path(value_to_check).suffix.lower()
            return ext in [e.lower() for e in limit]

        if key == "max_depth":
            return int(value_to_check) <= int(limit)

        return True


if settings.AUTH_ENABLED and settings.POLICY_CONFIG_PATH:
    policy_manager = PolicyManager(settings.POLICY_CONFIG_PATH)
