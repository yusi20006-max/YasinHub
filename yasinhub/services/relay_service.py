from yasinhub.relay_integration import RelayIntegration


class RelayService:

    def __init__(self):
        self.relay = RelayIntegration()

    def health(self):
        status = self.relay.get_status()

        return {
            "service": "YasinHub Relay Service",
            "status": status
        }

    def connect(self):
        return self.relay.connect()

    def handle_event(self, event_type, payload):
        return self.relay.handle_event(
            event_type,
            payload
        )

    def verify_channels(self, channels=None):
        return self.relay.verify_channels(channels)
