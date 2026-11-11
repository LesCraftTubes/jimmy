# Jimmy

**Un assistant vocal pour Claude Code.** Tu lui parles (ou tu lui écris), et il fait le travail sur ton ordinateur : lire et modifier du code, lancer des commandes, gérer ton site ou ton serveur. Les réponses s'affichent et sont lues à voix haute.

Tout passe par [Claude Code](https://code.claude.com) : ton abonnement Claude suffit, **aucune clé API**. Tout reste sur ton ordinateur.

> *English: Jimmy is a voice assistant on top of Claude Code (Windows). Install it, talk to it, drive it from your phone with the built-in mobile web app. See the English summary at the bottom.*

## Installation (Windows)

1. Télécharge **`Jimmy-Setup-X.Y.Z.exe`** dans la page [Releases](../../releases) du dépôt et lance-le (pas besoin d'être administrateur).
2. Au premier lancement, l'**assistant** :
   - installe **Claude Code** s'il manque (installateur officiel) ;
   - te connecte à ton compte Claude (une page s'ouvre dans ton navigateur) ;
   - te fait choisir ton dossier de travail et la précision de la reconnaissance vocale.
3. Au tout premier démarrage, le modèle vocal se télécharge (une seule fois, l'avancement s'affiche). Ensuite : dis **« Jimmy »** puis ta demande, ou clique sur **Parler**.

**Mises à jour** : Jimmy vérifie les nouvelles versions publiées sur GitHub (réglage `update_repo`) et propose de les installer en un clic.

## Utilisation

- **Parler / « Jimmy »** : après un court silence, la phrase part. **Stop** annule la tâche ou coupe la voix.
- **Pendant qu'il travaille**, tu peux continuer à parler ou écrire : ta précision est **ajoutée à la tâche en cours**, Claude la prend en compte dès sa prochaine étape, sans tout recommencer. Si tu parles quand sa réponse arrive, il ne te coupe pas.
- **Discussions** : celles de Claude Code sont reprises ; « Ouvrir dans Claude Code » continue la même conversation dans le terminal.
- **Économie** : modèle de repli automatique près de la limite de session, plugins chargés seulement quand il faut, reprise de contexte automatique quand la discussion devient trop grosse.

## Appli mobile

Pilote Jimmy depuis ton téléphone, y compris à distance : **Appli mobile** dans la fenêtre de Jimmy → scanne le QR code. C'est une appli web installable (écran d'accueil), avec la voix (micro et lecture des réponses) et le même visuel que Jimmy. **Le PC doit rester allumé avec Jimmy ouvert.**

Trois modes : Wi-Fi (même réseau), Internet (tunnel Cloudflare gratuit, sans compte), ou ton adresse (Tailscale, domaine…). Détails et sécurité : [docs/MOBILE.md](docs/MOBILE.md).

## Réglages

Le fichier `config.json` (dans `%APPDATA%\Jimmy` une fois installé) se règle surtout par le bouton ⚙ de la fenêtre. Principaux champs :

| Réglage | Rôle |
|---|---|
| `permission_mode` | `acceptEdits` (modifie les fichiers sans demander) ou `bypassPermissions` (aucune demande). |
| `custom_prompt` / `extra_instructions` | Tes habitudes, tes outils, ton serveur : ajoutés aux consignes de Jimmy. Jamais de mot de passe ici. |
| `browser` | Navigateur à utiliser (ex. `Brave`). |
| `whisper_model` | `tiny`, `base`, `small`, `medium` : précision de la reconnaissance vocale. |
| `whisper_device` | `cpu` ou `cuda` (carte NVIDIA, voir `requirements-gpu.txt`). |
| `model`, `effort`, `eco_auto` | Modèle Claude, niveau d'effort, bascule économique. |
| `remote_enabled`, `remote_mode` | Appli mobile (voir ci-dessus). |
| `update_repo` | `proprietaire/depot` GitHub des versions publiées. |

## Depuis les sources

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Fabriquer l'installateur : `powershell -ExecutionPolicy Bypass -File build.ps1` (Python 3.12, [Inno Setup 6](https://jrsoftware.org/isinfo.php)). Publier une version : `release.ps1 -Version 1.2.0` (tag + GitHub Actions, voir `.github/workflows/release.yml`).

## Sécurité

Claude Code agit réellement sur ton ordinateur et tes serveurs. Fais des sauvegardes avant les grosses sessions, évite les mots de passe dans les consignes, et garde l'appli mobile désactivée si tu n'en as pas l'usage : un téléphone relié peut donner des ordres à Jimmy.

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md). Licence : [MIT](LICENSE).

---

### English summary

Jimmy wraps Claude Code with a voice interface (Windows, PySide6). Install `Jimmy-Setup-X.Y.Z.exe` from Releases: a first-run wizard installs Claude Code, signs you in and picks your folder and speech model. Speak or type; extra instructions you give while a task is running are injected into that task. A built-in mobile web app (QR pairing, voice in/out, Wi-Fi / Cloudflare tunnel / custom URL) lets you drive Jimmy from your phone while the PC stays on. Auto-update from GitHub Releases. MIT licensed.
