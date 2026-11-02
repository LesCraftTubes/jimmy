"""Fonctions de texte pures (sans dépendance externe), faciles à tester."""
import json
import re
import unicodedata
from difflib import SequenceMatcher

# Mots que les gens disent avant le nom (« Hey Jarvis », « OK Claude »...) : facultatifs.
_PREFIXES = {
    "hey", "hei", "hay", "hai", "he", "eh", "ey", "ok", "okay", "salut",
    "dis", "oh", "et", "bonjour", "hello", "yo",
}
# Whisper déforme parfois le nom : variantes connues.
_ALIASES = {
    "claude": ("clode", "clod", "cloud", "claud", "klod", "clau"),
    "jimmy": ("jimi", "jimy", "jimmi", "jimmie", "jimie", "gimmy", "djimmy", "dimmy", "jemmy",
              "jiminy", "jimmys"),
    "jarvis": ("jarvi", "jarviss", "jarvice", "jervis", "djarvis", "charvis", "jarbis", "jarviz",
               "jarvisse", "garvis", "jaavis"),
}

_HALLUCINATIONS = (
    "sous titr",
    "amara",
    "merci d avoir regarde",
    "abonnez vous",
    "thanks for watching",
    "thank you for watching",
    "sous titrage",
)


def fold(text: str) -> str:
    """Minuscules, sans accents ni ponctuation, en gardant exactement la même longueur."""
    out = []
    for ch in text:
        d = unicodedata.normalize("NFD", ch)
        base = (d[0] if d else ch).lower()[:1] or " "
        out.append(base if (base.isalnum() or base == " ") else " ")
    return "".join(out)


def _tokens(folded: str):
    return [(m.group(), m.start(), m.end()) for m in re.finditer(r"[a-z0-9]+", folded)]


def _match_word(token: str, word: str) -> bool:
    if token == word or token in _ALIASES.get(word, ()):
        return True
    # Tolérance aux petites erreurs de transcription pour les mots d'au moins 5 lettres.
    if len(word) >= 5 and len(token) >= 4 and abs(len(token) - len(word)) <= 2:
        return SequenceMatcher(None, token, word).ratio() >= 0.72
    return False


def apply_corrections(text: str, corrections) -> str:
    """Remplace les mots que Whisper comprend de travers (« chenso man » -> « Chainsaw Man »).

    `corrections` : dict {mal compris: bon texte}, insensible à la casse, mots entiers.
    """
    if not text or not isinstance(corrections, dict):
        return text
    for bad, good in sorted(corrections.items(), key=lambda kv: -len(kv[0])):
        if bad:
            text = re.sub(r"(?<!\w)" + re.escape(bad) + r"(?!\w)", good, text, flags=re.IGNORECASE)
    return text


def extract_wake(text: str, words=("claude",)):
    """Détecte le mot d'éveil au début de la phrase.

    `words` : liste de mots ou d'expressions (« jarvis », « hey claude »...).
    Retourne (détecté, reste_de_la_phrase).
    """
    folded = fold(text)
    toks = _tokens(folded)
    if not toks:
        return False, ""
    phrases = []
    for w in words or ():
        ws = fold(str(w)).split()
        if ws:
            phrases.append(ws)
    for ws in phrases:
        # Le mot d'éveil est pris tel que tu l'as écrit : « hey jimmy » exige « hey » (ou une
        # variante comme « hé », « eh »), « jimmy » tout seul ne suffit pas. Seul un mot d'éveil
        # d'un seul mot tolère un « hey » devant (« Hey Jimmy » réveille bien « jimmy »).
        starts = (0, 1) if len(ws) == 1 and toks[0][0] in _PREFIXES else (0,)
        for s0 in starts:
            seg = toks[s0:s0 + len(ws)]
            if len(seg) == len(ws) and all(
                _match_word(t[0], w) or (w in _PREFIXES and t[0] in _PREFIXES)
                for t, w in zip(seg, ws)
            ):
                rest = text[seg[-1][2]:].strip(" \t\n,.;:!?-–—…'\"")
                return True, rest
    return False, ""


