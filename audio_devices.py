"""Choix du micro et de la sortie audio (noms Windows complets, via DirectSound)."""
import sounddevice as sd

# DirectSound : noms complets (MME les coupe à 31 lettres) et rééchantillonnage automatique.
_HOSTAPI = "Windows DirectSound"
# Entrées « par défaut » de DirectSound, déjà couvertes par notre option « Par défaut ».
_SKIP = ("pilote de capture audio principal", "périphérique audio principal")


def _hostapi_index():
    for i, h in enumerate(sd.query_hostapis()):
        if h["name"] == _HOSTAPI:
            return i
    return None


def list_devices(kind: str) -> list:
    """Noms des périphériques d'entrée (kind="input") ou de sortie (kind="output")."""
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    api = _hostapi_index()
    names = []
    for d in sd.query_devices():
        if d[key] <= 0 or (api is not None and d["hostapi"] != api):
            continue
        if d["name"].lower() in _SKIP or d["name"] in names:
            continue
        names.append(d["name"])
    return names


def resolve(device, kind: str):
    """Nom enregistré -> numéro sounddevice (None = périphérique par défaut de Windows)."""
    if device in (None, ""):
        return None
    if isinstance(device, int):
        return device
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    api = _hostapi_index()
    fallback = None
    for i, d in enumerate(sd.query_devices()):
        if d[key] <= 0:
            continue
        if d["name"] == device and (api is None or d["hostapi"] == api):
            return i
        if fallback is None and str(device).lower() in d["name"].lower():
            fallback = i
    return fallback  # appareil débranché : None = retour au périphérique par défaut
