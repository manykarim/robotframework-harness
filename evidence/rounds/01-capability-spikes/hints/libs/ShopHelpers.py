"""Tiny project library used to provoke a real keyword-name collision with Browser."""


class ShopHelpers:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def take_screenshot(self, name: str = "shot"):
        """Project helper that clashes with Browser.Take Screenshot."""
        return name
