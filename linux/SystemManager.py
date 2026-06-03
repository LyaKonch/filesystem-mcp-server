import logging

from fastmcp import Context
from fastmcp.server.dependencies import CurrentContext

from core_tools.BaseSystemManager import BaseSystemManager, EnvScope


class SystemManager(BaseSystemManager):
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_variable(self, name: str, scope: EnvScope = EnvScope.USER) -> str | None:
        raise NotImplementedError()

    def list_variables(self, scope: EnvScope = EnvScope.USER) -> dict[str, str]:
        raise NotImplementedError()

    async def set_variable(
        self,
        name: str,
        value: str,
        scope: EnvScope = EnvScope.USER,
        ctx: Context | None = CurrentContext(),
    ) -> str:
        raise NotImplementedError()

    async def delete_variable(
        self, name: str, scope: EnvScope = EnvScope.USER, ctx: Context | None = CurrentContext()
    ) -> str:
        raise NotImplementedError()
