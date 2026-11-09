"""Pont entre Jimmy et Claude Code (commande `claude`).

Tout passe par Claude Code en mode non interactif : ton abonnement Claude suffit,
aucune clé API n'est nécessaire. La conversation continue d'un message à l'autre
grâce à l'identifiant de session conservé dans state.json.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from config import Config, app_dir, data_dir
from textutils import fold, parse_claude_output, steps_from_event


class ClaudeError(Exception):
    pass


def _purge_old_jobs(folder: Path, days: float = 3.0) -> None:
    """Efface les vieux fichiers de sortie de Claude (les tâches terminées depuis plus de quelques jours)."""
    limit = time.time() - days * 86400
    try:
        for f in folder.glob("*.*"):
            if f.suffix in (".out", ".err") and f.stat().st_mtime < limit:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
    finally:
        k.CloseHandle(h)


# Une seule ligne, sans guillemets ni caractères spéciaux : elle est passée en argument,
# et certains environnements Windows (claude.cmd) corrompent les arguments multilignes.
IDENTITY = (
    "Tu t'appelles Jimmy, l'assistant vocal personnel de l'utilisateur, avec un style un peu cyberpunk, "
    "complice et efficace. Tu te présentes toujours comme Jimmy et tu réponds à ce nom. "
)
SHORT_STYLE = (
    "Tes réponses sont lues à voix haute en entier : réponds en français naturel, du tac au tac, comme à l'oral. "
    "Va droit au but : donne la réponse tout de suite en une à trois phrases courtes, sans introduction, "
    "sans formule de politesse, sans reformuler la question, sans récapitulatif ni conseil non demandé. "
    "Une seule idée par phrase, aucun titre. Ne développe que si l'utilisateur te le demande. "
)
LONG_STYLE = (
    "Mode discussion longue : l'utilisateur veut des réponses complètes. Réponds en français de façon "
    "détaillée et bien organisée : une courte phrase de réponse d'abord, puis le détail dans un ordre logique "
    "(contexte, étapes ou explications, conclusion), avec des titres de niveau deux (## Titre) pour chaque partie "
    "quand il y a plus de deux idées, des listes à tirets ou numérotées pour les étapes, et du gras pour les mots clés. "
    "Reste concret et sans remplissage. Tout le texte est lu à voix haute, donc écris des phrases qui sonnent bien à l'oral. "
)
SPEECH_RULES = (
    "Les blocs de code s'affichent à l'écran avec un bouton copier mais ne sont jamais lus : "
    "juste avant chaque bloc, dis en une phrase ce qu'il fait et ce que l'utilisateur doit en faire. "
    "Pas de tableaux ni de liens bruts. Mise en forme markdown propre : paragraphes courts separes par une ligne vide, "
    "listes avec un tiret, gras avec deux etoiles pour les mots cles, noms de fichiers ou de commandes entre accents graves, "
    "code dans un bloc avec son langage, jamais de points ou de symboles isoles et pas de puces decoratives. Termine par une question uniquement si tu attends vraiment "
    "une réponse de l'utilisateur. "
)
SYSTEM_PROMPT = (
    "Quand la demande concerne des fichiers, du code, le site web ou le serveur, fais le travail toi-même "
    "avec tes outils, puis résume en une ou deux phrases ce que tu as trouvé ou modifié (noms de fichiers à l'appui). "
    "Pour un site : lis d'abord le code concerné, fais la modification minimale nécessaire, vérifie le résultat. "
    "Chaque message est une session courte : tout test, déploiement ou commande longue se lance au premier plan "
    "(délai long, jusqu'à 10 minutes) et tu attends le résultat avant de répondre ; rien en arrière-plan, "
    "et jamais de promesse de résultat « plus tard » ou « à la fin ». "
    "Si une information te manque, pose une seule question courte. "
)
# Ajouté seulement en mode autonomie (permission_mode = bypassPermissions).
AUTONOMY_PROMPT = (
    "Accord permanent de l'utilisateur : n'en demande jamais avant d'agir. Modifie, teste, déploie "
    "(sauvegarde avant, vérification après), supprime tes fichiers de travail, installe les outils prévus, "
    "puis dis ce que tu as fait. Jamais : saisir un mot de passe, jeton ou clé à sa place, créer un compte, "
    "--force, --no-verify, DROP ou TRUNCATE. "
)
# Garde-fous techniques : refusés même en mode autonomie (les règles « deny » passent avant « bypass »).
GUARD_DENY = [
    "Bash(git push --force*)", "Bash(git push -f*)", "Bash(git push * --force*)", "Bash(git push * -f)",
    "Bash(*--no-verify*)", "Bash(*DROP TABLE*)", "Bash(*DROP DATABASE*)", "Bash(*TRUNCATE*)",
    "PowerShell(git push --force*)", "PowerShell(git push -f*)", "PowerShell(*--no-verify*)",
    "PowerShell(*DROP TABLE*)", "PowerShell(*DROP DATABASE*)", "PowerShell(*TRUNCATE*)",
]


def _mem_hint() -> str:
    """Une seule phrase : la mémoire de Jimmy (jamais son contenu dans le prompt)."""
    if getattr(sys, "frozen", False):
        run = f"{sys.executable} --mem"          # Jimmy.exe sait aussi servir de commande mémoire
    else:
        script = app_dir() / "jimmy_mem.py"
        if not script.exists():
            return ""
        run = f"{sys.executable} {script}"
    return (f" Mémoire : avant de chercher à l'aveugle ou de redemander, fais {run} search mots ; "
            f"quand une décision, un chemin, une règle ou un état de projet importe, fais {run} add "
            "(jamais de secret dedans). ")


def _music_hint() -> str:
    """Consigne pour la musique : passe par play_youtube.py (un seul onglet, lecture directe)."""
    script = app_dir() / "play_youtube.py"
    if not script.exists():
        return ""
    py = sys.executable if not getattr(sys, "frozen", False) else "python"
    return (
        " Pour mettre de la musique ou une vidéo YouTube, lance directement la commande "
        f"{py} {script} suivie des mots de recherche, sans autre étape : elle ouvre la vidéo "
        "dans Brave en un seul onglet. Une fois la commande lancée, ne réponds rien du tout "
        "(ta voix couvrirait la musique), sauf si elle échoue."
    )


def _volume_hint() -> str:
    """Consigne pour le volume de la musique (Brave uniquement, pas celui de Windows)."""
    script = app_dir() / "brave_volume.ps1"
    if not script.exists():
        return ""
    run = f"powershell -NoProfile -ExecutionPolicy Bypass -File {script}"
    return (
        " Pour baisser ou monter le son de la musique YouTube, lance directement "
        f"{run} -Change -15 (baisse de 15 points, positif pour monter) ou {run} -Set 40 "
        "(met à 40 pour cent) : ça ne règle que Brave, pas Windows ni ta voix. "
        "Sans option, il affiche le volume actuel. Pour un réglage de volume, une fois la commande "
        "lancée, ne réponds rien du tout (ta voix couvrirait la musique), sauf si elle échoue."
    )


def _discord_hint() -> str:
    """Consigne Discord : MP, vocal, micro... passent par discord_control.py (app Discord ouverte)."""
    script = app_dir() / "discord_control.py"
    if not script.exists():
        return ""
    py = sys.executable if not getattr(sys, "frozen", False) else "python"
    run = f"{py} {script}"
    return (
        " Discord : tout ce qui parle de MP, message à quelqu'un, salon vocal, vocal, mute ou sourdine "
        f"concerne l'app Discord de ce PC. Pour un MP lance {run} dm PSEUDO MESSAGE "
        "(le pseudo tel que l'utilisateur le dit, même si sur Discord il est écrit en police "
        f"spéciale : le script le retrouve et vérifie avant d'envoyer). Pour rejoindre un vocal : {run} "
        f"join NOM_DU_SALON --server NOM_DU_SERVEUR. Pour quitter le vocal : {run} leave. "
        f"Micro coupé ou sourdine : {run} mute ou {run} deafen. Envoie directement quand la demande "
        "est claire, et redis en une phrase ce que le script a affiché."
    )


# Mots qui font charger les plugins (navigateur, DevTools...) même en mode économie.
_MCP_WORDS = re.compile(
    r"playwright|devtools|chrome|lighthouse|navigateur|capture d.?ecran|screenshot|mcp|plugin|accessibilite"
    r"|vercel|supabase|firecrawl|figma|netlify|context7|gamma|zoho|connecteur"
    r"|teste (le|la|ma|mon) (site|page)|console du (site|navigateur)"
)
PLUGINS_NEEDED = "PLUGINS_NEEDED"


class ClaudeBridge:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session_id = None
        self._proc = None
        self._cancelled = False
        self._lock = threading.Lock()
        # Outils refusés au dernier appel (Jimmy demande l'accord à voix haute).
        self.pending_tools = []
        # Outils déjà autorisés mais bloqués quand même (validation à l'écran nécessaire).
        self.blocked_tools = []
        # Outils autorisés oralement pour cette session de Jimmy.
        self.session_tools = []
        # Étapes en direct (lecture, modification, commande...) : appelé depuis le thread de travail.
        self.on_step = None
        # % de la limite de session (mis à jour par la fenêtre) pour le mode économie auto.
        self.usage_pct = 0.0
        self._no_effort = False
        self._need_mcp = False   # plugins nécessaires pour ce message (mode économie)
        self.context_tokens = 0  # taille du contexte de la conversation en cours (tokens)
        # Demandes d'autorisation affichées dans la fenêtre de Jimmy : ask(outil, entrée) -> (autorisé, retenir).
        self.perm_ask = None
        self._perm_server = None
        self._state_path = data_dir() / "state.json"
        # Entrée standard du processus en cours : reste ouverte pendant la tâche pour pouvoir ajouter du contexte.
        self._stdin = None
        self._injected = 0
        self._close_timer = None
        self._result_seen = False
        self._detached = False   # Jimmy se ferme alors qu'une tâche tourne : on la laisse continuer
        self._job_path = data_dir() / "job.json"
        self._load_state()

    # ------------------------------------------------------------------ état
    def _load_state(self) -> None:
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if data.get("workdir") == self.workdir():
                self.session_id = data.get("session_id")
                if self.session_id:
                    self.context_tokens = self._transcript_tokens(self.session_id)
        except (OSError, ValueError):
            pass

    def _save_state(self) -> None:
        try:
            self._state_path.write_text(
                json.dumps({"session_id": self.session_id, "workdir": self.workdir()}),
                encoding="utf-8",
            )
        except OSError:
            pass

    def reset(self) -> None:
        """Nouvelle conversation."""
        self.session_id = None
        self.context_tokens = 0
        self._save_state()

    def _transcript_tokens(self, session_id: str) -> int:
        import sessions
        return sessions.context_tokens(self.workdir(), session_id)

    def set_session(self, session_id: str) -> None:
        """Reprend une conversation existante de Claude Code."""
        self.session_id = session_id
        self.context_tokens = self._transcript_tokens(session_id)
        self.pending_tools = []
        self.blocked_tools = []
        self._save_state()

    def open_in_terminal(self, prompt: str = "") -> bool:
        """Ouvre la conversation en cours dans Claude Code (nouvelle fenêtre de terminal).

        prompt : demande déjà écrite et envoyée au démarrage (une seule ligne, sans guillemets,
        pour ne pas être corrompue par claude.cmd).
        """
        cli = self.find_cli()
        if not cli:
            return False
        cmd = [cli] + (["--resume", self.session_id] if self.session_id else [])
        prompt = " ".join(prompt.replace('"', "'").split())
        if prompt:
            cmd.append(prompt)
        flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        subprocess.Popen(cmd, cwd=self.workdir(), creationflags=flags)
        return True

    # ------------------------------------------------------------- environnement
    def workdir(self) -> str:
        wd = self.cfg.get("workdir")
        return wd if wd and Path(wd).is_dir() else str(Path.home())

    def find_cli(self):
        configured = self.cfg.get("claude_path")
        if configured and Path(configured).exists():
            return configured
        found = shutil.which("claude")
        if found:
            return found
        home = Path.home()
        appdata = os.environ.get("APPDATA", "")
        candidates = [
            home / ".local" / "bin" / "claude.exe",
            home / ".local" / "bin" / "claude",
            Path(appdata) / "npm" / "claude.cmd" if appdata else None,
        ]
        for c in candidates:
            if c and c.exists():
                return str(c)
        return None

    # ------------------------------------------------------------------ appels
    def ask(self, text: str) -> str:
        cli = self.find_cli()
        if not cli:
            raise ClaudeError(
                "Claude Code est introuvable. Installe-le (voir le README), connecte-toi avec "
                "la commande « claude », puis relance Jimmy."
            )
        self._cancelled = False
        try:
            return self._with_plugins(cli, text)
        except ClaudeError as e:
            msg = str(e).lower()
            if self.session_id and not self._cancelled and "no conversation" in msg:
                self.session_id = None
                self._save_state()
                return self._run(cli, text, resume=False)
            if not self._cancelled and "effort" in msg and self.cfg.get("effort") and not self._no_effort:
                self._no_effort = True   # modèle sans niveau d'effort : on réessaie sans
                try:
                    return self._run(cli, text, resume=bool(self.session_id))
                finally:
                    self._no_effort = False
            raise

    def _lean(self) -> bool:
        """Mode économie actif pour cet appel : les plugins MCP ne sont pas chargés."""
        return bool(self.cfg.get("lean_mcp")) and not self._need_mcp

    def _with_plugins(self, cli: str, text: str) -> str:
        """Plugins chargés seulement si le message les évoque, ou si Claude dit qu'il en a besoin."""
        self._need_mcp = bool(_MCP_WORDS.search(fold(text)))
        out = self._run(cli, text, resume=bool(self.session_id))
        if (self._lean() and not self._cancelled
                and out.strip().strip(".! ").upper() == PLUGINS_NEEDED):
            self._need_mcp = True
            if self.on_step:
                self.on_step("Chargement des plugins")
            out = self._run(cli, text, resume=bool(self.session_id))
        return out

    # ------------------------------------------------------------ modèle / coût
    def eco_active(self) -> bool:
        """Mode économie : la session dépasse le seuil choisi, on bascule sur un modèle moins cher."""
        return bool(self.cfg.get("eco_auto")) and self.usage_pct >= float(self.cfg.get("eco_threshold", 85))

    def effective_model(self) -> str:
        if self.eco_active() and self.cfg.get("eco_model"):
            return self.cfg.get("eco_model")
        return self.cfg.get("model") or ""

    def _build_cmd(self, cli: str, resume: bool) -> list:
        style = LONG_STYLE if self.cfg.get("long_mode") else SHORT_STYLE
        auto = self.cfg.get("permission_mode") == "bypassPermissions"
        system = (IDENTITY + style + SPEECH_RULES + SYSTEM_PROMPT + (AUTONOMY_PROMPT if auto else "")
                  + _mem_hint() + _music_hint() + _volume_hint() + _discord_hint())
        projects = [" ".join(l.split()) for l in str(self.cfg.get("projects_text", "")).splitlines() if l.strip()]
        if projects:
            system += (" Carte des dossiers de l'utilisateur (va directement au bon endroit, sans explorer "
                       "ni chercher à l'aveugle) : " + " ; ".join(projects) + ".")
        if self._lean():
            system += (" Les plugins et connecteurs (Playwright, DevTools, Vercel, Supabase, Firecrawl, Figma, Netlify...) ne sont pas chargés pour économiser des "
                       f"tokens. Si une tâche en a vraiment besoin, réponds uniquement {PLUGINS_NEEDED} : "
                       "Jimmy te relancera aussitôt avec les plugins chargés.")
        if self.cfg.get("show_steps", True):
            system += (" Pendant que tu travailles, avant chaque action ou groupe d'actions, écris une courte phrase "
                       "en français simple qui dit ce que tu fais et ce que tu en déduis (par exemple : « Je regarde "
                       "comment la page boutique calcule les prix, pour trouver d'où vient l'écart. »). "
                       "Pas de noms de variables ni de code dans ces phrases. Ta réponse finale reste courte.")
        browser = str(self.cfg.get("browser", "")).strip()
        if browser:
            system += f" Tout ce qui passe par un navigateur s'ouvre dans {browser}."
        extra = " ".join(str(self.cfg.get("extra_instructions", "")).split())
        if extra:
            system += " Contexte de l'utilisateur : " + extra
        custom = " ".join(str(self.cfg.get("custom_prompt", "")).split())
        if custom:
            system += " " + custom
        cmd = [
            cli,
            "-p",
            # stream-json : chaque étape arrive en direct (affichée à l'écran, aucun token en plus).
            "--output-format", "stream-json", "--verbose",
            # Entrée en flux : on peut envoyer d'autres messages PENDANT que Claude travaille (ajout de contexte).
            "--input-format", "stream-json",
            "--permission-mode", self.cfg.get("permission_mode", "bypassPermissions"),
            "--append-system-prompt", system,
        ]
        model = self.effective_model()
        if model:
            cmd += ["--model", model]
        effort = self.cfg.get("effort")
        if effort and not self._no_effort:
            cmd += ["--effort", effort]
        if resume and self.session_id:
            cmd += ["--resume", self.session_id]
        tools = list(self.cfg.get("allowed_tools") or [])
        tools += [t for t in self.session_tools if t not in tools]
        if tools:
            cmd += ["--allowedTools", ",".join(tools)]
        if self.cfg.get("permission_mode") == "bypassPermissions":
            # Mode autonomie : plus aucune demande, donc pas de serveur d'autorisation à charger (économise des tokens).
            # Les garde-fous (--force, DROP...) restent refusés : les règles « deny » passent avant « bypass ».
            if self.cfg.get("guard_deny", True):
                cmd += ["--disallowedTools", ",".join(GUARD_DENY)]
        else:
            cmd += self._perm_args()
        if self._lean():
            cmd.append("--strict-mcp-config")      # seul le serveur d'autorisation de Jimmy est chargé
        return cmd

    def _perm_args(self) -> list:
        """Branche les demandes d'autorisation sur la fenêtre de Jimmy (au lieu de refuser ou d'ouvrir un terminal)."""
        script = app_dir() / "perm_mcp.py"
        if not (self.perm_ask and self.cfg.get("ui_permissions", True)
                and (script.exists() or getattr(sys, "frozen", False))):
            return []
        try:
            if self._perm_server is None:
                from perm_server import PermServer
                self._perm_server = PermServer(self._ask_user)
            if getattr(sys, "frozen", False):
                command, args = sys.executable, ["--perm-mcp"]     # Jimmy.exe sert lui-même de serveur d'autorisation
            else:
                command, args = sys.executable, [str(script)]
            conf = {"mcpServers": {"jimmyperm": {
                "command": command, "args": args,
                "env": {"JIMMY_PERM_PORT": str(self._perm_server.port), "JIMMY_PERM_TOKEN": self._perm_server.token,
                        "JIMMY_PERM_WAIT": str(int(self.cfg.get("perm_timeout", 120)) + 30)},
            }}}
            path = Path(tempfile.gettempdir()) / "jimmy_perm_mcp.json"
            path.write_text(json.dumps(conf), encoding="utf-8")
        except Exception:  # noqa: BLE001
            return []
        return ["--mcp-config", str(path), "--permission-prompt-tool", "mcp__jimmyperm__approve"]

    def _ask_user(self, tool_name: str, tool_input):
        allow, remember = self.perm_ask(tool_name, tool_input)
        if allow and remember and tool_name not in self.session_tools:
            self.session_tools.append(tool_name)
        return allow, remember

    def _run(self, cli: str, text: str, resume: bool) -> str:
        cmd = self._build_cmd(cli, resume)
        if self._perm_server is not None:
            self._perm_server.answered = 0
        self.pending_tools = []
        self.blocked_tools = []
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        # La sortie de Claude va dans un FICHIER (pas un tuyau) : si Jimmy se ferme ou redémarre en pleine tâche,
        # Claude continue et finit d'écrire sa réponse ; le prochain Jimmy la retrouve (voir recover_job).
        jobs = data_dir() / "jobs"
        jobs.mkdir(parents=True, exist_ok=True)
        _purge_old_jobs(jobs)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_path, err_path = jobs / f"{stamp}.out", jobs / f"{stamp}.err"
        self._detached = False
        try:
            out_f, err_f = open(out_path, "wb"), open(err_path, "wb")
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=out_f,
                    stderr=err_f,
                    cwd=self.workdir(),
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=flags,
                )
            finally:
                out_f.close()
                err_f.close()
        except OSError as e:
            raise ClaudeError(f"Impossible de lancer Claude Code : {e}")
        self._job_path = data_dir() / "job.json"
        try:
            self._job_path.write_text(json.dumps({
                "pid": proc.pid, "out": str(out_path), "session_id": self.session_id,
                "started": time.time(),
            }), encoding="utf-8")
        except OSError:
            pass

        with self._lock:
            self._proc = proc
            self._stdin = proc.stdin
            self._injected = 0
            self._result_seen = False
        timed_out = threading.Event()

        def _timeout() -> None:
            timed_out.set()
            self._kill(proc)

        # Délai d'INACTIVITÉ : il repart à zéro à chaque signe de vie de Claude Code,
        # donc une longue tâche qui avance n'est plus coupée au milieu.
        idle_limit = float(self.cfg.get("timeout_seconds", 1800))
        timer_box = [None]

        def _arm() -> None:
            old = timer_box[0]
            if old is not None:
                old.cancel()
            t = threading.Timer(idle_limit, _timeout)
            t.daemon = True
            t.start()
            timer_box[0] = t

        class _TimerHandle:
            @staticmethod
            def cancel() -> None:
                if timer_box[0] is not None:
                    timer_box[0].cancel()

        timer = _TimerHandle()
        _arm()
        final, raw = None, []
        try:
            # Le message passe par l'entrée standard (JSON, une ligne) : aucun souci de guillemets ou d'accents.
            # L'entrée reste ouverte : inject() peut y ajouter du contexte tant que la tâche tourne.
            try:
                self._write_user(proc, text)
            except OSError:
                pass
            for line in self._tail_lines(proc, out_path):
                _arm()
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except ValueError:
                    raw.append(line)
                    continue
                if not isinstance(evt, dict):
                    continue
                if evt.get("type") == "assistant":
                    u = (evt.get("message") or {}).get("usage") or {}
                    tot = sum(int(u.get(k) or 0) for k in
                              ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                    if tot:
                        self.context_tokens = tot
                if evt.get("type") == "result":
                    final = evt
                    self._on_result(proc)
                elif evt.get("type") == "system" and evt.get("session_id"):
                    # Session connue dès le départ : même annulée, la discussion reste reprenable.
                    self.session_id = evt["session_id"]
                    self._save_state()
                elif self.on_step:
                    for step in steps_from_event(evt):
                        self.on_step(step)
                if evt.get("type") != "result":
                    self._cancel_close()   # de nouveaux événements : la tâche continue (message ajouté en cours de route)
            if not self._detached:
                proc.wait()
        finally:
            timer.cancel()
            self._cancel_close()
            with self._lock:
                self._proc = None
                self._stdin = None
        if self._detached:
            # Jimmy se ferme : la tâche continue sans lui (job.json reste pour que le prochain Jimmy la retrouve).
            raise ClaudeError("Jimmy s'est fermé : la tâche continue en arrière-plan.")
        try:
            self._job_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            err = err_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            err = ""
        out = "\n".join(raw)

        if self._cancelled:
            raise ClaudeError("Tâche annulée.")
        if timed_out.is_set():
            raise ClaudeError("Claude Code n'a plus donné signe de vie pendant trop longtemps.")
        if final is None:
            if proc.returncode != 0:
                raise ClaudeError((err or out or "Erreur inconnue de Claude Code.").strip()[:500])
            return out.strip() or "Je n'ai rien reçu en retour."
        result, sid, is_error, denied = parse_claude_output(json.dumps(final))

        if sid:
            self.session_id = sid
            self._save_state()
        if is_error:
            raise ClaudeError(result or (err or "").strip()[:500] or "Erreur de Claude Code.")
        if proc.returncode != 0 and not result:
            raise ClaudeError((err or "Claude Code a échoué.").strip()[:500])
        result = result.strip() or "C'est fait."
        allowed = set(self.cfg.get("allowed_tools") or []) | set(self.session_tools)
        # Outil déjà autorisé mais refusé quand même : règle « deny » ou fichier protégé
        # (.claude/settings.json...) qui exige une validation à l'écran. Redemander l'accord
        # tournerait en boucle : on propose d'ouvrir Claude Code dans un terminal.
        if self._perm_server is not None and self._perm_server.answered:
            denied = []   # les demandes ont déjà été posées à l'écran : pas de seconde question
        self.pending_tools = [t for t in denied if t not in allowed]
        self.blocked_tools = [t for t in denied if t in allowed] if not self.pending_tools else []
        if self.blocked_tools:
            result += (
                f"\n\n{', '.join(self.blocked_tools)} est déjà autorisé, mais cette action demande "
                "une validation à l'écran que je ne peux pas faire d'ici. "
                "Tu veux que j'ouvre Claude Code dans un terminal pour que tu valides ?"
            )
        return result

    # ---------------------------------------------------- ajout de contexte en cours de tâche
    @staticmethod
    def _user_line(text: str) -> str:
        msg = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        return json.dumps(msg, ensure_ascii=False) + "\n"

    def _write_user(self, proc, text: str) -> None:
        with self._lock:
            proc.stdin.write(self._user_line(text))
            proc.stdin.flush()

    def can_inject(self) -> bool:
        with self._lock:
            return self._proc is not None and self._stdin is not None and not self._stdin.closed

    def inject(self, text: str) -> bool:
        """Ajoute un message à la tâche EN COURS : Claude le prend en compte dès sa prochaine étape.

        Renvoie False si aucune tâche ne tourne (le message doit alors partir normalement).
        """
        text = (text or "").strip()
        if not text:
            return False
        with self._lock:
            proc, stdin = self._proc, self._stdin
            if proc is None or stdin is None or stdin.closed:
                return False
            try:
                stdin.write(self._user_line(text))
                stdin.flush()
            except (OSError, ValueError):
                return False
            self._injected += 1
            late = self._result_seen
        self._cancel_close()
        if late:
            # le résultat était déjà arrivé : si Claude ne reprend pas, on referme après un court délai
            self._schedule_close(proc, 15.0)
        return True

    def _on_result(self, proc) -> None:
        """Fin d'un tour : on referme l'entrée tout de suite, ou après un court délai si un message a été ajouté
        (au cas où il déclenche un second tour)."""
        self._result_seen = True
        self._schedule_close(proc, 1.5 if self._injected else 0.0)

    def _schedule_close(self, proc, delay: float) -> None:
        self._cancel_close()
        if delay <= 0:
            self._close_stdin(proc)
            return
        t = threading.Timer(delay, self._close_stdin, args=(proc,))
        t.daemon = True
        t.start()
        self._close_timer = t

    def _cancel_close(self) -> None:
        t, self._close_timer = self._close_timer, None
        if t is not None:
            t.cancel()

    def _close_stdin(self, proc) -> None:
        with self._lock:
            try:
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.close()
            except OSError:
                pass
            self._stdin = None

    # ------------------------------------------------------------- autorisations
    def approve(self, remember: bool = False) -> str:
        """Autorise les outils refusés au dernier appel, puis relance la tâche."""
        tools, self.pending_tools = self.pending_tools, []
        for t in tools:
            if t not in self.session_tools:
                self.session_tools.append(t)
        if remember:
            saved = list(self.cfg.get("allowed_tools") or [])
            self.cfg.set("allowed_tools", saved + [t for t in tools if t not in saved])
        return self.ask(
            "L'utilisateur vient d'autoriser " + ", ".join(tools)
            + ". Reprends et termine la tâche précédente."
        )

    def deny(self) -> None:
        self.pending_tools = []

    # --------------------------------------------------------------- annulation
    @staticmethod
    def _kill(proc) -> None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                proc.kill()
        except Exception:
            pass

    def busy_process(self) -> bool:
        """Une tâche de Claude est en cours d'exécution."""
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def detach(self) -> None:
        """Jimmy se ferme : la tâche en cours N'EST PAS arrêtée. Claude finit son travail tout seul
        (sa réponse est écrite dans un fichier) et le prochain Jimmy l'affiche."""
        self._detached = True
        with self._lock:
            proc = self._proc
        if proc is not None:
            self._close_stdin(proc)     # plus de nouveau message : Claude termine le tour en cours puis s'arrête

    # ------------------------------------------------- tâche laissée en arrière-plan
    def _tail_lines(self, proc, path):
        """Lit le fichier de sortie de Claude au fur et à mesure, jusqu'à la fin du processus
        (ou jusqu'à ce que Jimmy se détache : la tâche continue alors sans lui)."""
        buf = b""
        with open(path, "rb") as f:
            while not self._detached:
                chunk = f.read(65536)
                if chunk:
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        yield line.decode("utf-8", "replace")
                    continue
                if proc.poll() is not None:
                    chunk = f.read()          # dernière lecture après la fin du processus
                    if not chunk:
                        break
                    buf += chunk
                    continue
                time.sleep(0.05)
        if buf.strip():
            yield buf.decode("utf-8", "replace")

    def recover_job(self) -> bool:
        """Au démarrage : une tâche lancée par un Jimmy précédent est-elle encore à suivre ?"""
        try:
            self._job = json.loads(self._job_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._job = None
        return bool(self._job)

    def poll_job(self):
        """None s'il n'y a rien à suivre ; ("running", None) ; ("done", texte) ; ("lost", None)."""
        job = getattr(self, "_job", None)
        if not job:
            return None
        final = None
        try:
            with open(job["out"], "rb") as f:
                for raw in f.read().decode("utf-8", "replace").splitlines():
                    if raw.startswith("{") and '"type":"result"' in raw.replace(" ", ""):
                        try:
                            final = json.loads(raw)
                        except ValueError:
                            pass
        except OSError:
            pass
        if final is None:
            if _pid_alive(job.get("pid", 0)):
                return ("running", None)
            self._clear_job()
            return ("lost", None)
        result, sid, is_error, _denied = parse_claude_output(json.dumps(final))
        if sid:
            self.session_id = sid
            self._save_state()
        self._clear_job()
        return ("done", (result or "").strip() or "C'est fait.")

    def _clear_job(self) -> None:
        self._job = None
        try:
            self._job_path.unlink(missing_ok=True)
        except OSError:
            pass

    def cancel(self) -> None:
        self._cancelled = True
        with self._lock:
            proc = self._proc
        if proc is not None:
            self._kill(proc)
