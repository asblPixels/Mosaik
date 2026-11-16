# Contribuer à Mosaïk / Contributing to Mosaïk

Merci de vouloir contribuer ! 🎉 · Thank you for considering contributing! 🎉

## Comment contribuer / How to contribute

1. **Forkez** le dépôt / **Fork** the repository.
2. **Clonez** votre fork : `git clone https://github.com/VOTRE_COMPTE/Mosaik.git`
3. **Créez une branche** : `git checkout -b feature/ma-fonctionnalite`
4. **Faites vos changements** et lancez les tests (voir ci-dessous).
5. **Committez** avec un message clair : `git commit -m "feat: décrire le changement"`
6. **Poussez** et ouvrez une **Pull Request**.

## Convention des messages / Commit messages

Nous suivons [Conventional Commits](https://www.conventionalcommits.org/) :

- `feat:` nouvelle fonctionnalité / new feature
- `fix:` correction de bug / bug fix
- `docs:` documentation
- `refactor:` refactorisation
- `style:` mise en forme / formatting
- `test:` tests
- `chore:` maintenance

## Règles du projet / Project rules

- **Aucune dépendance** : uniquement la bibliothèque standard de Python 3.8+. C'est ce qui rend Mosaïk compatible avec toutes les distributions. / **No dependencies**: Python 3.8+ standard library only.
- **Jamais d'écriture sur le disque source** : toute lecture passe par `Source` (ouvert en `O_RDONLY`). / **Never write to the source disk.**
- Python : PEP 8, indentation 4 espaces, `pyflakes` propre.
- Shell : POSIX `sh`, propre avec `shellcheck`.
- Interface : un seul fichier `ui.html`, sans bibliothèque ni CDN (fonctionne hors ligne).
- Nouveau format de fichier : ajoutez un carveur dans `Carvers`, sa signature dans `SIGNATURES`, et un cas dans `tests/test_recuperation.py`.

## Tests

```bash
pip install pillow pyflakes
python3 -m pyflakes mosaik.py
python3 tests/test_recuperation.py
```

## Signaler un bug / Reporting bugs

Utilisez le [modèle de rapport de bug](.github/ISSUE_TEMPLATE/bug_report.md). Indiquez :
- votre distribution (`cat /etc/os-release`) ;
- la version de Python (`python3 --version`) et de Mosaïk (`mosaik --version`) ;
- la version de The Sleuth Kit si installé (`fls -V`) ;
- le type de support (disque dur, SSD, clé USB, carte SD) et le système de fichiers ;
- le journal affiché dans l'interface et le fichier `rapport.csv`.

⚠️ **Ne joignez jamais d'image disque ni de fichiers récupérés** : ils peuvent contenir des données personnelles.

## Proposer une idée / Feature requests

Utilisez le [modèle de demande de fonctionnalité](.github/ISSUE_TEMPLATE/feature_request.md).

## Licence

En contribuant, vous acceptez que votre contribution soit publiée sous [licence MIT](LICENSE).
