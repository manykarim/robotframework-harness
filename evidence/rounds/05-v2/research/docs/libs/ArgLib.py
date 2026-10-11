"""Library with init args: keywords differ by mode (dynamic API)."""
class ArgLib:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"
    def __init__(self, mode="basic", timeout="5s"):
        self.mode, self.timeout = mode, timeout
    def get_keyword_names(self):
        names = ["Basic Keyword"]
        if self.mode == "advanced":
            names.append("Advanced Keyword")
        return names
    def run_keyword(self, name, args, kwargs=None):
        return f"{name} {self.mode} {args}"
    def get_keyword_arguments(self, name):
        return ["value", "count=1"] if name == "Advanced Keyword" else ["value"]
    def get_keyword_documentation(self, name):
        if name == "__init__":
            return "Init: mode basic|advanced."
        return f"Docs for {name} (mode={self.mode})."
