class ReportGenerator:
    def __init__(self, results: list, output_path: str | None = None):
        self.results     = results
        self.output_path = output_path

    def print(self) -> None:
        raise NotImplementedError("ReportGenerator not built yet")