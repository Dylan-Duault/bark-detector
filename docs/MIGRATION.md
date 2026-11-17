# Migrer une installation existante

## Ce qui change

- Le serveur HTTP standard est remplacé par FastAPI / Uvicorn.
- Les données structurées sont regroupées dans `data/bark.sqlite3`.
- Les fichiers WAV et les morceaux MP3 gardent leurs noms et leurs emplacements.
- `.env` reste valide ; les réglages de détection peuvent maintenant y être définis.
- Les URL `/`, `/login`, `/logs`, `/api/dashboard`, `/audio/...` et `/api/waveform/...`
  sont conservées. Les anciennes URL des scripts restent des alias.
- Le dashboard et le détecteur peuvent redémarrer indépendamment.

Une série se termine toujours après 90 secondes sans détection par défaut.
Pour les nouvelles séries, la durée est l’écart entre première et dernière détection,
pauses comprises. Un arrêt propre conserve aussi cette durée réelle : il ne
soustrait plus 90 secondes à une série interrompue par l’arrêt du service.
Les durées historiques importées restent inchangées.

## Préparation

Conserver une copie du code v1 et une sauvegarde complète du dossier `data/`.
La sauvegarde automatique ci-dessous couvre les métadonnées historiques, pas une
seconde copie des WAV ni les futures données v2.

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Pour préparer uniquement les unités sans toucher aux services :

```bash
.venv/bin/python install_services.py --output-dir /tmp/bark-services-v2
```

## Bascule

```bash
sudo .venv/bin/python install_services.py
```

Le compte de service est l’utilisateur qui a lancé `sudo`, ou le propriétaire
du projet depuis une session root. Pour le choisir explicitement, ajouter
`--user NOM` (par exemple `--user vhan` sur cette installation).

L’installateur arrête les deux anciens services, applique les migrations, importe
les données et vérifie les comptes de détections, séries, événements musicaux
et la somme des durées historiques. Il recharge ensuite systemd et démarre les
deux nouveaux services. En cas d’échec de la vérification, il les laisse arrêtés
et affiche l’erreur.

Le premier import conserve dans `data/backups/before-v2/` :

- une copie des anciens journaux texte et JSONL ;
- une sauvegarde SQLite cohérente de `monitoring.sqlite3` ;
- un manifeste `complete.json`.

Les originaux restent intacts. Les lignes incomplètes et malformées sont ignorées.
Une ligne terminée après un premier import peut être importée au suivant.
Les identifiants source / numéro de ligne empêchent les doublons. L’import suppose
des fichiers historiques auxquels on ajoute des lignes : ne pas les réécrire,
les renommer ou réordonner leurs lignes après migration.

L’état et la couverture de l’ancien monitoring sont importés une seule fois.
Le nouveau détecteur poursuit ensuite les mesures dans la nouvelle base.

## Vérifier et reprendre

```bash
.venv/bin/python -m app.cli verify
systemctl status bark-detector bark-dashboard
journalctl -u bark-detector -u bark-dashboard -n 50 --no-pager
```

`verify` renvoie un JSON avec `ok: true` et un code de sortie nul si les données
historiques correspondent. Il ne modifie pas la base. Les données créées directement
en v2 ne sont pas comptées comme des imports.

Pour reprendre un import après correction d’un problème, services arrêtés :

```bash
.venv/bin/python -m app.cli migrate
sudo systemctl restart bark-detector bark-dashboard
```

Pour indexer des WAV ajoutés ou supprimés manuellement :

```bash
.venv/bin/python -m app.cli sync
```

Les WAV produits par le détecteur v2 sont indexés immédiatement à leur fermeture.

## Retour arrière

1. Arrêter les deux services.
2. Restaurer le code et les unités systemd de la v1 depuis la copie conservée.
3. Conserver `bark.sqlite3` et ses éventuels fichiers `-wal` / `-shm` pour préserver
   les données créées en v2 ; ne pas les supprimer.
4. Réinstaller les unités v1, recharger systemd et relancer les services.

La v1 retrouve les journaux historiques et les WAV restés en place. Elle ne sait
pas afficher les événements créés uniquement en v2 : un retour arrière ne les
convertit pas automatiquement en journaux texte.

Pour sauvegarder une base v2 en cours d’utilisation, utiliser l’API de sauvegarde
SQLite ou arrêter les deux services avant de copier le dossier de données complet.
