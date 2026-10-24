"""Configuracion de recoleccion de pytest para todo el repo.

Los tests de ESTE repo viven en scripts/tests/. Lo que hay en g360/ son
assets que trajo `g360 bring` (templates de la CLI, app Flet con numpy):
no son tests de master-data y al recolectarlos pytest falla por modulos
que no son dependencias de este proyecto.

Con esto, `pytest` a secas y `pytest scripts/tests` dan lo mismo: 198 tests.
"""

collect_ignore_glob = ["g360/*"]
