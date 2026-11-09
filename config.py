"""Configuration de Jimmy (fichier config.json à côté du programme)."""
import json
import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Dossier des fichiers du programme, en lecture seule (aussi une fois transformé en .exe)."""
    if getattr(sys, "frozen", False):
        # PyInstaller 6 range les fichiers de données dans _internal (sys._MEIPASS).
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """Dossier où Jimmy écrit ses données (réglages, appareils jumelés, voix, cache).

    Installé (.exe) : le dossier « Jimmy » dans AppData, car le dossier du programme est en lecture seule.
    En développement : le dossier du code, comme avant.
    """
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("APPDATA") or Path.home()) / "Jimmy"
        base.mkdir(parents=True, exist_ok=True)
        return base
    return app_dir()


# Alias Claude Code -> nom lisible avec sa version (à mettre à jour quand une nouvelle version sort).
MODEL_NAMES = {
    "opus": "Opus 5.5",
    "sonnet": "Sonnet 5.5",
    "haiku": "Haiku 5.5",
    "fable": "Fable 5.1",
}

# Couleurs d'accent du thème : nom -> (couleur principale, couleur secondaire).
ACCENTS = {
    "Cyan néon": ("#22d3ee", "#7c3aed"),
    "Magenta néon": ("#e84df5", "#22d3ee"),
    "Vert matrix": ("#4ade80", "#0891b2"),
    "Rouge sang": ("#ff1e46", "#7c3aed"),
    "Jaune néon": ("#fbbf24", "#ec4899"),
    "Cyberpsychose": ("#ff1e46", "#00f0ff"),   # rouge + glitchs permanents, quel que soit le quota
}

DEFAULTS = {
    # Apparence et effets
    "accent": "Cyan néon",
    "effects": True,           # balayages, éclairs, animations
    "orb_sides": True,         # flux de données à gauche et à droite de l'orbe
    "orb_sats": True,          # petits satellites autour de l'orbe
    "voice_glitch": True,      # la voix de Jimmy a de petits accrocs pendant la cyberpsychose
    "ctx_auto": True,          # reprise automatique du contexte dans une nouvelle discussion
    "ctx_threshold": 70,       # % de la limite de contexte à partir duquel on change de discussion
    "context_limit": 1000000,  # taille maximale du contexte du modèle (en tokens)
    "glitch_freq": "Moyenne",   # Rare (~1 min), Moyenne (~20 s), Fréquente (~8 s)
    "micro_glitch": True,     # très légers glitchs aléatoires de temps en temps
    "psy_enabled": True,       # effet de cyberpsychose en fin de quota
    "psy_threshold": 80,       # % de la session à partir duquel il se déclenche
    "chat_font": 15,           # taille du texte de la discussion
    "live_preview": True,      # texte écrit en direct pendant que tu parles
    "tts_speed_bonus": 24,     # vitesse de la voix : % ajoutés à la vitesse de la voix choisie
    # Dossier sur lequel Claude Code travaille (ton site monté en SFTP, ou un clone local).
    "workdir": "",
    # Chemin de la commande `claude` si elle n'est pas trouvée automatiquement.
    "claude_path": "",
    # Modèle Claude (vide = celui par défaut de Claude Code). Ex : "sonnet", "opus".
    "model": "",
    # Niveau d'effort (vide = défaut) : low, medium, high, xhigh, max. Bas = moins de tokens.
    "effort": "",
    # Économie auto : au-delà de eco_threshold % de la limite de session, bascule sur eco_model.
    "eco_auto": False,
    "eco_threshold": 85,
    "eco_model": "sonnet",
    # Étapes de travail (lecture, modification, commande...) affichées pendant que Claude bosse.
    "show_steps": True,
    # "acceptEdits" : modifie les fichiers sans demander.
    # "bypassPermissions" : aucune demande de permission, quoi que Claude fasse.
    "permission_mode": "bypassPermissions",
    # Garde-fous techniques en mode autonomie : git push --force, --no-verify, DROP, TRUNCATE restent refusés.
    "guard_deny": True,
    # Demande d'autorisation (hors mode autonomie) : sans réponse après ce délai (secondes), l'action est refusée.
    "perm_timeout": 120,
    # Outils que Claude Code peut utiliser sans demander (Bash = commandes, ssh, etc.).
    "allowed_tools": [
        "Read", "Edit", "Write", "Glob", "Grep", "Bash", "PowerShell", "WebFetch", "WebSearch",
        "NotebookEdit", "TodoWrite", "Task", "Agent", "Skill",
    ],
    "timeout_seconds": 1800,
    # Reprise de contexte : l'ancienne discussion est supprimée (copie gardée trash_days jours dans la corbeille de Jimmy).
    "handoff_delete": True,
    "trash_days": 7,
    "cleanup_reprises_done": False,
    # Texte libre ajouté aux consignes de Jimmy : infos sur ton serveur, ton site, ta base...
    "extra_instructions": "",
    # Carte de tes dossiers, une ligne par projet : « nom = chemin (à quoi il sert) ». Jimmy y va tout droit.
    "projects_text": "",
    # Économie de tokens : les plugins MCP (Playwright, DevTools...) ne sont chargés que si besoin.
    "lean_mcp": False,
    # Voix et écoute
    "language": "fr",
    "whisper_model": "small",      # tiny, base, small, medium (plus gros = plus précis, plus lent)
    "whisper_device": "cpu",       # "cpu" ou "cuda" (carte NVIDIA) ou "auto"
    "mic_device": None,            # nom du micro (None = micro par défaut) : bouton Réglages
    "speaker_device": None,        # nom de la sortie audio de la voix (None = par défaut)
    "mic_sensitivity": 1.0,        # >1 = capte les voix plus basses
    "continue_seconds": 1.5,       # temps pour reprendre ta phrase après une pause
    "continue_unfinished_seconds": 4.0,  # idem quand la phrase semble coupée
    "wake_words_enabled": True,    # écoute permanente du mot d'éveil
    "wake_words": ["jimmy"],      # modifiable dans la fenêtre : ex. ["jimmy", "hey claude"]
    # Petit modèle rapide, utilisé seulement pour repérer le mot d'éveil (vide = whisper_model).
    "wake_whisper_model": "base",
    "wake_silence_seconds": 0.45,  # silence après « Jimmy » avant de réagir
    "wake_beep": True,             # petit bip dès que le mot d'éveil est reconnu
    "capture_sounds": True,        # « bloup » discret au début et à la fin de la capture de ta voix
    "silence_seconds": 1.2,        # silence qui clôt un morceau de phrase (puis temps de reprise)
    "long_mode": False,            # réponses détaillées affichées, seul le résumé est lu
    "dictation": False,            # la voix écrit dans la zone de texte au lieu d'envoyer
    "question_listen_seconds": 8,  # écoute sans « Jimmy » quand Jimmy vient de poser une question
    "followup_seconds": 4,         # petite écoute sans « Jimmy » après chaque réponse (0 = jamais)
    "auto_relisten": True,         # bouton « Relance » : réécoute après une réponse (questions comprises)
    # Voix premium (facultatif) : clé sur elevenlabs.io, puis choisir « ElevenLabs (premium) ».
    "elevenlabs_api_key": "",
    "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
    "command_prompt": "Claude Code, SFTP, Python, site web, base de données.",
    "voice_enabled": True,
    # Voix de Jimmy (liste dans speaker.py) : Jimmy, Néon (féminine), Androïde...
    "voice_preset": "Jimmy",
    "tts_voice": "fr-FR-HenriNeural",   # autre voix : fr-FR-DeniseNeural
    "tts_rate": "+8%",
    "browser": "",                  # navigateur à utiliser (ex. Brave) ; vide = celui par défaut
    "start_maximized": True,       # la fenêtre s'ouvre en grand (toujours une fenêtre)
    # Consignes personnelles ajoutées à celles de Jimmy (habitudes, outils, projets) : propres à chaque utilisateur.
    "custom_prompt": "",
    # Appli mobile (PWA) : désactivée par défaut, elle donne accès à ton PC depuis le téléphone.
    "remote_enabled": False,
    "remote_mode": "lan",          # lan (Wi-Fi), tunnel (Internet via Cloudflare), custom (ton adresse : Tailscale, domaine...)
    "remote_port": 8765,
    "remote_custom_url": "",       # utilisé en mode custom, ex. https://jimmy.mondomaine.fr
    # Mises à jour : dépôt GitHub « proprietaire/depot » des versions publiées (vide = pas de mise à jour automatique).
    "update_repo": "",
    "update_check": True,
    "setup_done": False,           # assistant de premier lancement terminé
}


class Config:
    def __init__(self, data: dict, path: Path):
        self.data = data
        self.path = path

    @classmethod
    def load(cls) -> "Config":
        path = data_dir() / "config.json"
        data = dict(DEFAULTS)
        existed = path.exists()
        if existed:
            try:
                data.update(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        cfg = cls(data, path)
        if not existed:
            cfg.save()
        return cfg

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value
        self.save()

    def save(self) -> None:
        try:
            self.path.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass
