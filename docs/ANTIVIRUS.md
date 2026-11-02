# L'antivirus bloque Jimmy (« Trojan », « Bearfoos »…)

**Jimmy n'est pas un virus.** C'est un *faux positif* : les antivirus se méfient de tout programme **Python empaqueté, non signé et nouveau**, parce que les vrais virus utilisent la même technique d'empaquetage. Windows Defender le signale par exemple sous un nom du type `Trojan:Win32/Bearfoos.A!ml` : le `!ml` veut dire « détection automatique par apprentissage », pas une signature connue de virus.

Le code est ouvert : tu peux le lire, et même reconstruire toi-même l'installateur (`build.ps1`).

## Ce qui est fait pour limiter le problème

- Le programme est reconstruit avec **son propre chargeur** (le « bootloader » standard de PyInstaller est celui que les antivirus connaissent le mieux, donc le plus souvent suspecté).
- Le `.exe` porte une identité (nom, version, licence) dans ses propriétés.
- Pas de compression exécutable (UPX), pas de code caché.

## Si ton antivirus l'a quand même bloqué

1. **Vérifie le fichier** : compare son empreinte avec celle de la page de la release (`certutil -hashfile Jimmy-Setup-X.Y.Z.exe SHA256`) ou envoie-le sur [virustotal.com](https://www.virustotal.com).
2. **Restaure-le** puis **autorise-le** : Sécurité Windows › Protection contre les virus et menaces › Historique de protection › sélectionne l'élément › *Actions › Autoriser sur l'appareil*.
3. **Signale le faux positif** (c'est ce qui le fait disparaître pour tout le monde, parfois en quelques jours) : <https://www.microsoft.com/wdsi/filesubmission> (choisis « Je suis un développeur », « Faux positif »). Les autres éditeurs ont des formulaires équivalents.

## Pour l'auteur : rendre l'installateur de confiance

Le vrai remède, c'est la **signature de code** : un installateur signé est reconnu, et sa réputation grandit à chaque téléchargement.

| Solution | Coût | Remarques |
|---|---|---|
| [SignPath Foundation](https://signpath.org/) | **Gratuit pour l'open source** | Dépôt public requis ; s'intègre à GitHub Actions. La meilleure piste. |
| Azure Artifact Signing (ex Trusted Signing) | ~10 $/mois | Signature gérée par Microsoft, réputation immédiate. |
| Certificat de signature (OV/EV) | ~100 à 400 €/an | Classique ; l'EV supprime l'avertissement SmartScreen d'emblée. |
| Microsoft Store (MSIX) | ~19 $ une fois | Microsoft signe le paquet ; plus d'avertissement. |

En attendant : publier les **empreintes SHA-256** des installateurs, soumettre chaque nouvelle version à Microsoft, et garder des versions peu fréquentes (chaque nouveau fichier repart avec zéro réputation).
