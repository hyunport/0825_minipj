"""Kiosk의 Mock/PostgreSQL 데이터와 짧은 대화 상태를 관리합니다."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.schemas.kiosk import CartItem, MenuItem


MOCK_MENUS = [
    {"menu_id": "B001", "name": "불고기버거", "aliases": "불고기,불고기 버거", "description": "달콤한 불고기 소스가 들어간 햄버거", "single_price": 5000, "set_price": 7500, "active": True},
    {"menu_id": "B002", "name": "치즈버거", "aliases": "치즈,치즈 버거", "description": "고소한 치즈가 들어간 햄버거", "single_price": 5500, "set_price": 8000, "active": True},
    {"menu_id": "B003", "name": "새우버거", "aliases": "새우,새우 버거", "description": "바삭한 새우 패티가 들어간 햄버거", "single_price": 6000, "set_price": 8500, "active": True},
]


class KioskRepository:
    """영구 주문 데이터와 Backend 메모리 상태의 경계를 한곳에 둡니다."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._pending_actions: dict[str, dict[str, Any]] = {}
        self._mock_orders: list[dict[str, Any]] = []

    @property
    def db_mode(self) -> str:
        return settings.kiosk_db_mode.lower()

    def reset_runtime_state(self) -> None:
        """대화와 확인 대기 상태만 지우며 저장된 주문은 유지합니다."""
        with self._lock:
            self._sessions = {}
            self._pending_actions = {}

    def reset_all_for_test(self) -> None:
        with self._lock:
            self._sessions = {}
            self._pending_actions = {}
            self._mock_orders = []

    def list_menus(self) -> list[MenuItem]:
        return [MenuItem.model_validate(row) for row in self._menu_rows() if row.get("active", True)]

    def search_menu(self, query: str) -> list[MenuItem]:
        compact_query = self._compact(query)
        matches: list[MenuItem] = []
        for row in self._menu_rows():
            terms = [row["name"], row.get("description", ""), *row.get("aliases", "").split(",")]
            if row.get("active", True) and any(
                self._compact(term) in compact_query or compact_query in self._compact(term)
                for term in terms
                if self._compact(term)
            ):
                matches.append(MenuItem.model_validate(row))
        return matches

    def get_menu(self, menu_id: str) -> MenuItem | None:
        return next((menu for menu in self.list_menus() if menu.menu_id == menu_id), None)

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._sessions.get(session_id, {}))

    def update_session(self, session_id: str, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.setdefault(session_id, {})
            session.update(deepcopy(values))
            return deepcopy(session)

    def create_pending_action(self, session_id: str, mode: str, cart: list[CartItem], total_price: int) -> str:
        action_id = str(uuid4())
        with self._lock:
            self._pending_actions[action_id] = {
                "action_id": action_id,
                "session_id": session_id,
                "mode": mode,
                "cart": [item.model_dump() for item in cart],
                "total_price": total_price,
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=settings.kiosk_pending_ttl_seconds),
            }
        return action_id

    def create_order_from_pending(self, action_id: str, session_id: str) -> dict[str, Any] | None:
        """유효한 action을 한 번 소비한 뒤 그 안의 주문만 저장합니다."""
        with self._lock:
            action = self._pending_actions.get(action_id)
            if action is None:
                return None
            if action["expires_at"] < datetime.now(timezone.utc):
                self._pending_actions.pop(action_id, None)
                return None
            if action["session_id"] != session_id:
                return None
            self._pending_actions.pop(action_id, None)
            if self.db_mode == "mock":
                return self._save_mock_order(action)
            if self.db_mode == "postgres":
                return self._save_postgres_order(action)
            raise ValueError(f"지원하지 않는 KIOSK_DB_MODE입니다: {self.db_mode}")

    def mock_order_count(self) -> int:
        with self._lock:
            return len(self._mock_orders)

    def _save_mock_order(self, action: dict[str, Any]) -> dict[str, Any]:
        order_number = f"K{len(self._mock_orders) + 1:06d}"
        order = {"created": True, "order_number": order_number, "cart": deepcopy(action["cart"]), "total_price": action["total_price"]}
        self._mock_orders.append(order)
        return deepcopy(order)

    def _save_postgres_order(self, action: dict[str, Any]) -> dict[str, Any]:
        try:
            import psycopg
        except ImportError as error:
            raise RuntimeError("psycopg가 설치되지 않았습니다.") from error

        with psycopg.connect(settings.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO orders (session_id, execution_mode, total_price, status) VALUES (%s, %s, %s, 'completed') RETURNING order_id",
                    (action["session_id"], action["mode"], action["total_price"]),
                )
                order_id = cursor.fetchone()[0]
                order_number = f"K{order_id:06d}"
                cursor.execute("UPDATE orders SET order_number = %s WHERE order_id = %s", (order_number, order_id))
                for item in action["cart"]:
                    cursor.execute(
                        """INSERT INTO order_items (order_id, menu_id, menu_name, order_option, quantity, unit_price, line_total)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (order_id, item["menu_id"], item["menu_name"], item["option"], item["quantity"], item["unit_price"], item["line_total"]),
                    )
        return {"created": True, "order_number": order_number, "cart": deepcopy(action["cart"]), "total_price": action["total_price"]}

    def _menu_rows(self) -> list[dict[str, Any]]:
        if self.db_mode == "mock":
            return deepcopy(MOCK_MENUS)
        if self.db_mode != "postgres":
            raise ValueError(f"지원하지 않는 KIOSK_DB_MODE입니다: {self.db_mode}")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("psycopg가 설치되지 않았습니다.") from error
        with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT menu_id, name, aliases, description, single_price, set_price, active
                                  FROM menu_items WHERE active = TRUE ORDER BY menu_id""")
                return list(cursor.fetchall())

    @staticmethod
    def _compact(value: str) -> str:
        return "".join(value.lower().split())


kiosk_repository = KioskRepository()
