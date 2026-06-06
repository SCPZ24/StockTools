from __future__ import annotations

from stocktools.infra.cron import remove_stocktools_cron, set_stocktools_cron


class CronService:
    def set(self, hour: int, minute: int, command: str) -> None:
        set_stocktools_cron(hour, minute, command)

    def remove(self) -> bool:
        return remove_stocktools_cron()
