<!-- g360:agents:begin -->
# AGENTS.md — g360-master-data

Sistema centralizado de datos maestros para proyectos G360.

> El bloque entre los markers `g360:agents` lo genera `g360 agents` y se
> regenera sin perder lo que escribas afuera.

## Verificación

Un solo comando deja el repo listo y verifica que todo esté en verde:

```powershell
.\scripts\verificar.ps1
```

- Bootstrap: crea `.venv` e instala `requirements.txt` si faltan (red solo la primera vez).
- Corre `pytest` (tests en `scripts\tests\`) y `ruff check scripts`.
- Sin `.venv` activado y sin pasos manuales.

- Stack: python (pip)
- Tests: pytest en `scripts\tests/`

## Estructura

- `scripts/`
- `config/`
- `plantillas/`
- `data/`

## Variables de entorno

El código lee estas variables: documentá cada una con su default en `.env.example`.

- `API_KEY`
- `G360_S1_CACHE`
- `G360_STOCK_API_KEY`
- `G360_STOCK_URL`

## Convenciones

- Tests con `pytest` en `tests/`.
- Dependencias declaradas en `requirements.txt`.
- Comentarios que expliquen el *por qué*, no el *qué*.

## Reglas de este repo

- **Autosuficiente**: `git clone` + el comando de verificación debe dejar la app levantada y los tests en verde, sin red y sin ayuda de una persona.
- **Tests honestos**: nada de `it.skip`, `pytest.mark.skip`, `xfail` ni `assert true` para forzar verde.
- **Entorno declarativo**: toda variable de entorno va en `.env.example` con un default seguro.
- **Sin paths de tu máquina**: nada de rutas absolutas locales ni secretos en el código.
- **Evidencia**: al entregar, reportá el comando que corriste y su salida. Si no pudiste verificar, decilo.
<!-- g360:agents:end -->
