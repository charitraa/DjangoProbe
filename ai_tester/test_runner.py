class TestRunner:
    def __init__(self, repo_path: str, test_files: list[str]):
        self.repo_path  = repo_path
        self.test_files = test_files

    def run(self) -> list:
        raise NotImplementedError("TestRunner not built yet")