"""
lcu_client.py
=============
Comunicación con la LCU API (League Client Update).

El cliente de LoL expone un servidor HTTP local en 127.0.0.1:{puerto}.
Las credenciales se leen del archivo 'lockfile' que el cliente genera
al abrirse y elimina al cerrarse.

Formato del lockfile:
    LeagueClient:{pid}:{puerto}:{token}:https

Uso:
    from lcu_client import LCUClient
    lcu = LCUClient()
    lcu.connect()          # lee lockfile
    lcu.accept_match()
    lcu.search_match()
    lcu.select_champion(103)
"""

import os
import time
import requests
import urllib3

# Silenciar warnings de SSL autofirmado del cliente de LoL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─── Ruta al lockfile ─────────────────────────────────────────────────────────
# Ajustar si LoL está instalado en otra ruta
LOCKFILE_PATH = r"D:\Riot Games\League of Legends\lockfile"

# Timeout para requests a la LCU
REQUEST_TIMEOUT = 5


class LCUError(Exception):
    """Error de comunicación con la LCU API."""
    pass


class LCUClient:
    """
    Cliente para la LCU API local de League of Legends.

    Métodos principales:
        connect()            → lee lockfile y establece sesión
        is_connected()       → True si el cliente de LoL está abierto
        accept_match()       → acepta la cola cuando aparece
        search_match()       → inicia búsqueda de partida
        select_champion(id)  → bloquea campeón en champion select
        get_session()        → info de la sesión de champ select actual
    """

    def __init__(self):
        self._port: int | None = None
        self._token: str | None = None
        self._session: requests.Session | None = None

    # ─── Conexión ─────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Lee el lockfile y configura la sesión HTTP.
        Retorna True si conectó exitosamente, False si el cliente está cerrado.
        """
        try:
            port, token = self._read_lockfile()
            self._port = port
            self._token = token
            self._session = requests.Session()
            self._session.auth = ("riot", token)
            self._session.verify = False
            return True
        except FileNotFoundError:
            return False

    def is_connected(self) -> bool:
        """Verifica si el cliente de LoL sigue abierto (lockfile existe)."""
        return os.path.exists(LOCKFILE_PATH)

    def wait_for_client(self, timeout: float = 60.0, interval: float = 2.0):
        """
        Espera hasta que el cliente de LoL esté abierto.
        Útil al iniciar el script antes de abrir el juego.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.connect():
                return True
            time.sleep(interval)
        return False

    # ─── Acciones principales ─────────────────────────────────────────────────

    def accept_match(self) -> bool:
        """
        Acepta la cola cuando aparece la pantalla de aceptar partida.
        Retorna True si el request fue exitoso.
        """
        resp = self._post("/lol-matchmaking/v1/ready-check/accept")
        return resp.status_code in (200, 204)

    def search_match(self) -> bool:
        """
        Inicia la búsqueda de partida (equivale a clickear 'Buscar partida').
        Retorna True si el request fue exitoso.
        """
        resp = self._post("/lol-lobby/v2/lobby/matchmaking/search")
        return resp.status_code in (200, 204)

    def select_champion(self, champion_id: int) -> bool:
        """
        Selecciona (lockea) un campeón en champion select.

        Requiere obtener primero el action_id de la sesión actual,
        que identifica la acción de pick asignada al jugador local.

        Retorna True si el campeón fue lockeado correctamente.
        """
        session = self.get_champ_select_session()
        if session is None:
            raise LCUError("No hay sesión de champion select activa.")

        action_id = self._get_local_pick_action_id(session)
        if action_id is None:
            raise LCUError("No se encontró acción de pick para el jugador local.")

        # Paso 1: Seleccionar (hover) el campeón
        self._patch(
            f"/lol-champ-select/v1/session/actions/{action_id}",
            json={"championId": champion_id, "completed": False},
        )

        # Paso 2: Confirmar (lockear)
        resp = self._post(
            f"/lol-champ-select/v1/session/actions/{action_id}/complete"
        )
        return resp.status_code in (200, 204)

    def get_champ_select_session(self) -> dict | None:
        """
        Retorna la sesión actual de champion select, o None si no hay ninguna.
        Contiene info de acciones, timers, picks, bans, etc.
        """
        try:
            resp = self._get("/lol-champ-select/v1/session")
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

    def get_ready_check(self) -> dict | None:
        """
        Retorna el estado del ready-check (cola encontrada), o None si no hay.
        """
        try:
            resp = self._get("/lol-matchmaking/v1/ready-check")
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

    # ─── Helpers internos ─────────────────────────────────────────────────────

    def _read_lockfile(self) -> tuple[int, str]:
        """
        Lee y parsea el lockfile del cliente de LoL.
        Formato: LeagueClient:{pid}:{puerto}:{token}:https
        """
        with open(LOCKFILE_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()

        parts = content.split(":")
        if len(parts) < 5:
            raise LCUError(f"Lockfile con formato inesperado: {content}")

        port = int(parts[2])
        token = parts[3]
        return port, token

    def _base_url(self) -> str:
        return f"https://127.0.0.1:{self._port}"

    def _get(self, path: str) -> requests.Response:
        self._ensure_connected()
        return self._session.get(
            self._base_url() + path, timeout=REQUEST_TIMEOUT
        )

    def _post(self, path: str, json: dict | None = None) -> requests.Response:
        self._ensure_connected()
        return self._session.post(
            self._base_url() + path, json=json, timeout=REQUEST_TIMEOUT
        )

    def _patch(self, path: str, json: dict | None = None) -> requests.Response:
        self._ensure_connected()
        return self._session.patch(
            self._base_url() + path, json=json, timeout=REQUEST_TIMEOUT
        )

    def _ensure_connected(self):
        """Reconecta automáticamente si el lockfile cambió (ej. reinicio del cliente)."""
        if self._session is None or not self.is_connected():
            if not self.connect():
                raise LCUError(
                    "Cliente de LoL no detectado. Asegúrate de tener el cliente abierto."
                )

    def _get_local_pick_action_id(self, session: dict) -> int | None:
        """
        Busca en la sesión de champ select el action_id correspondiente
        al pick del jugador local (localPlayerCellId).

        La sesión tiene una lista de 'actions' (grupos de acciones simultáneas).
        Cada acción tiene: id, type ('pick'/'ban'), actorCellId, completed.
        """
        local_cell = session.get("localPlayerCellId")
        if local_cell is None:
            return None

        for action_group in session.get("actions", []):
            for action in action_group:
                if (
                    action.get("actorCellId") == local_cell
                    and action.get("type") == "pick"
                    and not action.get("completed", True)
                ):
                    return action["id"]
        return None