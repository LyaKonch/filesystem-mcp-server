import json
import logging
from pathlib import Path

from config import settings


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
        return json.loads(self.path.read_text())

    def get_user_role(self, user_id, username="unknown"):
        user_id = str(user_id)
        self.policy = self._load()  # reload to get latest changes
        if user_id not in self.policy["users"]:
            # auto-registering
            self.policy["users"][user_id] = {"role": "guest", "username": username}
            self.path.write_text(json.dumps(self.policy, indent=2))
        return self.policy["users"][user_id]["role"]

    def check_access(self, user_id, permission, username="unknown") -> bool:
        role_name = self.get_user_role(user_id, username)
        role = self.policy["roles"].get(role_name, {})
        perms = role.get("permissions", [])
        return "*" in perms or permission in perms

    def get_constraints(self, user_id, permission, username="unknown") -> dict:
        role_name = self.get_user_role(user_id, username)
        return self.policy["roles"].get(role_name, {}).get("constraints", {}).get(permission, {})


if settings.AUTH_ENABLED and settings.POLICY_CONFIG_PATH:
    policy_manager = PolicyManager(settings.POLICY_CONFIG_PATH)
