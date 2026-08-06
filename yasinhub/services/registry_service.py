from yasinhub.registry import load_config, ProjectEntry


class RegistryService:

    def __init__(self):
        self.projects = load_config()

    def health(self):
        return {
            "service": "YasinHub Registry Service",
            "status": "ok",
            "projects": len(self.projects)
        }

    def register_service(
        self,
        name,
        process_pattern=None,
        description="",
        start_command=None,
        stop_command=None
    ):
        project = ProjectEntry(
            name=name,
            process_pattern=process_pattern,
            description=description,
            start_command=start_command,
            stop_command=stop_command
        )

        self.projects.append(project)

        return {
            "status": "registered",
            "service": project.name
        }

    def list_services(self):
        return self.projects

    def get_service(self, name):
        for project in self.projects:
            if project.name == name:
                return project

        return None

    def get_projects(self):
        return self.projects
