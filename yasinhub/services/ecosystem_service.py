from yasinhub.services.feed_service import FeedService
from yasinhub.services.core_service import CoreService
from yasinhub.services.agent_service import AgentService
from yasinhub.services.relay_service import RelayService


class EcosystemService:

    def __init__(self):
        self.feed = FeedService()
        self.core = CoreService()
        self.agent = AgentService()
        self.relay = RelayService()


    def health(self):

        return {
            "feed": self.feed.health(),
            "core": self.core.health(),
            "agent": self.agent.health("default"),
            "relay": self.relay.health()
        }


    def summary(self):

        return {
            "services": [
                "YasinFeed",
                "YasinCore",
                "YasinAgent",
                "YasinRelay"
            ],
            "status": self.health()
        }
