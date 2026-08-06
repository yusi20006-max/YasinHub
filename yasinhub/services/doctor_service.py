import sys
import platform

from yasinhub.services.ecosystem_service import EcosystemService


class DoctorService:

    def __init__(self):
        self.ecosystem = EcosystemService()

    def python_check(self):

        return {
            "version": sys.version,
            "platform": platform.platform(),
            "status": "ok"
        }


    def ecosystem_check(self):

        return self.ecosystem.health()


    def run(self):

        return {
            "doctor": "YasinHub Doctor",
            "python": self.python_check(),
            "ecosystem": self.ecosystem_check()
        }
