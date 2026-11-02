# Guide de Jimmy : comment ça marche

## En une minute

Jimmy est une **fenêtre** (et une voix) posée par-dessus **Claude Code**, le programme d'Anthropic qui sait lire, modifier et lancer des choses sur ton ordinateur. Quand tu parles à Jimmy :

1. ta voix est transformée en texte **sur ton PC** (modèle Whisper, rien n'est envoyé à un service de reconnaissance vocale) ;
2. le texte part à **Claude Code**, qui travaille avec **ton propre compte Claude** ;
3. la réponse s'affiche, et Jimmy la lit à voix haute.

Jimmy n'a pas de serveur : aucun compte à créer chez nous, aucune clé API, aucune donnée envoyée ailleurs qu'à Claude.

## Est-ce que Claude se connecte tout seul ?

**Oui, au premier lancement, par un assistant en 4 étapes**, mais **tu dois valider ta connexion toi-même** (c'est normal : c'est ton compte) :

| Étape | Ce que fait l'assistant | Ce que tu fais |
|---|---|---|
| 1. Claude Code | Il cherche la commande `claude`. Si elle manque, il lance l'**installateur officiel** de Claude Code (`claude.ai/install`). | Rien (un clic sur « Installer »). |
| 2. Connexion | Il ouvre la page de connexion **officielle d'Anthropic** dans ton navigateur (`claude auth login`) et attend. | Tu te connectes avec ton compte Claude (abonnement Pro ou Max). Jimmy ne voit jamais ton mot de passe. |
| 3. Dossier | Il te demande sur quel dossier Claude travaille par défaut. | Tu en choisis un (modifiable plus tard). |
| 4. Voix | Il te laisse choisir la précision de la reconnaissance vocale. | Tu choisis (« small » est un bon départ). |

Si tu fermes l'assistant (« Plus tard »), il se relance au démarrage suivant. Pour vérifier à la main : ouvre un terminal et tape `claude auth status` (il doit afficher `"loggedIn": true`).

## La reconnaissance vocale

- **Au tout premier lancement**, le modèle vocal se télécharge (de 150 Mo à 1,5 Go selon ton choix). La fenêtre affiche « Téléchargement du modèle vocal : X % ». Tant que ce n'est pas fini, Jimmy ne t'entend pas, mais tu peux déjà **écrire** dans la zone de texte et Claude répond normalement.
- Ensuite, dis **« Jimmy »** puis ta demande, ou clique sur **Parler**.
- Si Jimmy ne t'entend pas : ouvre **Réglages (⚙)** et choisis ton **micro** dans la liste (le micro par défaut de Windows n'est pas toujours le bon).
- Pour un diagnostic complet, lance dans un terminal : `"%LOCALAPPDATA%\Programs\Jimmy\Jimmy.exe" --selftest`. Il écrit `selftest.txt` dans `%APPDATA%\Jimmy` : micros trouvés, modèle chargé, et une phrase de test qu'il doit comprendre. Envoie ce fichier si tu ouvres un ticket.

## L'appli mobile

Pour piloter Jimmy depuis ton téléphone :

1. Dans Jimmy, clique sur **Appli mobile** (colonne de gauche).
2. Coche **Activer l'appli mobile**, choisis un mode :
   - **Wi-Fi** : téléphone et PC sur le même réseau (écriture seulement) ;
   - **Internet (Cloudflare)** : fonctionne partout et permet de **parler** ; l'adresse change à chaque démarrage de Jimmy ;
   - **Mon adresse** : Tailscale, ZeroTier ou ton domaine (adresse fixe).
3. Scanne le **QR code** avec l'appareil photo du téléphone, puis « Ajouter à l'écran d'accueil ».

Tu peux aussi **changer de discussion** depuis le téléphone (bouton ☰) : elle s'ouvre en même temps sur le PC. Ça ne marche que **si le PC reste allumé avec Jimmy ouvert**. Détails : [MOBILE.md](MOBILE.md).

## Ce que Jimmy peut faire pendant qu'il travaille

- Tu peux **continuer à parler ou écrire** : ta précision est ajoutée à la tâche en cours.
- **Stop** (ou Échap) arrête la tâche.
- La **conversation** se poursuit d'une demande à l'autre ; « Nouvelle discussion » repart de zéro.

## Mises à jour

Jimmy cherche les nouvelles versions publiées sur GitHub (réglage `update_repo`) et te propose de les installer en un clic. Tes réglages et tes appareils jumelés sont dans `%APPDATA%\Jimmy` : ils sont conservés.

## Windows ou l'antivirus bloque l'installation

Voir [ANTIVIRUS.md](ANTIVIRUS.md).

## Désinstaller

Paramètres Windows › Applications › Jimmy › Désinstaller. Pour tout effacer, supprime aussi `%APPDATA%\Jimmy`. Claude Code reste installé (il est indépendant de Jimmy).
