# Historique des versions

## 2.5.4
- **Le navigateur d'Aurélie ne se trompe plus de site.** Quand tu parles de ton site avec une faute dans le nom, elle ouvrait l'adresse mal écrite, qui existe vraiment et appartient à quelqu'un d'autre. Ouvrir une page, la capturer et juger un rendu corrigent maintenant le nom (d'après les réglages `site_url` et `site_alias`). Les autres adresses, fichiers locaux et `localhost` restent intacts.

## 2.5.3
- **Aurélie cherche vraiment, toute seule, sur un site.** Elle suit en priorité les liens qui parlent du sujet de ta demande (par exemple la page « reliques » quand tu parles de reliques) et lit jusqu'à 20 pages au lieu de s'arrêter à la première. Si l'adresse du site lui manque, elle la cherche (mémoire, recherche) au lieu de te la demander ou d'abandonner.
- **Plus de faux « j'ai transmis à Claude ».** Quand Aurélie annonçait passer la main sans appeler l'outil, rien n'arrivait chez Claude. Maintenant, si elle le promet, le relais est fait pour de vrai avec ta demande d'origine. Elle a aussi pour consigne de persévérer elle-même (explorer le site, chercher sur Internet, lire les pages) avant de passer la main.
- Nouveaux tests dans `test_site.py`.

## 2.5.2
- **L'IA locale peut parcourir n'importe quel site toute seule.** Nouvel outil « explorer_site » : Aurélie ouvre une page, suit les liens du même site (jusqu'à 12 pages), lit leur texte et cherche les mots utiles, sans rien demander à Jimmy ni à toi. Elle connaît ton site (adresse réglée dans la configuration, fautes de frappe du nom corrigées) et marche aussi pour une documentation, un wiki ou n'importe quelle adresse, avec ou sans « https:// ». Chaque page visitée s'affiche dans l'activité en direct (« Page lue 3/12 »).
- **Le panneau d'activité défile comme il faut.** Si tu es en bas, il suit : chaque nouveau message apparaît en entier, même quand une ligne grandit après coup. Si tu as remonté pour relire, il ne te force plus à redescendre.
- **Publication plus simple.** `release.ps1 -Version X -Notes notes.md` fait tout : version, commit, tag, envoi, attente de la construction, notes et suppression des anciennes versions.
- Nouveau test : `test_site.py`.

## 2.5.1
- **Le passage de relais marche pour de vrai.** Quand tu écris « d'abord Aurélie se présente, puis passe le relais à Jimmy pour qu'il se présente lui-même », Aurélie fait **seulement sa part**, puis Jimmy est lancé et fait la sienne : avant, Aurélie répondait pour les deux. Ça marche aussi avec « dis à Jimmy de modifier le bouton » (Aurélie passe tout à Jimmy tout de suite), « présentez-vous tous les deux, chacun son tour », ou « fais ça, ensuite tu passes la main à Jimmy pour qu'il fasse ça ». Le relais a lieu quel que soit le sélecteur (Claude / IA locale / Auto) et les deux réponses viennent de deux auteurs différents dans la discussion.
- **Une demande de modification adressée à Aurélie passe automatiquement à Jimmy** (« Hey Aurélie, modifie le bouton », « corrige l'interface », « déploie le site »...) : même si tu lui parles directement ou avec « @local », elle ne tente pas de le faire elle-même, elle prévient Jimmy en une phrase et il s'en occupe. Les questions qui lui reviennent restent chez elle (« que fait Jimmy ? », « qu'est-ce qu'il vient de modifier ? », captures, jugement d'un rendu).
- **Sa présentation est courte** (deux phrases), au lieu de la liste complète de ses capacités.
- Nouveau test : `test_relay.py`. Le faux Jimmy (`dev_fakejimmy.py`) vérifie aussi, de bout en bout avec le vrai Claude, le relais de présentation et la modification demandée à Aurélie.

## 2.5.0
- **Le panneau de droite est l'activité en direct de Jimmy ET d'Aurélie, en permanence.** Une seule vue, qui se remplit au fur et à mesure : ce que Jimmy lit, modifie (avec les lignes retirées en rouge et ajoutées en vert), les commandes qu'il lance et leur résultat (réussi, échec, en cours), ce qu'il dit, et tout ce que fait Aurélie. Il s'ouvre tout seul dès qu'il y a de l'activité, se redimensionne à la souris, et **sa largeur est retenue**. Plus d'écran en direct ni de galerie : **les captures sont de simples rendus envoyés dans la conversation, pendant le travail (au plus un toutes les 75 secondes) et à la fin.**
- **Une vraie discussion avec Aurélie, pas juste un outil.** Ta question à Aurélie ET sa réponse sont gardées dans la discussion. Une discussion menée seulement avec elle a maintenant son propre identifiant : elle apparaît dans la liste (titrée par ta première question), se renomme, se supprime, se rouvre en entier, et quand Jimmy s'en mêle elle devient la même discussion que celle de Claude, sans rien perdre. Aurélie relit tout le fil avant de répondre : tes messages, ceux de Jimmy et ses propres réponses précédentes.
- **Tout ce qui s'affiche est sauvegardé par discussion et revient quand tu la rouvres** : captures, messages d'Aurélie, dialogues avec Jimmy, passages de main, et l'activité du panneau, remis dans l'ordre où ça s'est passé.
- **Aurélie travaille vraiment après chaque tâche de Jimmy, sans un token** : elle **relit les fichiers modifiés** (erreurs de syntaxe en Python, JSON, JavaScript, HTML, CSS ; mots de passe, jetons ou clés écrits en clair, sans jamais recopier leur valeur), recharge la page concernée, mesure le rendu et te l'envoie avec son verdict. Les problèmes trouvés sont aussi transmis à Jimmy pour son prochain message.
- **Aurélie sait ce que fait Jimmy** : « que fait Jimmy ? », « qu'a-t-il modifié ? » : elle répond d'après l'activité réelle (lectures, modifications, commandes, échecs), sans consommer de tokens.
- **Aurélie voit vraiment les rendus et les couleurs.** Elle mesure la page affichée (couleurs de fond et de texte avec leur nom, contrastes selon la norme, polices, textes trop petits ou coupés, éléments qui se chevauchent, images déformées ou floues) et, si un modèle de vision est installé dans LM Studio, elle regarde aussi l'image (**Qwen3-VL 4B**, choisi automatiquement ; nouveau bouton « Installer le modèle de vision » dans les Réglages). Comme la carte graphique est souvent presque pleine, elle décharge un moment le modèle de discussion (environ 20 secondes), regarde, puis remet exactement les modèles d'avant, même en cas de panne. Quand on lui demande de juger un rendu, **sa réponse est composée par le code à partir des mesures** : plus de « contraste 2,02:1, c'est acceptable ».
- **Jimmy lui délègue ce travail** : `capture ADRESSE` (rapport texte + mesures exactes + texte lu) et, avec `--look "question"`, elle regarde aussi la capture. Jimmy ne lit une image lui-même qu'en dernier recours.
- **Le micro reste ouvert pendant que Jimmy travaille** : avant, ta voix n'était pas enregistrée tant qu'une tâche tournait. Tu peux maintenant parler pour ajouter une précision, elle est ajoutée à la tâche en cours. Le micro ne se coupe que quand Jimmy parle lui-même.
- **L'apparence est enregistrée dans la configuration de Jimmy** (style, mode clair ou sombre, teinte, ambiance, arrondis, largeur du panneau) et non plus seulement dans la page, qui l'oubliait d'une session à l'autre. Ce que la page avait déjà gardé est repris une fois.
- **La barre du haut ne se superpose plus** quand le panneau de droite est ouvert : les cartes Jimmy / Aurélie passent sur une seconde ligne quand la place manque (vérifié à toutes les largeurs).
- **Titres de discussions propres** : plus de « [Contexte : l'IA locale… » ni de « @claude » devant ta vraie demande.
- Nouveaux tests : `test_checks.py`, `test_persist.py` (sauvegarde par discussion), et `dev_fakejimmy.py`, un faux Jimmy qui pilote la vraie fenêtre avec les vrais modèles pour vérifier de bout en bout.

## 2.4.0
- **Un panneau « Écran en direct » à droite de la fenêtre : le PC d'Aurélie.** Quand Aurélie (ou Jimmy, via elle) travaille sur un site, tu le vois en direct, comme sur un vrai PC : la page qui se charge, un anneau animé à l'endroit où elle clique, le titre et l'adresse. Trois onglets : **Écran** (tu peux aussi y ouvrir toi-même une adresse, un site, localhost ou un fichier .html, et capturer ce que tu vois), **Activité** (tout ce qu'elle fait, heure par heure, et les passages de la main) et **Captures** (la galerie). Le panneau s'ouvre tout seul la première fois qu'il y a quelque chose à voir, se redimensionne à la souris et se ferme d'un clic. **Aucun token n'est utilisé** : ces images ne vont jamais à Claude.
- **Aurélie a un vrai navigateur à elle** (invisible, rien n'est gardé : ni cookies, ni historique, ni identifiants) : elle ouvre un site ou une page locale, lit le texte vraiment affiché (JavaScript compris), défile, **contrôle la page** (images cassées, débordement en largeur, erreurs JavaScript, éléments trop petits, balise mobile absente) et, quand tu le demandes, clique et écrit dans un champ. Elle n'envoie jamais un formulaire : pas d'Entrée, pas de validation.
- **Des captures propres, envoyées dans la conversation** : écran visible, page entière, un seul élément (sélecteur), ou une largeur au choix (390 px pour un téléphone). Elles s'affichent dans la discussion avec leur légende, s'agrandissent d'un clic, et se rangent dans la galerie (gardées 14 jours, réglable). Depuis la galerie, tu peux remettre une capture dans la discussion ou la **joindre à ton prochain message** pour que Jimmy la voie.
- **Aurélie analyse les images** : elle lit le texte d'une image ou d'une capture (reconnaissance de texte de Windows, en français, sans rien installer), donne les couleurs dominantes et le ton, et décrit l'aspect si tu as installé un modèle de vision dans LM Studio (nouveau réglage « Modèle de vision »). Sans lui, elle te dit honnêtement ce qu'elle n'a pas pu juger, au lieu d'inventer.
- **Jimmy lui délègue ces travaux** : pour voir un site ou une image, Jimmy passe par `jimmy_local.py capture ADRESSE` ou `see IMAGE` : Aurélie ouvre, capture, contrôle, lit, affiche la capture à l'utilisateur et lui rend un **rapport en texte** (pas l'image, qui coûterait beaucoup de tokens). Jimmy ne lit une image lui-même qu'en dernier recours. Le passage de l'un à l'autre se voit dans les cartes du haut et dans le fil d'activité.
- **Aurélie comprend les demandes de vue** : « fais une capture de ce site en version mobile », « montre-moi le rendu », « vérifie s'il y a des images cassées », « ouvre la page puis clique sur Réserver » : le code lance et enchaîne les outils lui-même, elle n'a plus qu'à raconter. Ces demandes ne partent plus chez Claude à cause de mots comme « bouton » ou « couleur ». Elle sait maintenant qu'elle a un navigateur et ne répond plus « je ne peux pas ouvrir une page ».
- **Sécurité** : cliquer, écrire dans un champ et capturer tout l'écran du PC ne partent que si tu l'as demandé dans ton message (contrôlé par le code, pas par le modèle). Quand c'est Jimmy qui délègue, ces trois actions sont refusées. Les fichiers qui ressemblent à des secrets (.env, clés, mots de passe, config.php...) ne sont jamais ouverts ni analysés. Seules les adresses http(s) et les fichiers locaux sont acceptées.
- **Correction** : après une délégation de Jimmy interrompue (fichier refusé, adresse invalide), Aurélie restait affichée comme « au travail » : elle est maintenant toujours rendue à Jimmy.
- La barre du haut s'adapte quand le panneau réduit la place (les cartes Jimmy / Aurélie passent sur une seconde ligne). Nouveaux tests : `test_live.py` (navigateur, captures, rapport, lecture d'image, sécurité, délégation de Jimmy).

## 2.3.0
- **On voit enfin qui travaille : Jimmy et Aurélie côte à côte en haut de la fenêtre.** Chacun a sa carte avec son voyant : celui qui travaille s'allume (halo, anneau qui tourne, « travaille… » ou « parle… »), l'autre se grise (« attend » ou « en veille »). L'orbe prend aussi la couleur de celui qui travaille, et le titre dit « Aurélie travaille » ou « Jimmy travaille ».
- **Les passages de l'un à l'autre se voient** : quand Aurélie passe la main à Jimmy (ou que Jimmy lui demande de chercher, puis qu'elle lui rend sa réponse), une lumière traverse le lien entre les deux cartes, et une ligne colorée apparaît dans la discussion : « Aurélie → Jimmy · ça dépasse ses moyens ».
- **La couleur d'Aurélie se choisit** : menu des thèmes, 8 couleurs ou n'importe quelle autre. Elle est utilisée partout : carte, voyant, messages, lien, statistiques, bouton Auto.
- **Les thèmes changent beaucoup plus que les boutons** : la couleur choisie teinte maintenant toute l'interface (fonds, barre latérale, barre du haut, bulles, zone d'écriture, bordures, barres de défilement), avec un curseur « Teinte de l'interface » de 0 à 100 %. Quatre ambiances de fond (Uni, Halo, Grille, Aurore animée) et trois arrondis (Net, Doux, Rond). Tout se retient d'une fois sur l'autre.
- **Aurélie ne parle plus d'elle à la troisième personne** : sa consigne dit maintenant que « je » c'est elle, et qu'elle ne dit jamais « Aurélie a fait » ou « l'IA locale a fait ».

## 2.2.1
- **Aurélie ne se fait plus passer pour Jimmy** : l'étiquette « [Jimmy a répondu] » que j'avais mise dans son historique était recopiée dans ses propres réponses, ce qui donnait l'impression d'un faux. Le fil de la discussion est maintenant donné à Aurélie à part (« Utilisateur : ... / Jimmy : ... ») et non comme de faux tours de parole, elle relit toujours les derniers messages avant de répondre, et si une étiquette de ce genre apparaît quand même, elle est retirée avant l'affichage.
- **Plus d'appli inventée** : Aurélie avait répondu que l'appli mobile se télécharge sur le Google Play Store. Faux : l'appli mobile de Jimmy est une page web. Bouton « Appli mobile » dans Jimmy, scanner le QR code ou ouvrir le lien sur le téléphone, autoriser l'appareil sur le PC, puis « Ajouter à l'écran d'accueil » dans le navigateur. Elle connaît maintenant cette procédure et n'en invente plus d'autre.

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





