from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import threading
import xml.etree.ElementTree as ET
import requests
import os
import datetime

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
GRID_URL = "http://localhost:4444"

# Xray Cloud
XRAY_CLIENT_ID = os.getenv("XRAY_CLIENT_ID", "YOUR_CLIENT_ID")
XRAY_CLIENT_SECRET = os.getenv("XRAY_CLIENT_SECRET", "YOUR_CLIENT_SECRET")

# Jira
JIRA_PROJECT_KEY = "FORM"
JIRA_TEST_EXEC_KEY = "FORM-42"

# ──────────────────────────────────────────────
# MOT DE PASSE COURANT
# Reset la BD avant de lancer → password = ".admin-2026"
# ──────────────────────────────────────────────
current_password = "admin-2026"
password_lock = threading.Lock()

# ──────────────────────────────────────────────
# COLLECTE DES RÉSULTATS
# ──────────────────────────────────────────────
results = []
results_lock = threading.Lock()

def record_result(test_id, status, error_msg="", duration=0):
    with results_lock:
        results.append({
            "id": test_id,
            "status": status,
            "error": error_msg,
            "duration": duration
        })

# ──────────────────────────────────────────────
# GÉNÉRATION JUNIT XML (format attendu par Xray)
# ──────────────────────────────────────────────
def generate_junit_xml(output_file="xray_results.xml"):
    testsuite = ET.Element("testsuite",
                           name="SeleniumGrid",
                           tests=str(len(results)))
    for r in results:
        tc = ET.SubElement(testsuite, "testcase",
                           name=r["id"],
                           classname="selenium.grid",
                           time=str(r["duration"]))
        if r["status"] == "FAIL":
            ET.SubElement(tc, "failure", message=r["error"][:300])
    tree = ET.ElementTree(testsuite)
    ET.indent(tree, space="  ")
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ JUnit XML généré : {output_file}")

# ──────────────────────────────────────────────
# ENVOI À XRAY
# ──────────────────────────────────────────────
def get_xray_token():
    r = requests.post(
        "https://xray.cloud.getxray.app/api/v2/authenticate",
        json={"client_id": XRAY_CLIENT_ID, "client_secret": XRAY_CLIENT_SECRET},
        timeout=10
    )
    r.raise_for_status()
    return r.text.strip('"')

def push_results_to_xray(xml_file):
    try:
        with open(xml_file, "rb") as f:
            xml_data = f.read()
        token = get_xray_token()
        response = requests.post(
            "https://xray.cloud.getxray.app/api/v2/import/execution/junit",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "text/xml"
            },
            params={
                "projectKey": JIRA_PROJECT_KEY,
                "testExecKey": JIRA_TEST_EXEC_KEY
            },
            data=xml_data,
            timeout=15
        )
        if response.status_code in (200, 201):
            print(f"✅ Résultats importés dans Xray : {response.json()}")
        else:
            print(f"❌ Erreur Xray {response.status_code} : {response.text}")
    except Exception as e:
        print(f"❌ Push Xray impossible : {e}")

# ──────────────────────────────────────────────
# OPTIONS NAVIGATEURS (macOS)
# ──────────────────────────────────────────────
def chrome_options_macos():
    opts = Options()
    opts.binary_location = "/Users/zaichsmail/browsers/chrome/mac-148.0.7778.56/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--remote-debugging-port=0")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    })
    return opts

def firefox_options_macos():
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    opts = FirefoxOptions()
    opts.set_preference("dom.webnotifications.enabled", False)
    return opts

def edge_options_macos():
    from selenium.webdriver.edge.options import Options as EdgeOptions
    opts = EdgeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--remote-debugging-port=0")
    return opts

# ──────────────────────────────────────────────
# SCREENSHOT HELPER
# ──────────────────────────────────────────────
def screenshot(driver, test_id, status):
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"CT_{test_id}_{status}_{ts}.png"
        driver.save_screenshot(filename)
        print(f"  -> Screenshot : {filename}")
    except Exception:
        pass

