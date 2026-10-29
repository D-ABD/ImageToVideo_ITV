# Petit Studio Vidéo — Django local

Application web locale en français pour transformer des images JPG/PNG ou des pages PDF en vidéo MP4 narrée. Les scènes, textes, réglages, échantillons vocaux et exports restent dans le dossier `media/` et dans SQLite (`db.sqlite3`). Aucun compte ni API cloud n’est requis pour l’utiliser ; une connexion Internet est nécessaire à l’installation et au premier téléchargement des poids IA, qui sont ensuite mis en cache localement.

## Fonctions

- Import d’images et de PDF ; chaque page du PDF devient une scène.
- Réorganisation par glisser-déposer, suppression, aperçu et texte modifiable par scène.
- Échantillon vocal WAV/MP3 ou enregistrement depuis le navigateur, écoute avant sauvegarde et confirmation d’autorisation.
- Clonage vocal local avec XTTS v2 en français.
- Sous-titres générés par alignement forcé WhisperX sur l’audio synthétisé ; affichage en phrases progressives.
- Image fixe, zoom avant ou zoom arrière doux par scène ; cadrages vertical 9:16 et horizontal 16:9.
- Assemblage MP4 et prévisualisation/téléchargement.
- Cache local des narrations : le même texte et le même échantillon vocal réutilisent le WAV déjà calculé.
- Projets persistés dans SQLite et réouvrables depuis la colonne de gauche.

## Prérequis

- Python 3.10 ou 3.11 recommandé pour la compatibilité de l’écosystème XTTS.
- FFmpeg avec les encodeurs `libx264` et `aac` disponible dans le PATH. Si le filtre `subtitles`/libass existe, il est utilisé ; sinon, les sous-titres sont dessinés localement avec Pillow et incrustés avec le filtre `overlay`.
- Pour une génération raisonnablement rapide : GPU NVIDIA/CUDA. L’inférence CPU fonctionne en principe mais peut être lente et nécessite davantage de mémoire.
- Environ 10 Go libres pour les modèles de synthèse et d’alignement lors du premier lancement ; le poids réel varie selon les modèles téléchargés.

Vérifie FFmpeg avec :

```bash
ffmpeg -version
ffmpeg -filters | grep subtitles
```

Sur macOS, installe FFmpeg avec Homebrew :

```bash
brew install ffmpeg
ffmpeg -filters | grep -E 'subtitles|overlay'
```

Sur Debian/Ubuntu : `sudo apt install ffmpeg libavcodec-extra`. L’installation de libass/`ffmpeg-full` est facultative : le pipeline inclut un rendu de secours des sous-titres quand libass n’est pas disponible.

## Installation

```bash
cd coach_shiba_video
python3.11 -m venv .venv
source .venv/bin/activate              # Windows PowerShell : .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip uninstall -y TTS coqui-tts
python -m pip install -r requirements-ai.txt
python -c "import torch; from TTS.api import TTS; print('XTTS prêt')"
python manage.py migrate
python manage.py runserver
```

Ouvre ensuite `http://127.0.0.1:8000/`. Au premier rendu, XTTS v2 et les poids WhisperX sont téléchargés puis conservés dans le cache local de PyTorch. Le chargement initial peut prendre plusieurs minutes.

Toutes les commandes d’installation et de lancement doivent être exécutées dans le même environnement virtuel. Les versions de `requirements-ai.txt` évitent la compilation de `llvmlite`, restent compatibles avec PyTorch 2.2.2 sur Mac Intel et préservent la méthode `generate` requise par XTTS. La commande de vérification doit afficher `XTTS prêt` avant de lancer le serveur. Sur Linux avec CUDA, installe d’abord la roue PyTorch correspondant à ton OS/CUDA depuis le sélecteur officiel PyTorch ; conserve une version compatible avec XTTS, puis installe les autres dépendances IA.

## Utilisation

1. Crée un projet et importe une ou plusieurs images, ou un PDF.
2. Réordonne les scènes par glisser-déposer ; sélectionne une scène pour écrire son texte et choisir son zoom.
3. Ajoute une voix avec un fichier ou l’enregistre au microphone. Écoute-la, nomme-la et confirme l’autorisation d’utilisation.
4. Lance « Préparer la narration » pour synthétiser les voix et synchroniser les sous-titres, puis écoute l’audio de chaque scène.
5. Choisis les sous-titres et le ratio, puis lance la génération vidéo. Les audios et sous-titres préparés sont réutilisés tant que le texte et la voix ne changent pas.
6. L’interface indique la progression et affiche les erreurs de dépendances ou de rendu. La vidéo se prévisualise et se télécharge dans le navigateur.

## Licence du modèle vocal

XTTS v2 est publié sous la Coqui Public Model License. Vérifie ses conditions avant tout usage commercial. L’application stocke la déclaration d’autorisation, mais ne peut pas vérifier les droits sur un échantillon vocal : n’enregistre que ta voix ou une voix pour laquelle tu as obtenu une autorisation explicite.

## Données et limites de la première version

- `db.sqlite3` contient projets, scènes, réglages et noms de voix ; les médias sont dans `media/`.
- L’application n’active pas l’authentification et le serveur de développement n’est prévu que pour l’accès local (`127.0.0.1`). Ne l’expose pas directement sur Internet.
- Le traitement démarre dans un thread du serveur Django. Pour de grosses vidéos, ferme les autres applications lourdes ; un worker de fond est une amélioration future.
- Le montage garde les images fixes ou applique uniquement un zoom doux. Aucun visage, bouche ou personnage n’est animé.
- L’alignement échoue explicitement si WhisperX n’arrive pas à trouver les mots dans l’audio ; l’application n’invente pas des horodatages de sous-titres.
