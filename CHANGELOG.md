# Historique des versions

## 2.2.0
- **Une discussion ne disparaît plus jamais par accident** : quand une discussion est trop grosse, Jimmy ne supprime plus l'ancienne tout de suite. Elle reste dans la liste (grisée) jusqu'à ce que la nouvelle existe vraiment et que Claude y ait répondu. Seulement ensuite, la nouvelle prend exactement le même nom et l'ancienne est supprimée (copie gardée 7 jours dans la corbeille). Si l'envoi échoue (limite d'usage atteinte, erreur, fermeture de Jimmy), rien n'est perdu et le résumé de reprise repart avec le prochain message.
- **Aurélie relit le fil de la discussion avant de répondre** : elle reprend les derniers messages réels, les tiens et ceux de Jimmy, ainsi que la reprise de contexte d'une discussion qui vient de naître. Elle ne se perd plus quand tu réponds « oui vas-y » ou « fais-le », et son fil ne s'efface plus au redémarrage ni quand tu changes de discussion. Elle garde 10 échanges au lieu de 8 et retient davantage des réponses de Jimmy.
- **Appli mobile : un seul appareil, un lien qui ne change plus** : chaque nouveau téléphone ou navigateur doit être autorisé sur le PC avant d'accéder à Jimmy, puis il reste relié, même après un redémarrage. Nouveau mode « Lien permanent » : une adresse fixe sur ton domaine (tunnel Cloudflare à nom fixe, création guidée avec une seule connexion Cloudflare de ta part), utilisable en lien comme en QR code, et ajoutable à l'écran d'accueil du téléphone comme une appli.
- **Reconnaissance vocale du téléphone aussi précise que sur le PC** : la voix enregistrée sur le téléphone est envoyée à Whisper sur le PC (même modèle précis que ton micro), au lieu de la dictée du navigateur.
- Nouveaux tests : `test_mobile.py` (jumelage, autorisation, voix, lien permanent).

## 2.1.2
- **Textes et boutons bien plus lisibles** : les gris secondaires (boutons du bas à gauche, recherche d'une discussion, titres de section, dossier de travail, heures, discussions pleines) étaient trop sombres, à 3,3:1 de contraste alors que le minimum lisible est 4,5:1. Ils sont maintenant à 6,7:1 ou plus, les boutons du bas sont presque blancs, et les petits textes passent de 11 à 12 px. Un test vérifie le contraste pour que ça ne se reproduise pas.
- **Aurélie** : une demande de modification d'interface (boutons, couleurs, apparence...) va directement à Jimmy au lieu de partir en recherche web ; « recherche dans une discussion » ne lance plus de recherche Internet ; son message à Jimmy ne parle plus d'elle à la troisième personne et ne s'excuse plus.

## 2.1.1
- **Aurélie répond de mémoire à « qu'est-ce que tu sais faire ? »** : aucune recherche, aucun token. Si la question concerne aussi Jimmy, elle lui passe la main pour qu'il présente ses propres capacités. Avant, elle partait chercher « Jimmy » sur Internet 7 fois de suite puis refusait.
- **Plus de recherches en boucle** : une recherche identique n'est jamais relancée, et pas plus de 3 recherches web par demande.
- **Son message à Jimmy n'est plus jamais un refus** (« je ne peux pas aider avec ça ») : si son modèle refuse, une vraie phrase de secours est utilisée.
- Dans les étapes, la ligne « J'ai obtenu : ... » montre le premier résultat au lieu de l'en-tête technique.

## 2.1.0
- **L'IA locale et Jimmy se parlent vraiment** : l'IA locale a un prénom, **Aurélie** (modifiable : réglage `local_name`). Quand elle passe la main, elle écrit elle-même, avec son modèle, un vrai message à Jimmy (ce que tu veux, ce qu'elle a déjà fait, pourquoi elle passe la main) ; il s'affiche dans la discussion, puis Jimmy répond. Si son moteur est éteint, une phrase de secours prend le relais : le dialogue ne casse jamais.
- **Jimmy peut demander du travail à Aurélie** : pour chercher un fichier, lire, lister un dossier ou chercher sur Internet, Claude appelle d'abord l'IA locale (commande gratuite, aucun token de ton abonnement). La question et la réponse s'affichent dans les deux sens. Elle n'a que des outils de lecture dans ce cas : le code lui interdit d'écrire ou de lancer des commandes.
- **Étapes en vraies phrases** : « Je regarde la config utilisateur », « Je lis shop.php »... à la place des lignes techniques « Commande · ... ».
- **« Hey Aurélie »** : elle répond quand tu dis son nom, avec **sa propre voix** (réglage `local_voice`, Éloïse par défaut) ; « Hey Jimmy » reste pour Claude.
- **Cyberpsychose : les glitchs d'origine sont de retour** (morceaux d'écran décalés, double image cyan/magenta, déchirures, parasites, balayage au changement de discussion, orbe rouge qui scintille), seulement avec le thème Cyberpsychose ou quand le quota est presque épuisé.
- **Menu des thèmes** : un seul bouton déroulant (style cyberpunk ou sobre, mode sombre ou clair, toutes les couleurs dont Cyberpsychose). Boutons principaux sans dégradé.
- **Discussions** : les boutons renommer / supprimer ne recouvrent plus le nom, et le survol affiche la demande complète dans une infobulle.
- **Carte « Limite atteinte »** : un vrai rectangle, qui reste à sa place dans la discussion même après un redémarrage.
- **Messages d'état** (micro actif, reconnaissance vocale prête, chargement...) : petite boîte à droite, seulement au moment où ça se passe, plus dans la discussion.
- **Plus d'autorisations ni de bip** : les anciens réglages « accepte les modifications » passent une fois pour toutes en « aucune demande » (les garde-fous `--force`, `DROP`... restent).
- **Dictée** : une phrase reconnue se termine toujours par un point. Le bouton Parler s'allume aussi pendant que Jimmy travaille. **Ctrl+V** d'une capture d'écran (ou de fichiers copiés) la joint au message.
- **Recherche de fichiers pour l'IA locale** (par nom et dans le contenu), et consignes d'économie pour Claude : chercher d'abord, lire seulement l'extrait utile, modifier sans tout réécrire.
- Nouveaux tests : `test_dialogue.py`, `test_aurelie.py`, `test_paste.py`.

## 2.0.4
- **L'IA locale peut vraiment chercher sur Internet** : sa recherche ne renvoyait rien (DuckDuckGo bloque les programmes, Bing leur sert des résultats faux). Elle passe maintenant par le navigateur intégré de Jimmy, **invisible** (aucun onglet ne s'ouvre dans ton navigateur, rien n'est gardé), avec de vrais résultats Bing / DuckDuckGo, leurs extraits de texte et le début de la page. L'API de Wikipédia et DuckDuckGo en direct servent de secours. Testé pour de vrai : « hauteur de la tour Eiffel » donne 330 m, avec la source.
- **Relais sans refaire le travail** : l'IA locale tient un journal de ce qu'elle a déjà fait (recherches, fichiers lus...) et le transmet à Claude avec la consigne de reprendre là où elle s'est arrêtée, sans refaire les mêmes recherches. Dans la discussion, la ligne verte de passage dit combien d'étapes sont transmises, et la réponse de Claude est étiquetée « CLAUDE · RELAIS » en violet : on voit qui parle.
- **Bouton « Vérifier les mises à jour »** dans la barre latérale : il cherche une nouvelle version et, s'il y en a une, télécharge (avec le pourcentage) et lance l'installation tout de suite ; Jimmy se ferme puis se rouvre tout seul.
- **Retour du style cyberpunk** (celui de l'ancien Jimmy) : hexagone « J » à effet glitch cyan / blanc / magenta, titre néon, lignes de balayage, anneau hexagonal autour de l'orbe, boutons taillés et lueurs néon. Il est actif par défaut ; le bouton hexagone du haut de la barre latérale revient au style sobre, et inversement.
- **Glisser-déposer fiabilisé** : le fichier déposé est maintenant attrapé au niveau de la fenêtre, avec son vrai chemin, quelle que soit sa taille ; un voile « Dépose les fichiers ici » s'affiche pendant le survol.
- Nouveaux tests : `test_websearch.py` (recherche réelle, demande Internet), `test_update_button.py`, `test_drop.py`.

## 2.0.3
- **Pièces jointes** : bouton trombone et glisser-déposer dans la zone de texte. Les fichiers (ou dossiers) sont copiés, quelle que soit leur taille, dans le dossier des pièces jointes de Jimmy (bouton « Pièces jointes » de la barre latérale pour l'ouvrir). Ils s'affichent en puces sous le message, et leur chemin reste écrit dans la discussion ; une note en mémoire permet aussi de les retrouver plus tard (« où est le fichier que je t'ai envoyé ? »). Les originaux ne sont jamais touchés ; deux fichiers de même nom ne s'écrasent pas.
- **Haiku pour les tâches simples** : Claude délègue maintenant la recherche de fichiers, l'exploration du code, la lecture et les tâches simples à un sous-agent Haiku, et garde son modèle pour raisonner et modifier. Ça économise le quota. Réglage `haiku_helper` (activé par défaut), et la règle est aussi notée en mémoire.
- **On voit ce que fait l'IA locale** : un compteur dans la barre latérale (réponses données seule, relais vers Claude, demandes envoyées directement à Claude). Les demandes clairement lourdes (code, serveur, base de données, longs textes) vont directement à Claude, sans perdre de temps à essayer en local.
- **Les deux IA se parlent** : ce que l'IA locale a répondu est transmis à Claude au prochain message, et ce que Claude répond est transmis à l'IA locale, pour qu'elles gardent le même fil.
- Nouveau test `test_attach.py` ; `test_local_flow.py` vérifie aussi les compteurs.

## 2.0.2
- **Menus cliquables** : le menu « Voix et écoute » était recouvert par la zone de discussion (aucun clic ne passait sur la voix, ni sur les interrupteurs). Corrigé et vérifié contrôle par contrôle. Les fenêtres de Réglages, de renommage et de choix du dossier s'ouvrent maintenant hors de l'appel venu de la page, ce qui évite qu'elles bloquent les clics.
- **Activer l'IA locale d'un clic** : un bouton « Activer l'IA locale » dans la barre du haut (et un interrupteur dans le menu) active le mode Auto sans passer par les Réglages, et dit tout de suite si un moteur local répond.
- **Mode Auto vraiment automatique** : si le moteur local est éteint, si l'IA locale plante, ou si elle répond « je ne peux pas », Jimmy ne te montre plus ce refus : Claude reprend la demande d'origine tout seul. Le passage est écrit dans la discussion (ligne verte « ↪ L'IA locale passe la main à Claude (raison) »).
- **L'IA locale peut agir** : elle sait maintenant créer et modifier des fichiers du dossier de travail (sauvegarde faite avant) et lancer des commandes PowerShell, seulement quand ton message le demande. Le code refuse le dangereux : fichiers de secrets, `--force`, `--no-verify`, `DROP`/`TRUNCATE`, suppressions récursives, réglages système, SSH (le serveur passe par Claude).
- Nouveaux tests : `test_brain.py` (outils, garde-fous, relais) et `test_local_flow.py` (passage Auto / manuel / `@local`).

## 2.0.1
- **Mise à jour réparée** : elle s'annulait toute seule (« annulation des modifications ») parce que Bionic, ton IA locale, charge quelques fichiers du dossier de Jimmy et que Windows ne peut pas le fermer. L'installateur ne cherche plus que les `.exe` à fermer, met de côté les fichiers verrouillés au lieu d'abandonner, et ferme les `Jimmy.exe` sans fenêtre restés ouverts. Testé avec un faux Jimmy et des fichiers verrouillés.
- **Notes de version complètes** : la fenêtre « Mise à jour » n'est plus coupée, elle affiche tout le texte avec une barre de défilement.

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