# ──────────────────────────────────────────────
# LOGIN + NAVIGATION PROFIL
# Ne réécrit PAS le mot de passe par-dessus la carte —
# efface d'abord le champ puis saisit le mot de passe fourni.
# ──────────────────────────────────────────────
def login_et_profil(driver, wait, password):
    """Login avec le mot de passe courant passé en paramètre"""
    try:
        # ── 1. Aller directement sur la page login
        driver.get("https://projet-consulting-school.fr/formation_app/login.php")
        time.sleep(4)

        # ── 2. Vider et remplir via JavaScript (fiable sur macOS, évite les pré-remplissages)
        champ_email = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type='email']")))
        driver.execute_script("arguments[0].value = '';", champ_email)
        driver.execute_script("arguments[0].value = 'marie.durand@formation.fr';", champ_email)
        # Déclencher les événements pour que le site prenne en compte la valeur
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", champ_email)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", champ_email)

        champ_mdp = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        driver.execute_script("arguments[0].value = '';", champ_mdp)
        driver.execute_script("arguments[0].value = arguments[1];", champ_mdp, password)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", champ_mdp)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", champ_mdp)
        time.sleep(1)

        # ── 3. Clic "Se connecter"
        driver.execute_script("arguments[0].click();",
            wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button#submitBtn"))))
        time.sleep(4)

        # ── 4. Ouvrir dropdown "Marie Durand"
        driver.execute_script("arguments[0].click();",
            wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.profile-chip.dropdown-toggle"))))
        time.sleep(1)

        # ── 5. Clic "Mon profil"
        driver.execute_script("arguments[0].click();",
            wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a.dropdown-item[href*='page=profil']"))))
        time.sleep(3)

    except Exception as e:
        raise Exception(f"[login_et_profil] Echec saisie identifiants ou soumission : {e}")

# ──────────────────────────────────────────────
# TESTS CT-SG1 à CT-SG3 — SÉQUENTIELS
# (modifient le MDP → current_password mis à jour)
# ──────────────────────────────────────────────
def test_sg1():
    global current_password
    driver = None
    start = time.time()
    try:
        print("\n[CT_SG1] Changement de mot de passe nominal (Chrome)")
        driver = webdriver.Remote(command_executor=GRID_URL, options=chrome_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.maximize_window()

        login_et_profil(driver, wait, current_password)

        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']"))).send_keys(current_password)
        driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']").send_keys("NouveauMdp456!")
        driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']").send_keys("NouveauMdp456!")
        driver.execute_script("arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(3)

        confirm = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".alert-success")))
        assert confirm.is_displayed()

        current_password = "NouveauMdp456!"
        print("[CT_SG1] PASSE")
        screenshot(driver, "SG1", "PASSE")
        record_result("CT-SG1", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG1] ECHEC : {e}")
        if driver:
            screenshot(driver, "SG1", "ECHEC")
        record_result("CT-SG1", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver:
            driver.quit()


def test_sg2():
    global current_password
    driver = None
    start = time.time()
    try:
        print("\n[CT_SG2] Changement de mot de passe (Firefox)")
        driver = webdriver.Remote(command_executor=GRID_URL, options=firefox_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.maximize_window()

        login_et_profil(driver, wait, current_password)

        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']"))).send_keys(current_password)
        driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']").send_keys("NouveauMdp789!")
        driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']").send_keys("NouveauMdp789!")
        driver.execute_script("arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(3)

        confirm = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".alert-success")))
        assert confirm.is_displayed()

        current_password = "NouveauMdp789!"
        print("[CT_SG2] PASSE")
        screenshot(driver, "SG2", "PASSE")
        record_result("CT-SG2", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG2] ECHEC : {e}")
        if driver:
            screenshot(driver, "SG2", "ECHEC")
        record_result("CT-SG2", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver:
            driver.quit()


def test_sg3():
    global current_password
    driver = None
    start = time.time()
    try:
        print("\n[CT_SG3] Changement de mot de passe (Edge)")
        driver = webdriver.Remote(command_executor=GRID_URL, options=edge_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.maximize_window()

        login_et_profil(driver, wait, current_password)

        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']"))).send_keys(current_password)
        driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']").send_keys("NouveauMdp111!")
        driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']").send_keys("NouveauMdp111!")
        driver.execute_script("arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(3)

        confirm = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".alert-success")))
        assert confirm.is_displayed()

        current_password = "NouveauMdp111!"
        print("[CT_SG3] PASSE")
        screenshot(driver, "SG3", "PASSE")
        record_result("CT-SG3", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG3] ECHEC : {e}")
        if driver:
            screenshot(driver, "SG3", "ECHEC")
        record_result("CT-SG3", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver:
            driver.quit()


# ──────────────────────────────────────────────
# TESTS CT-SG4 à CT-SG10 — PARALLÈLES
# Reçoivent le mot de passe en snapshot (pas de global)
# ──────────────────────────────────────────────
def test_sg4(pwd):
    driver_c = None
    driver_f = None
    start = time.time()
    try:
        print("\n[CT_SG4] Validation HTML5 champ MDP trop court (Chrome vs Firefox)")
        driver_c = webdriver.Remote(command_executor=GRID_URL, options=chrome_options_macos())
        wait_c = WebDriverWait(driver_c, 20)
        driver_c.maximize_window()

        driver_f = webdriver.Remote(command_executor=GRID_URL, options=firefox_options_macos())
        wait_f = WebDriverWait(driver_f, 20)
        driver_f.maximize_window()

        login_et_profil(driver_c, wait_c, pwd)
        login_et_profil(driver_f, wait_f, pwd)

        # Chrome
        new_pwd_chrome = wait_c.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[name='nouveau_mdp']")))
        new_pwd_chrome.clear()
        new_pwd_chrome.send_keys("abc")
        driver_c.execute_script("arguments[0].click();",
            driver_c.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(2)
        msg_chrome = driver_c.execute_script(
            "return arguments[0].validationMessage;", new_pwd_chrome)
        assert msg_chrome != ""
        print(f"  [Chrome] validationMessage : {msg_chrome}")

        # Firefox
        new_pwd_ff = wait_f.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[name='nouveau_mdp']")))
        new_pwd_ff.clear()
        new_pwd_ff.send_keys("abc")
        driver_f.execute_script("arguments[0].click();",
            driver_f.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(2)
        msg_ff = driver_f.execute_script(
            "return arguments[0].validationMessage;", new_pwd_ff)
        assert msg_ff != ""
        print(f"  [Firefox] validationMessage : {msg_ff}")

        print("[CT_SG4] PASSE")
        record_result("CT-SG4", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG4] ECHEC : {e}")
        record_result("CT-SG4", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver_c:
            driver_c.quit()
        if driver_f:
            driver_f.quit()


def test_sg5(pwd):
    driver = None
    start = time.time()
    try:
        print("\n[CT_SG5] Masquage des champs MDP")
        driver = webdriver.Remote(command_executor=GRID_URL, options=chrome_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.set_window_size(1920, 1080)

        login_et_profil(driver, wait, pwd)

        old_pwd = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']")))
        new_pwd = driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']")
        confirm_pwd = driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']")

        assert old_pwd.get_attribute("type") == "password"
        assert new_pwd.get_attribute("type") == "password"
        assert confirm_pwd.get_attribute("type") == "password"

        print("[CT_SG5] PASSE")
        screenshot(driver, "SG5", "PASSE")
        record_result("CT-SG5", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG5] ECHEC : {e}")
        if driver:
            screenshot(driver, "SG5", "ECHEC")
        record_result("CT-SG5", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver:
            driver.quit()


def test_sg6(pwd):
    driver = None
    start = time.time()
    try:
        print("\n[CT_SG6] Ancien MDP incorrect")
        driver = webdriver.Remote(command_executor=GRID_URL, options=chrome_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.set_window_size(1920, 1080)

        login_et_profil(driver, wait, pwd)

        wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']"))).send_keys("MauvaisMdp!")
        driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']").send_keys("NouveauMdp456!")
        driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']").send_keys("NouveauMdp456!")
        driver.execute_script("arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(3)

        error = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".alert-danger, [class*='error']")))
        assert error.is_displayed()
        assert "page=profil" in driver.current_url

        print("[CT_SG6] PASSE")
        screenshot(driver, "SG6", "PASSE")
        record_result("CT-SG6", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG6] ECHEC : {e}")
        if driver:
            screenshot(driver, "SG6", "ECHEC")
        record_result("CT-SG6", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver:
            driver.quit()


def test_sg7(pwd):
    driver = None
    start = time.time()
    try:
        print("\n[CT_SG7] MDP et confirmation non concordants")
        driver = webdriver.Remote(command_executor=GRID_URL, options=chrome_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.set_window_size(1920, 1080)

        login_et_profil(driver, wait, pwd)

        wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']"))).send_keys(pwd)
        driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']").send_keys("NouveauMdp456!")
        driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']").send_keys("MotDePasseDifferent!")
        driver.execute_script("arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(3)

        error = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".alert-danger, [class*='error']")))
        assert error.is_displayed()
        assert driver.find_element(
            By.CSS_SELECTOR, "input[name='nouveau_mdp']").is_displayed()

        print("[CT_SG7] PASSE")
        screenshot(driver, "SG7", "PASSE")
        record_result("CT-SG7", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG7] ECHEC : {e}")
        if driver:
            screenshot(driver, "SG7", "ECHEC")
        record_result("CT-SG7", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver:
            driver.quit()


def test_sg8(pwd):
    driver = None
    start = time.time()
    try:
        print("\n[CT_SG8] Confirmation succès + absence d'erreurs visibles")
        driver = webdriver.Remote(command_executor=GRID_URL, options=chrome_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.set_window_size(1920, 1080)

        login_et_profil(driver, wait, pwd)

        wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']"))).send_keys(pwd)
        driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']").send_keys("NouveauMdp999!")
        driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']").send_keys("NouveauMdp999!")
        driver.execute_script("arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(3)

        confirm = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".alert-success")))
        assert confirm.is_displayed()
        errors = driver.find_elements(By.CSS_SELECTOR, ".alert-danger, [class*='error']")
        assert len(errors) == 0

        print("[CT_SG8] PASSE")
        screenshot(driver, "SG8", "PASSE")
        record_result("CT-SG8", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG8] ECHEC : {e}")
        if driver:
            screenshot(driver, "SG8", "ECHEC")
        record_result("CT-SG8", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver:
            driver.quit()


def test_sg9(pwd):
    driver = None
    start = time.time()
    try:
        print("\n[CT_SG9] Résolution 1920x1080 - pas de scroll horizontal")
        driver = webdriver.Remote(command_executor=GRID_URL, options=chrome_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.set_window_size(1920, 1080)

        size = driver.get_window_size()
        assert size['width'] == 1920 and size['height'] == 1080

        login_et_profil(driver, wait, pwd)

        wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']")))
        scroll_w = driver.execute_script("return document.body.scrollWidth")
        client_w = driver.execute_script("return document.body.clientWidth")
        assert scroll_w == client_w

        driver.find_element(By.CSS_SELECTOR, "input[name='ancien_mdp']").send_keys(pwd)
        driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']").send_keys("NouveauMdp1920!")
        driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']").send_keys("NouveauMdp1920!")
        driver.execute_script("arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(3)

        confirm = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".alert-success")))
        assert confirm.is_displayed()

        print("[CT_SG9] PASSE")
        screenshot(driver, "SG9", "PASSE")
        record_result("CT-SG9", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG9] ECHEC : {e}")
        if driver:
            screenshot(driver, "SG9", "ECHEC")
        record_result("CT-SG9", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver:
            driver.quit()


def test_sg10(pwd):
    driver = None
    start = time.time()
    try:
        print("\n[CT_SG10] Résolution 1280x720 - pas de scroll horizontal")
        driver = webdriver.Remote(command_executor=GRID_URL, options=chrome_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.set_window_size(1280, 720)

        size = driver.get_window_size()
        assert size['width'] == 1280 and size['height'] == 720

        login_et_profil(driver, wait, pwd)

        wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']")))
        scroll_w = driver.execute_script("return document.body.scrollWidth")
        client_w = driver.execute_script("return document.body.clientWidth")
        assert scroll_w == client_w

        driver.find_element(By.CSS_SELECTOR, "input[name='ancien_mdp']").send_keys(pwd)
        driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']").send_keys("NouveauMdp1280!")
        driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']").send_keys("NouveauMdp1280!")
        driver.execute_script("arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(3)

        confirm = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".alert-success")))
        assert confirm.is_displayed()

        print("[CT_SG10] PASSE")
        screenshot(driver, "SG10", "PASSE")
        record_result("CT-SG10", "PASS", duration=round(time.time() - start, 2))

    except Exception as e:
        print(f"[CT_SG10] ECHEC : {e}")
        if driver:
            screenshot(driver, "SG10", "ECHEC")
        record_result("CT-SG10", "FAIL", str(e), round(time.time() - start, 2))
    finally:
        if driver:
            driver.quit()


# ──────────────────────────────────────────────
# RESET MOT DE PASSE → .admin-2026
# À appeler à la fin pour que le repo GitHub
# soit toujours dans un état connu au prochain lancement
# ──────────────────────────────────────────────
def reset_password():
    driver = None
    try:
        print("\n[RESET] Remise du mot de passe à admin-2026 ...")
        driver = webdriver.Remote(command_executor=GRID_URL, options=chrome_options_macos())
        wait = WebDriverWait(driver, 20)
        driver.maximize_window()

        login_et_profil(driver, wait, current_password)

        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[name='ancien_mdp']"))).send_keys(current_password)
        driver.find_element(By.CSS_SELECTOR, "input[name='nouveau_mdp']").send_keys(".admin-2026")
        driver.find_element(By.CSS_SELECTOR, "input[name='confirmer_mdp']").send_keys(".admin-2026")
        driver.execute_script("arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "button.btn.btn-outline-primary"))
        time.sleep(3)

        confirm = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, ".alert-success")))
        assert confirm.is_displayed()
        print("[RESET] ✅ Mot de passe remis à admin-2026 — prêt pour le prochain lancement")

    except Exception as e:
        print(f"[RESET] ❌ Echec reset mot de passe : {e}")
        if driver:
            screenshot(driver, "RESET", "ECHEC")
    finally:
        if driver:
            driver.quit()


# ──────────────────────────────────────────────
# LANCEMENT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=== LANCEMENT DES TESTS VIA SELENIUM GRID ===\n")

    # ── FIX CT-SG1 : délai de stabilisation du Grid au démarrage
    print("[INFO] Attente stabilisation du Grid (5s)...")
    time.sleep(5)

    # SG1, SG2, SG3 séquentiels (modifient le MDP)
    test_sg1()
    test_sg2()
    test_sg3()

    # Snapshot du mot de passe APRÈS les tests séquentiels
    # Les tests parallèles utilisent ce snapshot — pas la variable globale
    pwd_snapshot = current_password
    print(f"\n[INFO] Mot de passe utilisé pour les tests parallèles : {pwd_snapshot}\n")

    # ── FIX CT-SG4 / CT-SG10 : parallélisme limité à 4 sessions Chrome max
    # SG4 utilise 2 Chrome → occupe 2 slots ; SG5/SG6/SG7 = 1 Chrome chacun
    # Groupe 1 : SG4 (2 Chrome) + SG5 + SG6 = 4 Chrome simultanés ✅
    print("[INFO] Groupe 1 : CT-SG4, CT-SG5, CT-SG6 (4 Chrome max)")
    threads_1 = [
        threading.Thread(target=test_sg4, args=(pwd_snapshot,)),
        threading.Thread(target=test_sg5, args=(pwd_snapshot,)),
        threading.Thread(target=test_sg6, args=(pwd_snapshot,)),
    ]
    for t in threads_1:
        t.start()
    for t in threads_1:
        t.join()

    # Groupe 2 : SG7 + SG8 + SG9 + SG10 = 4 Chrome simultanés ✅
    print("[INFO] Groupe 2 : CT-SG7, CT-SG8, CT-SG9, CT-SG10 (4 Chrome max)")
    threads_2 = [
        threading.Thread(target=test_sg7,  args=(pwd_snapshot,)),
        threading.Thread(target=test_sg8,  args=(pwd_snapshot,)),
        threading.Thread(target=test_sg9,  args=(pwd_snapshot,)),
        threading.Thread(target=test_sg10, args=(pwd_snapshot,)),
    ]
    for t in threads_2:
        t.start()
    for t in threads_2:
        t.join()

    print("\n=== TOUS LES TESTS TERMINÉS ===")

    # Résumé
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = len(results) - passed
    print(f"\n✅ PASS : {passed} | ❌ FAIL : {failed} | Total : {len(results)}")

    # Génération JUnit XML
    generate_junit_xml("xray_results.xml")

    # ── Reset mot de passe à .admin-2026 pour la prochaine exécution (GitHub)
    reset_password()

    # Push Xray
    print("\n" + "=" * 60)
    reponse = input("▶ Pusher les résultats vers Xray ? (o/n) : ").strip().lower()
    if reponse in ("o", "oui", "y", "yes", ""):
        push_results_to_xray("xray_results.xml")
    else:
        print("Push annulé. Fichier disponible : xray_results.xml")
