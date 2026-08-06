from yasinhub.agent_integration import AgentIntegration


class AgentService:

    def __init__(self):
        self.agent = AgentIntegration()

    def health(self, name):
        return self.agent.check_agent_health(name)

    def status(self, name):
        return self.agent.get_agent_status(name)

    def register(self, name, description=""):
        return self.agent.register_agent(
            name,
            description
        )

    def start(self, name):
        return self.agent.start_agent(name)

    def stop(self, name):
        return self.agent.stop_agent(name)

    def restart(self, name):
        return self.agent.restart_agent(name)
