"""Imprime la longitud y el valor sanitizado de API_KEY: "<len> <valor>"."""
import os
import re

v = re.sub(r"[\s\u200b\ufeff]+", "", os.environ.get("API_KEY", ""))
print(f"{len(v)} {v}")
