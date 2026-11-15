# Historique des versions

## 2.0.0
- **Nouvelle interface** : toute la fenêtre est refaite comme une vraie page web moderne (HTML / CSS / JavaScript, affichée dans l'appli). Discussions avec recherche, aperçu de la voix en direct, blocs de code avec bouton « Copier », étapes de travail dépliables, thème sombre ou clair, jauges de quota et de contexte, menu Voix. Les réglages avancés restent dans la fenêtre Réglages. L'ancienne interface reste disponible (Réglages › Fenêtre › Interface) et prend le relais automatiquement si la nouvelle ne peut pas démarrer.
- **Reconnaissance vocale bien plus précise** : nouveau modèle **large-v3-turbo** (choisi automatiquement sur un PC avec carte NVIDIA, d'après la mémoire graphique), son nettoyé avant la reconnaissance (les voix basses ou les micros de casque sans fil sont remontés), début de phrase mieux conservé (plus de premières syllabes perdues), filtre de parole qui évite les phrases inventées dans le silence, et un **vocabulaire personnel** (Réglages › Écoute) pour les noms et mots techniques mal compris.
- **Le bouton « J'écoute » ne ment plus** : il n'est vert que si du son arrive vraiment du micro. Si le micro ne transmet plus rien (casque sans fil endormi, pilote bloqué), Jimmy le rouvre tout seul, et le dit clairement s'il n'y arrive pas.
- **Accélération carte graphique** pour la version installée : Réglages › Audio propose de télécharger les bibliothèques NVIDIA (≈ 1,3 Go, paquets officiels, vérifiés par empreinte) avec ton accord. Sans elles, ou en cas de problème, Jimmy bascule sans bruit sur le processeur.
- **IA locale (facultative)** : une IA qui tourne sur ton PC (LM Studio, Bionic ou Ollama), gratuite et privée. Sélecteur **Claude / IA locale / Auto** à côté de la zone de texte (`@local` ou `@claude` devant un message forcent le choix). Elle va sur Internet, lit tes fichiers, utilise la mémoire de Jimmy, et passe la main à Claude avec un résumé quand ça dépasse ses moyens. L'assistant d'installation et Réglages › IA locale analysent ton PC, expliquent ce qui est requis et ne téléchargent rien sans toi.
- **Packs de connaissances** : un dossier dans `%APPDATA%\Jimmy\packs` apprend à l'IA locale un projet précis (guides, index de fichiers, outils). Chacun fabrique les siens ; ils ne sont jamais publiés.
- **Garde anti-fuites** avant chaque publication : aucune donnée privée (mémoire, packs, adresses, secrets) ne peut partir sur GitHub.
- L'installateur est plus gros (≈ 100 Mo de plus) : il embarque le moteur d'affichage de la page web.

## 1.1.2
- **Raccourcis clavier retirés** : plus de Échap pour arrêter la tâche, ni de Ctrl+Espace, Ctrl+N ou Ctrl+M. Une touche pressée par mégarde n'annule donc plus rien : on arrête une tâche uniquement avec le bouton **Stop**. Restent seulement F2 (renommer) et Suppr (supprimer, avec confirmation) quand la liste des discussions est sélectionnée.

## 1.1.1
- **Mise à jour réparée** : elle s'annulait (« annulation des modifications ») quand un `Jimmy.exe` sans fenêtre restait ouvert, par exemple le serveur d'autorisation ou la mémoire lancés par une tâche de Claude : il gardait les fichiers verrouillés. L'installateur ferme maintenant ces restes juste avant de copier les fichiers.
- L'installation écrit un journal (`Jimmy-Setup-log.txt` dans le dossier temporaire) pour comprendre un éventuel échec.

## 1.1.0
- **Mode autonomie** (Réglages › Claude › Permissions) : une seule case, comme « bypass permissions » dans Claude Code. Jimmy agit sans jamais demander, et dit après ce qu'il a fait. Des garde-fous techniques restent actifs même dans ce mode : `git push --force`, `--no-verify`, `DROP` et `TRUNCATE` sont refusés (case désactivable). En mode autonomie, le serveur d'autorisation n'est plus chargé à chaque message : un peu moins de tokens.
- **Demandes d'autorisation** (hors autonomie) : plus jamais d'attente sans fin. La fenêtre clignote dans la barre des tâches, fait un bip, affiche le délai et refuse toute seule sans réponse (120 s par défaut, réglable) en le disant clairement, à toi et à Claude (qui ne réessaie plus en boucle).
- **Règle du premier plan** dans les consignes de Jimmy : chaque message est une session courte, donc tests, déploiements et commandes longues se lancent au premier plan et Jimmy attend le résultat, sans promesse de verdict « plus tard ».
- **Mémoire de Jimmy** (`memoire.db` dans `%APPDATA%\Jimmy`, SQLite avec recherche plein texte) et commande `jimmy_mem.py` (`add`, `search`, `get`, `list`, `forget`, aussi disponible avec `Jimmy.exe --mem`). Réponses très courtes pour consommer peu de tokens ; les mots de passe, clés et jetons sont refusés. Les consignes de Jimmy ne contiennent qu'une phrase d'explication, jamais le contenu de la base.
- **Reprise de contexte refaite** : quand une discussion est presque pleine, l'essentiel (but, fichiers touchés, état, suite) est enregistré en mémoire, la nouvelle discussion ne reçoit qu'un mini-message, puis l'ancienne est supprimée pour de bon (copie de sécurité dans une corbeille purgée après 7 jours, option pour tout garder). La nouvelle discussion garde **exactement** le nom de l'ancienne, sans « Reprise… » ni suffixe, et prend sa place dans la liste.
- **Renommer une discussion** : double-clic, F2 ou clic droit › Renommer (Entrée valide, Échap annule). Le nom est enregistré durablement et Jimmy ne l'écrase jamais. Sans nom, la discussion prend un titre court tiré de ta première demande.
- **Ménage automatique** (une seule fois) des anciennes « Reprise de la discussion précédente » : une entrée par vraie discussion, avec son nom d'origine retrouvé quand c'est possible.
- Nouveau `test_handoff.py` (reprise, noms, corbeille, sécurité) et nouveaux contrôles dans le diagnostic (`selftest.py`).

## 1.0.9
- Fermer ou redémarrer Jimmy n'arrête plus la tâche de Claude en cours : elle continue en arrière-plan, et au prochain démarrage Jimmy affiche sa réponse (valable aussi pendant une mise à jour). Seuls les accords d'outils demandés après la fermeture sont refusés.
- Zone de saisie : plus de barre de défilement fantôme pour une seule ligne (la hauteur tenait compte de la mauvaise police) ; la barre n'apparaît qu'au-delà de 10 lignes.
- Reconnaissance vocale : quand tu reprends ta phrase après une pause, tout ce que tu as dit est retranscrit d'un bloc avec le modèle précis (au lieu de recoller des morceaux), donc le texte se corrige avec le contexte.

## 1.0.8
- Après une mise à jour, Jimmy se rouvre tout seul (avant il restait fermé).
- Le bouton redémarrer (et le redémarrage après un changement de réglage vocal) rouvre vraiment Jimmy : le nouveau attend que l'ancien soit fermé au lieu de s'arrêter.

## 1.0.7
- Titres du markdown bien plus gros, en couleur d'accent, avec de l'air autour : les réponses longues sont plus lisibles.
- Mode normal : Jimmy répond du tac au tac (une à trois phrases, sans introduction ni politesse ni récapitulatif).
- Mode long : réponses développées et organisées dans un ordre logique, avec titres, listes et gras.

## 1.0.6
- Réponses mieux mises en forme : listes, titres et retours à la ligne s'affichent proprement, les points ou symboles isolés disparaissent.
- Jimmy reçoit des consignes de mise en forme markdown plus précises.
- Discussions rouvertes : les balises techniques (rappels système, notifications) n'apparaissent plus dans les anciens messages, et la reprise de contexte est résumée en une ligne.

## 1.0.5
- Le numéro de version s'affiche maintenant sur sa propre ligne, sous le titre (il était coupé).
- Les anciennes versions (1.0.0 à 1.0.2) ont été retirées de GitHub : seule la dernière est téléchargeable.

## 1.0.4
- Mise à jour automatique plus fiable : la fenêtre de proposition s'ouvre toujours au bon endroit.
- Installation d'une mise à jour sans aucune question (dossier et options conservés), puis Jimmy se relance.
- Le numéro de version est affiché dans la fenêtre.

## 1.0.2
- Modèle vocal : l'erreur « point de montage non approuvé » (WinError 448) est réparée toute seule.
  Un cache cassé est nettoyé, et au besoin le modèle est téléchargé dans le dossier de Jimmy.

## 1.0.1
- Si le téléchargement du modèle vocal échoue, Jimmy réessaie seul (5 essais) ; un clic sur « Parler » relance.
- Changer le modèle vocal dans les réglages redémarre Jimmy automatiquement.

## 1.0.0
- Première version publique : voix, connexion à Claude, appli mobile, changement de discussion téléphone ↔ PC.





