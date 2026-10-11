"""Custom project library for the shop REST API."""
from typing import Optional


class ShopApi:
    """Project library wrapping the shop REST API.

    Must be imported with the ``base_url`` init argument.
    """
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url
        self.token = token

    def create_order(self, product_id: int, quantity: int = 1, coupon: Optional[str] = None) -> dict:
        """Creates a new order via POST /orders and returns the JSON body.

        ``product_id`` is the catalogue id; ``coupon`` is an optional discount code.
        """
        return {}

    def delete_order(self, order_id: int) -> None:
        """Deletes an order via DELETE /orders/{id}."""
