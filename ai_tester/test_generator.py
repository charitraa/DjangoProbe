from ai_tester.models import EndpointInfo

class TestGenerator:
    def __init__(self, repo_path: str, endpoints: list[EndpointInfo], use_ai: bool = False):
        self.repo_path = repo_path
        self.endpoints = endpoints
        self.use_ai    = use_ai

    def generate(self) -> list[str]:
        raise NotImplementedError("TestGenerator not built yet")