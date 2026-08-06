from yasinhub.services.feed_service import FeedService
from yasinhub.services.core_service import CoreService
from yasinhub.services.agent_service import AgentService
from yasinhub.services.relay_service import RelayService


class EcosystemService:

    def __init__(self):

        self.services = {
            "feed": FeedService(),
            "core": CoreService(),
            "agent": AgentService(),
            "relay": RelayService(),
        }


    def health(self):

        result = {}

        for name, service in self.services.items():

            try:
                result[name] = service.health()

            except Exception as e:
                result[name] = {
                    "status": "error",
                    "error": str(e)
                }

        return result
