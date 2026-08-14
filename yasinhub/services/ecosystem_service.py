from yasinhub.services.feed_service import FeedService
from yasinhub.services.core_service import CoreService
from yasinhub.services.agent_service import AgentService
from yasinhub.services.relay_service import RelayService
from yasinhub.services.registry_service import RegistryService
from yasinhub.services.press_service import PressService


class EcosystemService:

    def __init__(self):
        self.feed = FeedService()
        self.core = CoreService()
        self.agent = AgentService()
        self.relay = RelayService()
        self.registry = RegistryService()
        self.press = PressService()

    def health(self):

        return {
            "feed": self.feed.health(),
            "core": self.core.health(),
            "agent": self.agent.health("default"),
            "relay": self.relay.health(),
            "registry": self.registry.health(),
            "press": self.press.health()
        }

    def summary(self):

        return {
            "ecosystem": "YasinHub",
            "services": [
                "YasinFeed",
                "YasinCore",
                "YasinAgent",
                "YasinRelay",
                "Registry",
                "YasinPress"
            ],
            "health": self.health()
        }
