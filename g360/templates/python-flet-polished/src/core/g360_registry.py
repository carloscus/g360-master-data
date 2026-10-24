"""
G360 App Registry — Sistema de identidad y descubrimiento entre apps G360.

Cada app G360 se registra automaticamente al iniciar con:
- Nombre unico
- Version
- Skill aplicado
- Eventos disponibles
- Endpoints de comunicacion
- Version del evento (para backward compatibility)

Las apps pueden descubrir otras apps y enviar eventos entre si.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Callable, Any, Dict, List, Optional, Awaitable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from functools import wraps

try:
    import asyncio
    _has_asyncio = True
except ImportError:
    _has_asyncio = False

logger = logging.getLogger("g360.registry")


# Ruta del registry global
REGISTRY_FILE = Path.home() / ".g360" / "apps_registry.json"

# Version del schema de registry (para migration)
REGISTRY_SCHEMA_VERSION = "1.0.0"


@dataclass
class AppMetadata:
    """Metadatos de una app G360."""
    name: str
    version: str
    skill: str
    framework: str
    description: str = ""
    author: str = ""
    created_at: str = ""
    updated_at: str = ""
    
    # Version del evento (para compatibilidad)
    event_schema_version: str = "1.0.0"
    
    # Eventos que esta app puede procesar
    events: List[str] = field(default_factory=list)
    
    # Endpoints de comunicacion
    endpoints: Dict[str, str] = field(default_factory=dict)
    
    # Estado de salud
    status: str = "offline"  # online, offline, error, starting
    last_seen: str = ""
    uptime: float = 0.0
    
    # Versiones de dependencias
    dependencies: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AppMetadata':
        # Fallback para campos faltantes (migration)
        missing_fields = set(cls.__dataclass_fields__.keys()) - set(data.keys())
        for field_name in missing_fields:
            default = cls.__dataclass_fields__[field_name].default
            if callable(default):
                data[field_name] = default()
            else:
                data[field_name] = default
        return cls(**data)
    
    def is_recent(self, max_age_seconds: int = 300) -> bool:
        """Verificar si la app fue vista recientemente."""
        if not self.last_seen:
            return False
        try:
            last_seen = datetime.fromisoformat(self.last_seen)
            age = (datetime.now() - last_seen).total_seconds()
            return age < max_age_seconds
        except Exception:
            return False


class EventCallback:
    """Wrapper para callbacks que soporta sync y async."""
    
    def __init__(self, callback: Callable, is_async: bool = False):
        self.callback = callback
        self.is_async = is_async
    
    async def __call__(self, data: Optional[dict] = None):
        """Ejecutar el callback, manejando sync/async."""
        if self.is_async:
            return await self.callback(data)
        else:
            # Ejecutar sync en thread pool para no bloquear
            import concurrent.futures
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return await loop.run_in_executor(pool, self.callback, data)


class G360EventBus:
    """
    Bus de eventos estandarizado para comunicacion entre apps G360.
    
    Patrones de nombre de eventos:
    - app:{nombre}:{accion} — Eventos de la app
    - g360:{tipo}:{accion} — Eventos del sistema G360
    - {dominio}:{accion} — Eventos de dominio especifico
    
    Ejemplos:
    - app:stock-monitor:refresh
    - g360:theme:change
    - inventory:stock:low
    
    Soporta wildcards:
    - app:*:refresh — Todos los refresh de apps
    - g360:* — Todos los eventos del sistema
    - app:stock-monitor:* — Todos los eventos de stock-monitor
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._subscribers: Dict[str, List[EventCallback]] = {}
        self._app_registry: Dict[str, AppMetadata] = {}
        self._history: List[dict] = []
        self._max_history = 100
        self._version = "1.0.0"
    
    def subscribe(self, event_pattern: str, callback: Callable) -> str:
        """
        Suscribir a un evento (soporta wildcards).
        
        Args:
            event_pattern: patron del evento (ej: "app:*:refresh")
            callback: funcion a ejecutar (sync o async)
        
        Returns:
            ID de suscripcion para poder desuscribirse despues
        
        Example:
            sub_id = bus.subscribe("app:*:refresh", my_callback)
            bus.unsubscribe(sub_id)
        """
        is_async = _has_asyncio and asyncio.iscoroutinefunction(callback)
        wrapper = EventCallback(callback, is_async)
        
        if event_pattern not in self._subscribers:
            self._subscribers[event_pattern] = []
        self._subscribers[event_pattern].append(wrapper)
        
        # Return unique ID for this subscription
        sub_id = f"{event_pattern}:{len(self._subscribers[event_pattern]) - 1}"
        return sub_id
    
    def unsubscribe(self, event_pattern: str, callback: Optional[Callable] = None):
        """
        Desuscribir de un evento.
        
        Args:
            event_pattern: patron del evento
            callback: si es None, elimina todas las suscripciones
        """
        if event_pattern not in self._subscribers:
            return
        
        if callback is None:
            # Eliminar todas las suscripciones de este patron
            del self._subscribers[event_pattern]
        else:
            # Eliminar solo esta callback
            self._subscribers[event_pattern] = [
                cb for cb in self._subscribers[event_pattern]
                if cb.callback != callback
            ]
            if not self._subscribers[event_pattern]:
                del self._subscribers[event_pattern]
    
    def unsubscribe_all(self):
        """Eliminar todas las suscripciones."""
        self._subscribers.clear()
    
    async def publish(self, event: str, data: Optional[dict] = None):
        """
        Publicar un evento de forma asincrona.
        
        Args:
            event: nombre del evento
            data: datos opcionales
        """
        results = []
        
        # Ejecutar suscriptores exactos
        if event in self._subscribers:
            for cb in self._subscribers[event]:
                try:
                    result = cb(data)
                    if asyncio.iscoroutine(result):
                        results.append(await result)
                except Exception as e:
                    logger.error(f"Error in callback for {event}: {e}")
        
        # Ejecutar suscriptores con wildcard
        for pattern, callbacks in self._subscribers.items():
            if '*' in pattern and self._match_pattern(pattern, event):
                for cb in callbacks:
                    try:
                        result = cb(data)
                        if asyncio.iscoroutine(result):
                            results.append(await result)
                    except Exception as e:
                        logger.error(f"Error in callback for {pattern}: {e}")
        
        # Registrar en historial
        self._history.append({
            "event": event,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "results": len(results),
        })
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        return results
    
    def publish_sync(self, event: str, data: Optional[dict] = None):
        """
        Publicar un evento de forma sincrona (para usar fuera de async context).
        
        Args:
            event: nombre del evento
            data: datos opcionales
        """
        results = []
        
        # Ejecutar suscriptores exactos
        if event in self._subscribers:
            for cb in self._subscribers[event]:
                try:
                    result = cb.callback(data)
                    if asyncio.iscoroutine(result):
                        # Si es async, ejecutar en nuevo loop
                        import asyncio as _asyncio
                        result = _asyncio.run(result)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error in callback for {event}: {e}")
        
        # Ejecutar suscriptores con wildcard
        for pattern, callbacks in self._subscribers.items():
            if '*' in pattern and self._match_pattern(pattern, event):
                for cb in callbacks:
                    try:
                        result = cb.callback(data)
                        if asyncio.iscoroutine(result):
                            import asyncio as _asyncio
                            result = _asyncio.run(result)
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Error in callback for {pattern}: {e}")
        
        # Registrar en historial
        self._history.append({
            "event": event,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "results": len(results),
        })
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        return results
    
    def _match_pattern(self, pattern: str, event: str) -> bool:
        """Verificar si un evento coincide con un patron (wildcards)."""
        pattern_parts = pattern.split(':')
        event_parts = event.split(':')
        
        if len(pattern_parts) != len(event_parts):
            return False
        
        for p, e in zip(pattern_parts, event_parts):
            if p != '*' and p != e:
                return False
        return True
    
    def get_history(self, limit: int = 10) -> List[dict]:
        """Obtener historial de eventos."""
        return self._history[-limit:]
    
    def get_subscribers_count(self) -> int:
        """Obtener cantidad total de suscripciones."""
        return sum(len(cbs) for cbs in self._subscribers.values())
    
    def get_event_names(self) -> List[str]:
        """Obtener todos los patrones de eventos suscritos."""
        return list(self._subscribers.keys())


