# formationapp-tests selenium

Tests automatisés pour le changement de mot de passe sur FormationApp.

## Setup (5 minutes)

### 1. Copier la configuration
```bash
cp config/environment.example.py config/environment.py
```

### 2. Remplir config/environment.py
```python
TEST_EMAIL = "votre-email@test.com"
TEST_PASSWORD = "votre-mot-de-passe"
XRAY_CLIENT_ID = "votre-client-id"
XRAY_CLIENT_SECRET = "votre-secret"
```

### 3. Démarrer Selenium Grid
```bash
docker-compose up -d
```

### 4. Lancer les tests
```bash
python run_tests.py
```

C'est tout !

## Tests Inclus

- CT-SG1 : Chrome - Changement MDP
- CT-SG2 : Firefox - Changement MDP
- CT-SG3 : Edge - Changement MDP
- CT-SG4 à SG10 : Validation, responsive design, etc.

## Questions ?

Lire docs/SETUP.md pour plus de détails.
