# models/__init__.py
# Modelleri buradan import et ki db.create_all() onları görsün
from app.models.user import User
from app.models.legacy import Ancestor, AncestorMemory, LegacyKey, DeadManSwitch