def collapse_repeats(text: str) -> str:
    """Whisper boucle parfois (« le le le le le », ou la même phrase 5 fois) : on garde une seule occurrence
    d'un mot répété 3 fois de suite ou plus, et d'une suite de 2 à 8 mots répétée 3 fois de suite ou plus."""
    words = text.split()
    if len(words) < 3:
        return text
    keys = [fold(w) for w in words]
    changed = True
    while changed:
        changed = False
        for n in range(1, 9):
            i = 0
            while i + 3 * n <= len(words):
                block = keys[i:i + n]
                reps = 1
                while keys[i + reps * n:i + (reps + 1) * n] == block:
                    reps += 1
                if reps >= 3 and any(block):
                    del words[i + n:i + reps * n]
                    del keys[i + n:i + reps * n]
                    changed = True
                i += 1
    return " ".join(words)


def is_hallucination(text: str) -> bool:
    """Whisper invente parfois du texte sur du bruit (« Sous-titres par... »)."""
    f = " ".join(fold(text).split())
    if not f:
        return True
    return any(h in f for h in _HALLUCINATIONS)


_UNFINISHED = {
    "que", "qu", "de", "du", "des", "le", "la", "les", "l", "un", "une", "et", "ou", "mais",
    "pour", "avec", "sans", "dans", "sur", "en", "a", "au", "aux", "je", "tu", "il", "on",
    "nous", "vous", "ils", "me", "te", "se", "ce", "mon", "ma", "mes", "ton", "ta", "tes",
    "son", "sa", "ses", "si", "quand", "comme", "parce", "puis", "donc", "genre", "est",
    "faut", "veux", "voudrais", "aimerais", "peux", "vais", "qui", "dont", "par", "chez",
    "puisse", "puisses", "voulais", "veut", "aussi", "enfin", "bref",
}


def looks_unfinished(text: str) -> bool:
    """La phrase semble coupée (« …pour que je puisse… ») : on attend la suite plus longtemps."""
    t = text.rstrip()
    if not t or t.endswith(("...", "…", ",")):
        return True
    if t.endswith((".", "!", "?")):
        return False
    words = fold(t).split()
    return bool(words) and words[-1] in _UNFINISHED


_BULLET_RE = re.compile(r"^(\s*)[•·–—▪●◦]\s+")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+")
_BLOCK_START_RE = re.compile(r"^\s{0,3}(?:#{1,6}\s|>|[-*_]{3,}\s*$|\|)")


def prepare_markdown(text: str) -> str:
    """Nettoie une réponse avant l'affichage markdown (le rendu de Qt est strict) :
    puces unicode -> « - », ligne vide avant les listes et titres, retours à la ligne gardés,
    points ou symboles isolés retirés, lignes vides en trop supprimées."""
    t = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ").replace("​", "")
    out: list = []
    prev_plain = False      # la ligne précédente est un simple paragraphe
    for raw in t.split("\n"):
        ln = raw.rstrip()
        if re.fullmatch(r"\s*[.·•…,;:]+\s*", ln):
            ln = ""                                   # point (ou virgule...) tout seul sur une ligne
        ln = _BULLET_RE.sub(r"\1- ", ln)
        ln = re.sub(r"^(\s{0,3}#{1,6})(?=[^#\s])", r"\1 ", ln)   # « #Titre » -> « # Titre »
        if not ln.strip():
            if out and out[-1] != "":
                out.append("")
            prev_plain = False
            continue
        is_list = bool(_LIST_RE.match(ln))
        is_block = is_list or bool(_BLOCK_START_RE.match(ln))
        indented = ln.startswith(("  ", "\t")) and not is_list
        if is_block and out and out[-1] != "" and not (is_list and not prev_plain):
            out.append("")                            # liste / titre collé à un paragraphe : on aère
        elif prev_plain and not is_block and not indented:
            out[-1] = out[-1] + "  "                  # retour à la ligne conservé (pas collé en une ligne)
        out.append(ln)
        prev_plain = not is_block and not indented
        if re.match(r"^\s{0,3}#{1,6}\s", ln):
            prev_plain = False
    return "\n".join(out).strip("\n")


