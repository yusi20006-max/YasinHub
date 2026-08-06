from yasinhub.core_integration import CoreIntegration


class CoreService:

    def __init__(self):
        self.core = CoreIntegration()

    def health(self):
        return self.core.check_health()

    def runtime_info(self):
        return self.core.get_runtime_info()