class G360AppRegistry:
    """
    Registry de apps G360.
    
    Permite:
    - Registrar una app
    - Descubrir apps disponibles
    - Ver estado de salud de apps
    - Comunicacion entre apps
    - Limpiar apps offline
    """
    
    def __init__(self, registry_file: Optional[Path] = None):
        self.registry_file = registry_file or REGISTRY_FILE
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        self._apps: Dict[str, AppMetadata] = {}
        self._schema_version = REGISTRY_SCHEMA_VERSION
        self._load_registry()
    
    def register(self, app: AppMetadata):
        """Registrar una app en el registry."""
        app.updated_at = datetime.now().isoformat()
        if not app.created_at:
            app.created_at = app.updated_at
        app.status = "online"
        app.last_seen = app.updated_at
        self._apps[app.name] = app
        self._save_registry()
        logger.info(f"App registered: {app.name} v{app.version}")
    
    def unregister(self, app_name: str):
        """Dar de baja una app."""
        if app_name in self._apps:
            del self._apps[app_name]
            self._save_registry()
            logger.info(f"App unregistered: {app_name}")
    
    def get_app(self, app_name: str) -> Optional[AppMetadata]:
        """Obtener metadatos de una app."""
        return self._apps.get(app_name)
    
    def list_apps(self) -> List[AppMetadata]:
        """Listar todas las apps registradas."""
        return list(self._apps.values())
    
    def list_online_apps(self) -> List[AppMetadata]:
        """Listar solo apps online."""
        return [app for app in self._apps.values() if app.status == "online"]
    
    def find_by_skill(self, skill: str) -> List[AppMetadata]:
        """Buscar apps por skill."""
        return [app for app in self._apps.values() if app.skill == skill]
    
    def find_by_framework(self, framework: str) -> List[AppMetadata]:
        """Buscar apps por framework."""
        return [app for app in self._apps.values() if app.framework == framework]
    
    def find_by_event(self, event: str) -> List[AppMetadata]:
        """Buscar apps que manejan un evento especifico."""
        return [app for app in self._apps.values() if event in app.events]
    
    def find_recent_apps(self, max_age_seconds: int = 300) -> List[AppMetadata]:
        """Buscar apps vistas recientemente."""
        return [app for app in self._apps.values() if app.is_recent(max_age_seconds)]
    
    def update_status(self, app_name: str, status: str):
        """Actualizar estado de una app."""
        if app_name in self._apps:
            self._apps[app_name].status = status
            self._apps[app_name].last_seen = datetime.now().isoformat()
            self._save_registry()
    
    def heartbeat(self, app_name: str):
        """Actualizar last_seen de una app (heartbeat)."""
        if app_name in self._apps:
            self._apps[app_name].last_seen = datetime.now().isoformat()
            self._save_registry()
    
    def cleanup_offline(self, max_age_seconds: int = 600):
        """Limpiar apps que han estado offline mucho tiempo."""
        to_remove = []
        for name, app in self._apps.items():
            if not app.is_recent(max_age_seconds):
                to_remove.append(name)
        
        for name in to_remove:
            del self._apps[name]
        
        if to_remove:
            self._save_registry()
            logger.info(f"Cleaned up {len(to_remove)} offline apps")
        
        return to_remove
    
    def _load_registry(self):
        """Cargar registry desde archivo."""
        try:
            if self.registry_file.exists():
                with open(self.registry_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Verificar version del schema
                    stored_version = data.get('schema_version', '0.0.0')
                    if stored_version != self._schema_version:
                        logger.warning(f"Schema version mismatch: {stored_version} vs {self._schema_version}")
                    
                    self._apps = {
                        name: AppMetadata.from_dict(app_data)
                        for name, app_data in data.get('apps', {}).items()
                    }
        except Exception as e:
            logger.error(f"Error loading registry: {e}")
            self._apps = {}
    
    def _save_registry(self):
        """Guardar registry en archivo."""
        try:
            data = {
                'schema_version': self._schema_version,
                'apps': {name: app.to_dict() for name, app in self._apps.items()},
                'updated_at': datetime.now().isoformat()
            }
            with open(self.registry_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving registry: {e}")


# Instancias globales
_event_bus = None
_app_registry = None


def get_event_bus() -> G360EventBus:
    """Obtener instancia singleton del event bus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = G360EventBus()
    return _event_bus


def get_app_registry() -> G360AppRegistry:
    """Obtener instancia singleton del registry."""
    global _app_registry
    if _app_registry is None:
        _app_registry = G360AppRegistry()
    return _app_registry


def register_g360_app(
    name: str,
    version: str,
    skill: str,
    framework: str = "flet",
    events: Optional[List[str]] = None,
    endpoints: Optional[Dict[str, str]] = None,
    description: str = "",
) -> AppMetadata:
    """
    Registrar una app G360 en el registry global.
    
    Usage:
        register_g360_app(
            name="stock-monitor",
            version="1.0.0",
            skill="cipsa",
            events=["app:stock:refresh", "app:data:update"]
        )
    """
    registry = get_app_registry()
    app = AppMetadata(
        name=name,
        version=version,
        skill=skill,
        framework=framework,
        description=description,
        events=events or [],
        endpoints=endpoints or {},
        status="online",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        last_seen=datetime.now().isoformat(),
    )
    registry.register(app)
    return app


def unsubscribe_g360_event(event_pattern: str, callback: Optional[Callable] = None):
    """Desuscribir de un evento G360."""
    bus = get_event_bus()
    bus.unsubscribe(event_pattern, callback)


def subscribe_g360_event(event_pattern: str, callback: Callable) -> str:
    """
    Suscribir a un evento G360.
    
    Returns:
        subscription_id para poder desuscribirse despues
    """
    bus = get_event_bus()
    return bus.subscribe(event_pattern, callback)


async def publish_g360_event(event: str, data: Optional[dict] = None):
    """Publicar un evento G360 (async)."""
    bus = get_event_bus()
    return await bus.publish(event, data)


def publish_g360_event_sync(event: str, data: Optional[dict] = None):
    """Publicar un evento G360 (sync)."""
    bus = get_event_bus()
    return bus.publish_sync(event, data)


def discover_apps(skill: Optional[str] = None, online_only: bool = True) -> List[AppMetadata]:
    """
    Descubrir apps G360 registradas.
    
    Args:
        skill: Filtrar por skill (opcional)
        online_only: Solo apps online
    
    Returns:
        Lista de apps encontradas
    """
    registry = get_app_registry()
    
    if online_only:
        apps = registry.list_online_apps()
    else:
        apps = registry.list_apps()
    
    if skill:
        apps = [app for app in apps if app.skill == skill]
    
    return apps