def clean_for_tts(text: str) -> str:
    """Retire ce qui ne doit pas être lu à voix haute (code, liens, symboles markdown)."""
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"https?://\S+", " lien ", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)
    t = re.sub(r"[*_~|]+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def split_for_speech(text: str, first_max: int = 70, max_chars: int = 220) -> list:
    """Découpe en morceaux à lire : une 1re phrase courte (pour démarrer vite), puis des
    groupes de phrases. Rien n'est coupé ni résumé : tout le texte est lu."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…:;])\s+", text) if s.strip()]
    pieces = []
    for s in sentences:
        while len(s) > max_chars:  # phrase très longue : coupe à une virgule ou un espace
            cut = max(s.rfind(", ", 0, max_chars), s.rfind(" ", 0, max_chars))
            cut = cut if cut > 40 else max_chars
            pieces.append(s[:cut + 1].strip())
            s = s[cut + 1:].strip()
        if s:
            pieces.append(s)
    chunks = []
    for s in pieces:
        limit = first_max if len(chunks) <= 1 else max_chars
        if chunks and len(chunks) > 1 and len(chunks[-1]) + len(s) + 1 <= limit:
            chunks[-1] += " " + s
        else:
            chunks.append(s)
    return chunks


def limit_for_speech(text: str, max_chars: int = 900) -> str:
    """Évite de lire un roman : on coupe à une fin de phrase et on renvoie vers l'écran."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    idx = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if idx > 200:
        cut = cut[: idx + 1]
    return cut.strip() + " La suite est affichée à l'écran."


def parse_claude_output(raw: str):
    """Analyse la sortie `claude -p --output-format json`.

    Retourne (texte, session_id, is_error, outils_refusés). Lève ValueError si ce n'est pas du JSON.
    """
    data = json.loads(raw.strip())
    if isinstance(data, list):
        results = [d for d in data if isinstance(d, dict) and d.get("type") == "result"]
        data = results[-1] if results else {}
    if not isinstance(data, dict):
        raise ValueError("format inattendu")
    denied = []
    for d in data.get("permission_denials") or []:
        name = d.get("tool_name") if isinstance(d, dict) else None
        if name and name not in denied:
            denied.append(name)
    return (
        str(data.get("result") or ""),
        data.get("session_id"),
        bool(data.get("is_error")),
        denied,
    )


_TOOL_LABELS = {
    "Read": "Lecture", "Edit": "Modification", "MultiEdit": "Modification", "Write": "Écriture",
    "Glob": "Recherche de fichiers", "Grep": "Recherche", "Bash": "Commande",
    "PowerShell": "Commande", "WebFetch": "Lecture web", "WebSearch": "Recherche web",
    "TodoWrite": "Plan", "Task": "Sous-agent", "Agent": "Sous-agent", "Skill": "Compétence",
    "NotebookEdit": "Notebook", "LS": "Exploration", "ToolSearch": "Outils", "BashOutput": "Commande",
    "KillShell": "Commande",
}


def _short(text: str, n: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _where(inp) -> str:
    """Nom court du fichier ou du dossier visé par l'outil."""
    path = inp.get("file_path") or inp.get("notebook_path") or inp.get("path")
    return re.split(r"[\\/]", str(path).rstrip("\\/"))[-1] if path else ""


# Reconnaissance des commandes -> phrase simple qui dit CE QUE fait la commande (fichier, dossier, serveur...).
_PATH_RE = re.compile(r"""(?:["']?)((?:[A-Za-z]:)?[\w./\\~$-]*[./\\][\w./\\~$-]*\w)(?:["']?)""")


def _last_path(text: str) -> str:
    """Nom du dernier fichier ou dossier cité dans une commande."""
    found = [m.group(1) for m in _PATH_RE.finditer(text) if not m.group(1).startswith("-")]
    return re.split(r"[\\/]", found[-1].rstrip("\\/"))[-1] if found else ""


def _first_quoted(text: str) -> str:
    m = re.search(r"""["']([^"']{2,60})["']""", text)
    return m.group(1) if m else ""


def _ssh_remote(cmd: str):
    """Commande lancée sur le serveur : ce qui suit « ssh [options] hôte »."""
    toks = re.findall(r"""(?:[^\s"']+|"[^"]*"|'[^']*')+""", cmd)
    k = [i for i, t in enumerate(toks) if t.lower() in ("ssh", "ssh.exe")]
    if not k:
        return None
    i, takes_arg = k[0] + 1, set("iploFJLRDESwbcm")
    while i < len(toks):
        t = toks[i]
        if t.startswith("-"):
            i += 2 if (len(t) == 2 and t[1] in takes_arg) else 1
        else:
            break
    host = toks[i] if i < len(toks) else ""
    rest = " ".join(toks[i + 1:]).strip()
    if len(rest) >= 2 and rest[0] == rest[-1] and rest[0] in "\"'":
        rest = rest[1:-1]
    return host, rest


_GIT = {"status": "je regarde l'état des fichiers du projet", "diff": "je compare les modifications",
        "log": "je relis l'historique du projet", "add": "je prépare les modifications à enregistrer",
        "commit": "j'enregistre les modifications", "push": "j'envoie les modifications",
        "pull": "je récupère les dernières modifications", "clone": "je télécharge le projet",
        "init": "je crée le dépôt du projet", "checkout": "je change de version", "branch": "je regarde les branches"}


def _describe_one(cmd: str, remote: bool = False, depth: int = 0) -> str:
    """Phrase simple pour UNE commande, d'après son NOM (pas le contenu des chemins). "" si inconnue."""
    where = " sur le serveur" if remote else ""
    first = re.split(r"\s*(?:\|\||&&|\||;)\s*", cmd.strip())[0]       # on décrit la 1re commande de la chaîne
    m = re.match(r"\s*(?:sudo\s+|&\s*)?[\"']?([\w./\\:-]+)", first)
    word = re.split(r"[\\/]", m.group(1))[-1].lower() if m else ""
    word = re.sub(r"\.(exe|cmd|bat|ps1)$", "", word)
    rest = first[m.end():] if m else first
    low = first.lower()
    f = _last_path(rest)
    if word == "ssh":
        parsed = _ssh_remote(cmd)
        if parsed and parsed[1] and depth < 2:
            return _describe_cmd(parsed[1], True, depth + 1)
        return "je me connecte au serveur"
    if word in ("scp", "sftp", "winscp", "rsync"):
        up = bool(re.search(r"\s\S+\s+\S+@\S+:", first))
        verb, dest = ("j'envoie", " vers le serveur") if up else ("je récupère", " depuis le serveur")
        return f"{verb} {f or 'des fichiers'}{dest}"
    if word == "mysqldump":
        return f"je sauvegarde la base de données{where}"
    if word in ("mysql", "mariadb", "sqlite", "sqlite3"):
        if re.search(r"\b(update|insert|alter|create|replace|delete|drop|truncate)\b", low):
            return f"je modifie la base de données{where}"
        if re.search(r"\b(select|show|describe)\b", low):
            return f"je lis des données dans la base{where}"
        return f"je consulte la base de données{where}"
    if word == "phpstan" or (word == "php" and re.search(r"\s-l\b", rest)):
        return f"je vérifie que {f or 'le code'} est correct{where}"
    if word == "php":
        return f"je lance {f or 'un script PHP'}{where}"
    if word in ("python", "python3", "py", "pythonw"):
        return f"je lance le script {f or 'Python'}{where}"
    if word == "git":
        for k2, v in _GIT.items():
            if re.search(rf"\b{k2}\b", rest):
                return v + " (git)"
        return "j'utilise git"
    if word in ("npm", "npx", "composer", "pip", "winget", "node"):
        return ("j'installe ou je mets à jour des outils du projet"
                if re.search(r"install|update|add|require|upgrade", rest) else "je lance un outil du projet")
    if word in ("rm", "del", "rmdir", "rd", "remove-item"):
        return f"je supprime {f or 'des fichiers'}{where}"
    if word in ("mkdir", "md", "new-item"):
        return f"je crée {f or 'un dossier'}{where}"
    if word in ("cp", "copy", "xcopy", "robocopy", "copy-item") and re.search(r"bak|backup|sauv|\.old|\.orig", rest, re.I):
        names = [re.split(r"[\\/]", t.rstrip("\\/"))[-1] for t in re.findall(r"[^\s\"']+", rest) if not t.startswith("-")]
        return f"je fais une sauvegarde de {names[0] if names else 'un fichier'}{where}"
    if word in ("cp", "copy", "xcopy", "robocopy", "copy-item"):
        return f"je copie {f or 'des fichiers'}{where}"
    if word in ("mv", "move", "ren", "rename", "move-item"):
        return f"je déplace ou je renomme {f or 'des fichiers'}{where}"
    if word in ("tar", "zip", "unzip", "7z", "compress-archive", "expand-archive"):
        return f"je crée ou j'ouvre une archive{where}"
    if word == "sed" and re.search(r"\s-n\b", rest) and not re.search(r"\s-i", rest):
        rg = re.search(r"(\d+)\s*,\s*(\d+)\s*p", rest)
        return (f"je lis les lignes {rg.group(1)} à {rg.group(2)} de {f or 'un fichier'}{where}" if rg
                else f"je lis un extrait de {f or 'un fichier'}{where}")
    if word in ("screen", "tmux") and re.search(r"stuff|send-keys", rest):
        inner = re.search(r"""(?:stuff|send-keys)\s+["']([^"']{1,90})""", rest)
        text = inner.group(1) if inner else ""
        if "reload" in text:
            nm = re.search(r"([\w$.-]+\.sk)", text)
            name = re.split(r"[\\/]", nm.group(1))[-1] if nm and "$" not in nm.group(1) else ""
            return f"je recharge {name or 'les scripts'} dans le serveur Minecraft"
        return "j'envoie une commande à la console du serveur"
    if word in ("kill", "pkill", "killall", "java"):
        return f"je gère le serveur de jeu{where}"
    if word == "diff":
        return f"je compare des fichiers{where}"
    if word in ("wc", "sort", "uniq", "cut"):
        return ""
    if word in ("sed", "awk", "set-content", "out-file", "tee") or (">" in first and word in ("echo", "printf", "cat")):
        return f"j'écris dans {f or 'un fichier'}{where}"
    if word in ("grep", "rg", "select-string", "findstr", "egrep"):
        q = _first_quoted(rest)
        return f"je cherche « {q} » dans {f or 'les fichiers'}{where}" if q else f"je cherche dans {f or 'les fichiers'}{where}"
    if word == "tail":
        return f"je lis la fin de {f or 'un fichier'}{where}"
    if word == "head":
        return f"je lis le début de {f or 'un fichier'}{where}"
    if word in ("cat", "type", "get-content", "less", "more", "bat"):
        return f"je lis {f or 'un fichier'}{where}"
    if word in ("ls", "dir", "get-childitem", "find", "tree", "stat", "du", "ll"):
        return f"je regarde le contenu de {f or 'un dossier'}{where}"
    if word in ("curl", "wget", "invoke-webrequest", "invoke-restmethod"):
        host = re.search(r"https?://([^/\s\"']+)", first)
        return f"je récupère une page ({host.group(1)})" if host else "je récupère une page sur internet"
    if word in ("systemctl", "service", "nginx", "apache2", "apachectl", "httpd"):
        return f"je gère un service{where}"
    if word in ("chmod", "chown", "icacls"):
        return f"je règle les droits de {f or 'des fichiers'}{where}"
    if word in ("echo", "write-host", "pwd", "whoami", "hostname", "date", "test", "which", "where"):
        return f"je fais une petite vérification{where}"
    if word in ("powershell", "pwsh", "cmd", "bash", "sh"):
        inner = re.search(r"""(?:-command|-c|/c)\s+["']?(.+?)["']?\s*$""", rest, re.I)
        if inner and depth < 2:
            return _describe_cmd(inner.group(1), remote, depth + 1)
    return ""


_SKIP_WORDS = {"cd", "sleep", "echo", "set", "export", "true", "false", "test", "pwd", "ts", "eof", "done", "do", "then",
               "fi", "else", "for", "if", "while", "return", "print", "import", "def", "local", "exit", "cut", "head",
               "sort", "uniq", "wc", "tr", "xargs", "basename", "dirname", "ls2"}
_FILE_RE = re.compile(r"""['"]([^'"\n]+\.(?:sk|yml|yaml|php|py|json|txt|html|css|js|md|cfg|conf|ini|log|sql|properties))['"]""")


def _py_body(body: str, remote: bool) -> str:
    where = " sur le serveur" if remote else ""
    files = _FILE_RE.findall(body)
    name = re.split(r"[\\/]", files[0])[-1] if files else ""
    if re.search(r"open\([^)]*['\"]w|\.write\(|write_text|\.replace\(", body) and re.search(r"write", body):
        return f"je modifie {name or 'des fichiers'}{where}"
    if re.search(r"open\(|read_text|\.read\(", body):
        return f"je lis et j'analyse {name or 'des fichiers'}{where}"
    return f"je lance un petit script Python{where}"


def _statements(text: str):
    """[(position, instruction)] : on coupe sur ; && || et retours à la ligne, sauf entre guillemets."""
    out, buf, start, quote, k = [], [], 0, "", 0
    while k < len(text):
        ch = text[k]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == "\n" or ch == ";" or text[k:k + 2] in ("&&", "||"):
            out.append((start, "".join(buf)))
            k += 1 if (ch in "\n;") else 2
            buf, start = [], k
            continue
        else:
            buf.append(ch)
        k += 1
    out.append((start, "".join(buf)))
    res = []
    for pos, st in out:
        st = re.sub(r"^(?:do|then|else|elif|while|until)\s+", "", st.strip())
        if st:
            res.append((pos, st))
    return res


def _describe_cmd(cmd: str, remote: bool = False, depth: int = 0) -> str:
    """Résume en une phrase ce que fait une commande, même longue : enchaînements, scripts, serveur."""
    where = " sur le serveur" if remote else ""
    found = []                                            # [(position, phrase)]

    def add(pos, phrase):
        if phrase and all(phrase != q for _, q in found):
            found.append((pos, phrase))

    # script passé par « << EOF » : on regarde ce qui est lancé, pas le texte du script
    texts = [(0, cmd)]
    m = re.search(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)(?:\n\s*\2\b|\Z)", cmd, re.S)
    if m:
        header, body, tail = cmd[:m.start()], m.group(3), cmd[m.end():]
        texts = [(0, header), (m.end(), tail)]
        last = re.split(r"\s*(?:\|\||&&|;|\|)\s*", header.strip())[-1] if header.strip() else ""
        w = re.match(r"\s*(?:sudo\s+)?([\w./\\-]+)", last)
        word = re.split(r"[\\/]", w.group(1))[-1].lower() if w else ""
        if re.search(r"\bssh\b", header) and depth < 2:
            parsed = _ssh_remote(header)
            inner = parsed[1] if parsed else ""
            if re.search(r"\b(bash|sh)\b", inner):          # ssh ... 'bash -s' << EOF : le script tourne sur le serveur
                add(m.start(), _describe_cmd(body, True, depth + 1) if not _is_python(inner) else _py_body(body, True))
            elif "python" in inner:
                add(m.start(), _py_body(body, True))
        elif word.startswith("python") or word == "py":
            add(m.start(), _py_body(body, remote))
        elif word in ("bash", "sh") and depth < 2:
            add(m.start(), _describe_cmd(body, remote, depth + 1))
        elif word in ("cat", "tee"):
            f = _last_path(header)
            add(m.start(), f"j'écris {f or 'un fichier'}{where}")
    for base, text in texts:
        for pos, st in _statements(text):
            w = re.match(r"\s*(?:sudo\s+)?[\"']?([\w./\\-]+)", st)
            word = re.split(r"[\\/]", w.group(1))[-1].lower() if w else ""
            if word in _SKIP_WORDS or not word:
                continue
            if m and base == 0 and word in ("python", "python3", "py", "bash", "sh", "ssh", "cat", "tee"):
                continue                                    # déjà décrit avec le script
            add(base + pos, _describe_one(st, remote, depth))
    # transfert par tar | ssh
    if re.search(r"\btar\b", cmd) and re.search(r"\|\s*ssh\b", cmd):
        add(0, "j'envoie des fichiers vers le serveur")
    if not found:
        return f"je lance une commande{where}" if depth == 0 else ""
    found.sort(key=lambda t: t[0])
    phrases = [q for _, q in found]
    out = " puis ".join(phrases[:2])
    out += f" (et {len(phrases) - 2} autre{'s' if len(phrases) > 3 else ''})" if len(phrases) > 2 else ""
    return out.replace(" de un ", " d'un ").replace(" de une ", " d'une ")


def _is_python(text: str) -> bool:
    return bool(re.search(r"\bpython", text))


def _command_hint(inp) -> str:
    desc = " ".join(str(inp.get("description") or "").split())
    if desc:
        return _short(desc, 170)       # la description écrite par Claude lui-même (en français, voir la consigne)
    return _describe_cmd(str(inp.get("command") or ""))


def describe_tool(name: str, inp) -> str:
    """Étape lisible en français simple : « Lecture · je lis shop.php », « Modification · je modifie... »."""
    inp = inp if isinstance(inp, dict) else {}
    label = _TOOL_LABELS.get(name)
    f = _where(inp)
    if name == "Read":
        detail = f"je lis {f or 'un fichier'}" + (" (un extrait)" if inp.get("limit") else "")
    elif name in ("Edit", "MultiEdit"):
        detail = f"je modifie {f or 'un fichier'}"
    elif name == "Write":
        detail = f"j'écris {f or 'un fichier'}"
    elif name == "NotebookEdit":
        detail = f"je modifie {f or 'un notebook'}"
    elif name == "Grep":
        detail = f"je cherche « {_short(inp.get('pattern', ''), 45)} »" + (f" dans {f}" if f else " dans le projet")
    elif name == "Glob":
        detail = f"je repère les fichiers « {_short(inp.get('pattern', ''), 45)} »"
    elif name == "LS":
        detail = f"je regarde le contenu de {f or 'un dossier'}"
    elif name in ("Bash", "PowerShell"):
        detail = _command_hint(inp)
    elif name == "BashOutput":
        detail = "je regarde où en est la commande lancée"
    elif name == "KillShell":
        detail = "j'arrête une commande en cours"
    elif name == "WebFetch":
        host = re.sub(r"^https?://([^/]+).*$", r"\1", str(inp.get("url", "")))
        detail = f"je consulte la page {host}" if host else "je consulte une page web"
    elif name == "WebSearch":
        detail = f"je cherche « {_short(inp.get('query', ''), 70)} » sur internet"
    elif name in ("Task", "Agent"):
        detail = "je confie une tâche à un assistant" + (f" : {_short(inp.get('description', ''), 100)}" if inp.get("description") else "")
    elif name == "Skill":
        detail = f"j'utilise la compétence {inp.get('skill') or inp.get('name') or ''}".strip()
    elif name == "TodoWrite":
        n = len(inp.get("todos") or [])
        detail = "je mets à jour ma liste de tâches" + (f" ({n})" if n else "")
    elif name == "ToolSearch":
        detail = "je cherche un outil dont j'ai besoin"
    elif name.startswith("mcp__"):
        parts = name.split("__")
        label = "Outil externe"
        detail = f"j'utilise {parts[1] if len(parts) > 1 else 'un plugin'} : {' '.join(parts[2:]).replace('_', ' ')}"
    else:
        detail = ""
    label = label or name.replace("mcp__", "").replace("__", " · ")
    detail = detail.replace(" de un ", " d'un ").replace(" de une ", " d'une ")
    return f"{label} · {detail}" if detail else label


def steps_from_event(evt) -> list:
    """Étapes à afficher pour un événement `claude -p --output-format stream-json`."""
    if not isinstance(evt, dict) or evt.get("type") != "assistant":
        return []
    content = (evt.get("message") or {}).get("content") or []
    if not isinstance(content, list):
        return []
    tools = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"]
    if not tools:
        return []   # message final : c'est la réponse, pas une étape
    steps = []
    for c in content:
        if not isinstance(c, dict):
            continue
        kind = c.get("type")
        if kind == "text" and c.get("text", "").strip():
            steps.append("Analyse · " + _short(c["text"], 260))
        elif kind == "thinking" and str(c.get("thinking", "")).strip():
            steps.append("Réflexion · " + _short(c["thinking"], 260))
        elif kind == "tool_use":
            steps.append(describe_tool(str(c.get("name", "")), c.get("input")))
    return steps


_YES = ("oui", "ouais", "ok", "okay", "vas y", "d accord", "autorise", "valide", "go", "yes")
_NO = ("non", "refuse", "annule", "laisse tomber", "pas question")


def parse_consent(text: str):
    """Réponse à « Tu autorises ? » : (True/False/None, toujours)."""
    f = " ".join(fold(text).split())
    always = any(w in f for w in ("toujours", "tout le temps", "a chaque fois", "definitivement"))
    if any(f == w or f.startswith(w + " ") for w in _NO):
        return False, False
    if any(f == w or f.startswith(w + " ") or f" {w} " in f" {f} " for w in _YES) or always:
        return True, always
    return None, False
