# Contribuer à Jimmy

Merci ! Quelques repères :

- **Structure** : `window.py` (fenêtre), `claude_bridge.py` (pont vers la commande `claude`), `listener.py` / `speaker.py` (voix), `remote*.py` + `mobile/` (appli mobile), `setup_wizard.py` / `updater.py` (installation et mises à jour).
- **Lancer depuis les sources** : voir le README. Les données (réglages, appareils jumelés) sont dans le dossier du code en développement, dans `%APPDATA%\Jimmy` une fois installé.
- **Pas de secret dans le dépôt** : `config.json`, `devices.json` et les journaux sont ignorés par Git. N'ajoute jamais de clé, de jeton ni de chemin personnel.
- **Scripts personnels** (Discord, YouTube, serveur…) : restent hors du dépôt (voir `.gitignore`) ; Jimmy les utilise seulement s'ils sont présents à côté du programme.
- **Avant une pull request** : le programme doit démarrer (`python main.py`), et `python -m compileall .` passer.
- **Publier une version** : `release.ps1 -Version X.Y.Z` (tag `vX.Y.Z`), la CI construit l'installateur.
