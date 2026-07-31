import json
import logging
import time
from pathlib import Path
from urllib.parse import urljoin

from PySide6.QtCore import QTimer, Qt, Signal, QUrl
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineDownloadRequest,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestInfo,
)

import src.gui.coa_parser_tab as _coa_parser_tab

logger = logging.getLogger("coa_parser")


class _RequestLogger(QWebEngineUrlRequestInterceptor):
    """Logs every URL request from the web engine to help debug DOC downloads."""

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        url = info.requestUrl().toString()
        method = info.requestMethod()
        resource = info.resourceType()
        logger.warning("[REQ] %s %s (type=%s)", method, url, resource)


# ── One-shot click capturer (injected each time we need to capture one step) ───

_CAPTURE_JS = r"""
(function() {
    if (document.getElementById('coa-capture-style')) {
        return JSON.stringify({error: 'already active'});
    }

    function extractUrls(el) {
        var urls = [];
        if (el.href && el.href !== '#') urls.push(el.href);
        ['data-url','data-href','data-endpoint','data-download-url','data-action','data-request-url'].forEach(function(a) {
            var v = el.getAttribute(a);
            if (v) urls.push(v);
        });
        var form = el.closest('form');
        if (form && form.action) urls.push(form.action);
        var oc = el.getAttribute('onclick');
        if (oc) {
            var m = oc.match(/['"]([^'"]*download[^'"]*)['"]/i);
            if (m) urls.push(m[1]);
            m = oc.match(/['"]([^'"]*\/filesystm[^'"]*)['"]/i);
            if (m) urls.push(m[1]);
        }
        return urls.filter(function(u){return u;});
    }

    function buildPath(el) {
        var path = [];
        while (el && el.nodeType === 1) {
            var s = el.tagName.toLowerCase();
            if (el.id) { path.unshift('#' + CSS.escape(el.id)); break; }
            var c = el.className;
            if (c && typeof c === 'string') {
                var parts = c.trim().split(/\s+/).filter(function(x){return x;});
                if (parts.length) s += '.' + parts.map(function(x){return CSS.escape(x);}).join('.');
            }
            var n = 1, peer = el;
            while (peer = peer.previousElementSibling) {
                if (peer.tagName === el.tagName) n++;
            }
            path.unshift(s + ':nth-of-type(' + n + ')');
            el = el.parentElement;
        }
        return path.join(' > ');
    }

    function capture(el) {
        var selectors = [];
        var tag = el.tagName.toLowerCase();

        if (el.id) selectors.push('#' + CSS.escape(el.id));
        var aria = el.getAttribute('aria-label');
        if (aria) selectors.push('[aria-label=' + CSS.escape(aria) + ']');
        var testid = el.getAttribute('data-testid');
        if (testid) selectors.push('[data-testid=' + CSS.escape(testid) + ']');
        var title = el.getAttribute('title');
        if (title) selectors.push('[title=' + CSS.escape(title) + ']');
        ['data-qa','data-id','data-name','data-action','data-attribute'].forEach(function(a) {
            var v = el.getAttribute(a);
            if (v) selectors.push('[' + a + '=' + CSS.escape(v) + ']');
        });
        if (el.className && typeof el.className === 'string') {
            var cls = el.className.trim().split(/\s+/).filter(function(c){return c;});
            if (cls.length) {
                selectors.push(tag + '.' + cls.map(function(c){return CSS.escape(c);}).join('.'));
                if (el.parentElement) {
                    var ps = el.parentElement.tagName.toLowerCase();
                    var pcls = el.parentElement.className;
                    if (pcls && typeof pcls === 'string') {
                        var pc = pcls.trim().split(/\s+/).filter(function(c){return c;});
                        if (pc.length) ps += '.' + pc.map(function(c){return CSS.escape(c);}).join('.');
                    }
                    selectors.push(ps + ' > ' + tag + '.' + cls.map(function(c){return CSS.escape(c);}).join('.'));
                }
            }
        }
        var text = (el.innerText || '').trim();
        if (text && text.length < 100) {
            selectors.push('//' + tag.toUpperCase() + '[contains(text(),' + JSON.stringify(text) + ')]');
        }
        selectors.push(buildPath(el));

        var urls = extractUrls(el);

        var data = JSON.stringify({
            selectors: selectors,
            text: text,
            tag: tag,
            href: el.href || '',
            urls: urls
        });

        // Save both ways: window (fast poll) + localStorage (survives navigation)
        window.__coa_capture_result = data;
        try { localStorage.setItem('__coa_capture_result', data); } catch(ex) {}
    }

    // Style + overlay
    var style = document.createElement('style');
    style.id = 'coa-capture-style';
    style.textContent = '.coa-capture-hl { outline: 3px solid #f60 !important; background: rgba(255,102,0,0.08) !important; cursor: crosshair !important; }';
    document.head.appendChild(style);

    var overlay = document.createElement('div');
    overlay.id = 'coa-capture-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;padding:10px;background:#f60;color:#fff;font:bold 15px sans-serif;text-align:center;z-index:999999;pointer-events:none;';
    overlay.textContent = 'CAPTURE MODE — Click the element for this step';
    document.body.appendChild(overlay);

    // mousedown fires BEFORE click/navigation — capture data immediately
    var handler = function(e) {
        capture(e.target);
        document.getElementById('coa-capture-style')?.remove();
        document.getElementById('coa-capture-overlay')?.remove();
    };
    document.addEventListener('mousedown', handler, true);
    // Track listener for cleanup
    var listeners = document.__coa_capture_listeners;
    if (!listeners) { listeners = []; document.__coa_capture_listeners = listeners; }
    listeners.push(handler);

    return JSON.stringify({ok: true});
})()
"""

_CAPTURE_POLL_JS = r"""
(function() {
    var r = window.__coa_capture_result;
    if (r) {
        window.__coa_capture_result = null;
        return r;
    }
    try {
        r = localStorage.getItem('__coa_capture_result');
        if (r) {
            localStorage.removeItem('__coa_capture_result');
            return r;
        }
    } catch(ex) {}
    return null;
})()
"""

_CAPTURE_CLEANUP_JS = r"""
(function() {
    document.getElementById('coa-capture-style')?.remove();
    document.getElementById('coa-capture-overlay')?.remove();
    window.__coa_capture_result = null;
    try { localStorage.removeItem('__coa_capture_result'); } catch(ex) {}
    // Remove all old capture mousedown listeners
    var old = document.__coa_capture_listeners;
    if (old) {
        old.forEach(function(fn) { document.removeEventListener('mousedown', fn, true); });
        document.__coa_capture_listeners = [];
    }
    return true;
})()
"""

_WATCHER_JS = r"""
(function() {
    if (document.getElementById('coa-watcher-marker')) {
        return 'already active';
    }
    var marker = document.createElement('div');
    marker.id = 'coa-watcher-marker';
    marker.style.display = 'none';
    document.body.appendChild(marker);

    var processing = false;
    var processedPkgIds = new Set();
    var absentCount = 0;

    function getPkgIdFromRow(row) {
        if (!row) return null;
        var cells = row.querySelectorAll('td');
        if (cells.length < 2) return null;
        return cells[1].textContent.trim() || null;
    }

    function getDetailContainer(masterRow) {
        var detailRow = masterRow.nextElementSibling;
        return (detailRow && detailRow.classList.contains('k-detail-row')) ? detailRow : null;
    }

    window.__coa_watcher_interval = setInterval(function() {
        if (processing) return;

        var collapseEls = document.querySelectorAll('[aria-label=Collapse]');
        if (collapseEls.length === 0) {
            absentCount++;
            if (absentCount >= 6 && processedPkgIds.size > 0) {
                processedPkgIds.clear();
            }
            return;
        }
        absentCount = 0;

        for (var i = 0; i < collapseEls.length; i++) {
            var masterRow = collapseEls[i].closest('tr');
            var pkgId = getPkgIdFromRow(masterRow);
            if (!pkgId || processedPkgIds.has(pkgId)) continue;

            var detailRow = getDetailContainer(masterRow);
            if (!detailRow) break;

            processedPkgIds.add(pkgId);
            processing = true;

            (function(dr) {
                setTimeout(function() {
                    var labTab = document.evaluate(
                        './/SPAN[contains(text(),"Lab Results")]',
                        dr, null,
                        XPathResult.FIRST_ORDERED_NODE_TYPE, null
                    ).singleNodeValue;
                    if (labTab) labTab.click();

                    setTimeout(function() {
                        var docBtn = dr.querySelector('a.k-button.k-button-icontext.grid-row-button.k-grid-download-document');
                        if (!docBtn) docBtn = dr.querySelector('span.icon-file');
                        if (docBtn) docBtn.click();
                        processing = false;
                    }, 1200);
                }, 500);
            })(detailRow);

            break;
        }
    }, 250);

    return 'watching';
})()
"""

_WATCHER_STOP_JS = r"""
(function() {
    var m = document.getElementById('coa-watcher-marker');
    if (m) m.remove();
    if (window.__coa_watcher_interval) {
        clearInterval(window.__coa_watcher_interval);
        window.__coa_watcher_interval = null;
    }
    return true;
})()
"""

# ── Click execution ────────────────────────────────────────────────────

_CLICK_JS_T = "(function(){{var e=document.querySelector({sel!r});if(e){{e.click();return true;}}return false;}})()"
_COUNT_ALL_JS_T = "document.querySelectorAll({sel!r}).length"
_NTH_CLICK_JS_T = "(function(){{var e=document.querySelectorAll({sel!r})[{n}];if(e){{e.click();return true;}}return false;}})()"

# ── Login autofill JS ────────────────────────────────────────────────

_LOGIN_JS = r"""
(function() {
    try {
        var username = __USERNAME__;
        var password = __PASSWORD__;
        var found = false;

        function setValue(el, val) {
            el.focus();
            el.value = val;
            el.dispatchEvent(new Event('input', {bubbles: true, cancelable: true}));
            el.dispatchEvent(new Event('change', {bubbles: true, cancelable: true}));
            el.blur();
        }

        function findAndFill() {
            var userField = document.querySelector('#Username, #username, #UserId, #user_id, #email, #Email, #EmailAddress, #LoginUser_UserName, input[name="username"], input[name="email"], input[name="UserName"], input[name="UserId"]');
            var passField = document.querySelector('#Password, #password, #LoginPassword, input[name="password"], input[name="Password"]');

            if (!userField || !passField) {
                var inputs = document.querySelectorAll('input');
                for (var i = 0; i < inputs.length; i++) {
                    var inp = inputs[i];
                    if (inp.type === 'password') { if (!passField) passField = inp; }
                    else if (!userField && (inp.type === 'text' || inp.type === 'email' || inp.type === 'search')) userField = inp;
                }
            }

            if (userField && passField) {
                setValue(userField, username);
                setValue(passField, password);
                var btn = document.querySelector('button[type="submit"], input[type="submit"], .btn-primary, .login-button, #loginButton, #LoginButton, #login-btn');
                if (!btn) {
                    var allBtns = document.querySelectorAll('button, input[type="submit"]');
                    for (var i = 0; i < allBtns.length; i++) {
                        var txt = (allBtns[i].textContent || allBtns[i].value || '').toLowerCase();
                        if (txt.indexOf('log') !== -1 || txt.indexOf('sign') !== -1 || txt.indexOf('submit') !== -1) { btn = allBtns[i]; break; }
                    }
                }
                if (btn) setTimeout(function() { btn.click(); }, 200);
                found = true;
                return true;
            }
            return false;
        }

        if (findAndFill()) return 'ok';

        var observer = new MutationObserver(function() {
            if (!found && findAndFill()) {
                observer.disconnect();
            }
        });
        observer.observe(document.body, {childList: true, subtree: true, attributes: false});

        var tries = 0;
        var pollTimer = setInterval(function() {
            tries++;
            if (found || tries > 20) { clearInterval(pollTimer); observer.disconnect(); }
            else if (findAndFill()) { clearInterval(pollTimer); observer.disconnect(); }
        }, 500);

        return 'watching';
    } catch(e) {
        console.error('Login JS error:', e.message, e.stack);
        return 'error:' + e.message;
    }
})()
"""

_POPUP_JS = r"""
(function() {
    var origOpen = window.open;
    var _coaIframeCount = 0;
    window.open = function(url, target, features) {
        if (url && (url.indexOf('/filesystem/') !== -1 || url.indexOf('/document') !== -1 || url.indexOf('.pdf') !== -1)) {
            var iframe = document.createElement('iframe');
            iframe.style.display = 'none';
            iframe.src = url;
            document.body.appendChild(iframe);
            _coaIframeCount++;
            if (_coaIframeCount > 10) {
                var old = document.querySelector('iframe[src*="/filesystem/"], iframe[src*="/document"], iframe[src*=".pdf"]');
                if (old && old.parentNode) old.parentNode.removeChild(old);
            }
            return iframe.contentWindow;
        }
        return origOpen ? origOpen.apply(this, arguments) : null;
    };
})();
"""


def _login_js(username: str, password: str) -> str:
    return _LOGIN_JS.replace("__USERNAME__", repr(username)).replace("__PASSWORD__", repr(password))

# ── Config files ─────────────────────────────────────────────────────

CONFIG_DIR = _coa_parser_tab.INPUT_DIR.parent / ".opencode"
RECIPES_PATH = CONFIG_DIR / "metrc_recipes.json"
PROFILES_PATH = CONFIG_DIR / "metrc_profiles.json"


def _load_recipes() -> list[dict]:
    if RECIPES_PATH.exists():
        try:
            return json.loads(RECIPES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load metrc_recipes.json")
    return []


def _save_recipes(recipes: list[dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RECIPES_PATH.write_text(
        json.dumps(recipes, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_profiles() -> list[dict]:
    if PROFILES_PATH.exists():
        try:
            return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to load metrc_profiles.json")
    return []


def _save_profiles(profiles: list[dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_PATH.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Dialog for managing recipes ────────────────────────────────────────

class RecipeManagerDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Recipes")
        self.setMinimumWidth(500)
        self.resize(500, 400)

        self.recipes = _load_recipes()
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Saved Recipes:</b>"))

        self._list = QListWidget()
        for r in self.recipes:
            name = r.get("name", "Unnamed")
            steps = len(r.get("steps", []))
            self._list.addItem(f"{name}  ({steps} steps)")
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        delete_btn = QPushButton("Delete Selected")
        delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _delete_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete recipe '{self.recipes[row].get('name', 'Unnamed')}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.recipes.pop(row)
        _save_recipes(self.recipes)
        self._list.takeItem(row)


# ── Dialog for managing profiles ─────────────────────────────────────

class ProfileManagerDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Profiles")
        self.setMinimumWidth(450)
        self.resize(450, 350)

        self.profiles = _load_profiles()
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Saved Profiles:</b>"))

        self._list = QListWidget()
        for p in self.profiles:
            name = p.get("name", "Unnamed")
            user = p.get("username", "")
            self._list.addItem(f"{name}  ({user})")
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_profile)
        btn_row.addWidget(add_btn)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_profile)
        btn_row.addWidget(edit_btn)
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _add_profile(self) -> None:
        dlg = ProfileEditDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.profiles.append(dlg.profile_data())
            _save_profiles(self.profiles)
            self._refresh_list()

    def _edit_profile(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        dlg = ProfileEditDialog(self, self.profiles[row])
        if dlg.exec() == QDialog.Accepted:
            self.profiles[row] = dlg.profile_data()
            _save_profiles(self.profiles)
            self._refresh_list()

    def _delete_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete profile '{self.profiles[row].get('name', 'Unnamed')}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.profiles.pop(row)
        _save_profiles(self.profiles)
        self._list.takeItem(row)

    def _refresh_list(self) -> None:
        self._list.clear()
        for p in self.profiles:
            name = p.get("name", "Unnamed")
            user = p.get("username", "")
            self._list.addItem(f"{name}  ({user})")


class ProfileEditDialog(QDialog):
    def __init__(self, parent: QWidget | None = None,
                 data: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Profile" if data else "Add Profile")
        self.setMinimumWidth(380)

        self._data = data or {}

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Profile Name:"))
        self._name_edit = QLineEdit(self._data.get("name", ""))
        layout.addWidget(self._name_edit)

        layout.addWidget(QLabel("Username / Email:"))
        self._user_edit = QLineEdit(self._data.get("username", ""))
        layout.addWidget(self._user_edit)

        layout.addWidget(QLabel("Password:"))
        self._pass_edit = QLineEdit(self._data.get("password", ""))
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._pass_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def profile_data(self) -> dict:
        return {
            "name": self._name_edit.text().strip(),
            "username": self._user_edit.text().strip(),
            "password": self._pass_edit.text(),
        }


# ── Main tab widget ────────────────────────────────────────────────────

class METRCDownloaderTab(QWidget):
    pdf_downloaded = Signal(str)

    DEFAULT_ZOOM = 0.65

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile = QWebEngineProfile.defaultProfile()
        self._profile.setDownloadPath(str(_coa_parser_tab.INPUT_DIR))
        self._request_logger = _RequestLogger(self)
        self._profile.setUrlRequestInterceptor(self._request_logger)
        self._profile.downloadRequested.connect(self._on_download_requested)
        self._current_download: QWebEngineDownloadRequest | None = None
        self._capture_timeout: float = 0
        self._zoom_factor = self.DEFAULT_ZOOM
        self._detect_active = False
        self._detect_cancelled = False
        self._pre_detect_url: str | None = None

        # Detection state
        self._detect_queue: list[dict] = []
        self._detect_total = 0
        self._detect_completed = 0
        self._detect_recipe_idx = 0
        self._detect_step_idx = 0
        self._detect_recipes: list[dict] = []
        self._pending_login: tuple[str, str] | None = None

        # Recording state
        self._recording_steps: list[dict] = []

        # Execution state
        self._pending_urls: list[str] = []
        self._pending_selectors: list[str] = []
        self._pending_delay_ms = 5000

        # Download tracking
        self._return_url: str | None = None
        self._download_triggered = False



        self._build_ui()
        self._refresh_profiles()
        self.navigate("https://ok.metrc.com/log-in?ReturnUrl=%2f")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("METRC Downloader")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)

        nav = QHBoxLayout()
        nav.setSpacing(6)

        self._back_btn = QPushButton("<")
        self._back_btn.setFixedWidth(32)
        self._back_btn.clicked.connect(self._go_back)
        nav.addWidget(self._back_btn)

        self._fwd_btn = QPushButton(">")
        self._fwd_btn.setFixedWidth(32)
        self._fwd_btn.clicked.connect(self._go_forward)
        nav.addWidget(self._fwd_btn)

        self._refresh_btn = QPushButton("R")
        self._refresh_btn.setFixedWidth(32)
        self._refresh_btn.clicked.connect(self._reload)
        nav.addWidget(self._refresh_btn)

        self._zoom_out_btn = QPushButton("A-")
        self._zoom_out_btn.setFixedWidth(36)
        self._zoom_out_btn.setStyleSheet("font-size: 11px;")
        self._zoom_out_btn.clicked.connect(self._zoom_out)
        nav.addWidget(self._zoom_out_btn)

        self._zoom_label = QLabel("75%")
        self._zoom_label.setStyleSheet("font-size: 11px; min-width: 32px; text-align: center;")
        nav.addWidget(self._zoom_label)

        self._zoom_in_btn = QPushButton("A+")
        self._zoom_in_btn.setFixedWidth(36)
        self._zoom_in_btn.setStyleSheet("font-size: 11px;")
        self._zoom_in_btn.clicked.connect(self._zoom_in)
        nav.addWidget(self._zoom_in_btn)

        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(140)
        nav.addWidget(self._profile_combo)

        self._login_btn = QPushButton("Login")
        self._login_btn.setStyleSheet("background: #27ae60; color: #fff; font-weight: 600;")
        self._login_btn.clicked.connect(self._do_login)
        nav.addWidget(self._login_btn)

        self._profiles_btn = QPushButton("Profiles")
        self._profiles_btn.clicked.connect(self._open_profile_manager)
        nav.addWidget(self._profiles_btn)

        self._url_bar = QLineEdit()
        self._url_bar.setPlaceholderText("Enter URL and press Enter...")
        self._url_bar.returnPressed.connect(self._navigate_to_url)
        nav.addWidget(self._url_bar, stretch=1)

        layout.addLayout(nav)

        recipe_bar = QHBoxLayout()
        recipe_bar.setSpacing(6)

        self._watch_btn = QPushButton("Watch")
        self._watch_btn.setCheckable(True)
        self._watch_btn.setStyleSheet("background: #27ae60; color: #fff; font-weight: 700; padding: 4px 14px;")
        self._watch_btn.toggled.connect(self._on_watch_toggled)
        recipe_bar.addWidget(self._watch_btn)

        recipe_bar.addSpacing(12)

        self._record_btn = QPushButton("Record Recipe")
        self._record_btn.setCheckable(True)
        self._record_btn.setStyleSheet("font-weight: 600;")
        self._record_btn.toggled.connect(self._on_record_toggled)
        recipe_bar.addWidget(self._record_btn)

        self._add_step_btn = QPushButton("Add Step")
        self._add_step_btn.setVisible(False)
        self._add_step_btn.setStyleSheet("background: #f39c12; color: #fff; font-weight: 600;")
        self._add_step_btn.clicked.connect(self._capture_next_step)
        recipe_bar.addWidget(self._add_step_btn)

        self._detect_btn = QPushButton("Run Recipes")
        self._detect_btn.setStyleSheet("background: #8e44ad; color: #fff; font-weight: 600;")
        self._detect_btn.clicked.connect(self._detect_downloads)
        recipe_bar.addWidget(self._detect_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setVisible(False)
        self._cancel_btn.setStyleSheet("background: #c0392b; color: #fff; font-weight: 600;")
        self._cancel_btn.clicked.connect(self._cancel_detect)
        recipe_bar.addWidget(self._cancel_btn)

        self._recipes_btn = QPushButton("Manage Recipes...")
        self._recipes_btn.clicked.connect(self._open_recipe_manager)
        recipe_bar.addWidget(self._recipes_btn)

        self._dump_btn = QPushButton("Dump HTML")
        self._dump_btn.setStyleSheet("font-size: 10px;")
        self._dump_btn.clicked.connect(self._dump_page_html)
        recipe_bar.addWidget(self._dump_btn)

        recipe_bar.addStretch()
        layout.addLayout(recipe_bar)

        self._web_view = QWebEngineView()
        self._web_view.settings().setAttribute(QWebEngineSettings.PdfViewerEnabled, False)
        self._web_view.urlChanged.connect(self._on_url_changed)
        self._web_view.loadStarted.connect(self._on_load_started)
        self._web_view.loadFinished.connect(self._on_load_finished)
        layout.addWidget(self._web_view, stretch=1)

        status_layout = QHBoxLayout()
        status_layout.setSpacing(6)

        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("font-size: 11px; color: #555;")
        status_layout.addWidget(self._status_label)

        self._download_bar = QProgressBar()
        self._download_bar.setVisible(False)
        self._download_bar.setTextVisible(True)
        self._download_bar.setMaximumWidth(200)
        status_layout.addWidget(self._download_bar)

        status_layout.addStretch()
        layout.addLayout(status_layout)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate(self, url: str) -> None:
        self._web_view.setUrl(url)

    def _navigate_to_url(self) -> None:
        url = self._url_bar.text().strip()
        if not url.startswith("http"):
            url = "https://" + url
        self._web_view.setUrl(url)

    def _go_back(self) -> None:
        self._web_view.back()

    def _go_forward(self) -> None:
        self._web_view.forward()

    def _reload(self) -> None:
        self._web_view.reload()

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def _refresh_profiles(self) -> None:
        self._profile_combo.clear()
        self._profile_combo.addItem("-- No Profile --", None)
        for p in _load_profiles():
            self._profile_combo.addItem(p.get("name", "?"), p)

    def _open_profile_manager(self) -> None:
        dlg = ProfileManagerDialog(self)
        dlg.exec()
        self._refresh_profiles()

    def _do_login(self) -> None:
        data = self._profile_combo.currentData()
        if not data:
            QMessageBox.information(
                self, "No Profile",
                "Select a profile from the dropdown, then click Login.\n\n"
                "Add profiles via the Profiles button."
            )
            return

        username = data.get("username", "").strip()
        password = data.get("password", "")
        if not username:
            self._status_label.setText("Profile has no username")
            return

        self._pending_login = (username, password)
        self.navigate("https://ok.metrc.com/log-in?ReturnUrl=%2f")

    def _on_load_finished(self, ok: bool) -> None:
        if ok:
            self._status_label.setText("Ready")
            if self._pending_login:
                user, pw = self._pending_login
                self._pending_login = None
                QTimer.singleShot(500, lambda: self._do_autofill(user, pw))
        else:
            self._status_label.setText("Page load failed")
        self._apply_zoom()
        self._web_view.page().runJavaScript(_POPUP_JS)

    def _do_autofill(self, username: str, password: str) -> None:
        self._web_view.page().runJavaScript(_login_js(username, password), self._on_login_result)

    def _on_login_result(self, result: object) -> None:
        if result == "ok":
            self._status_label.setText("Autofilled ✓")
        elif result == "watching":
            self._status_label.setText("Waiting for login form...")
        elif isinstance(result, str) and result.startswith("error:"):
            self._status_label.setText(f"JS error: {result[6:]}")
        else:
            self._status_label.setText("Autofill: could not find login fields")

    # ------------------------------------------------------------------
    # URL bar / load status
    # ------------------------------------------------------------------

    def _on_url_changed(self, url) -> None:
        self._url_bar.setText(url.toString())
        self._back_btn.setEnabled(self._web_view.history().canGoBack())
        self._fwd_btn.setEnabled(self._web_view.history().canGoForward())

        url_str = url.toString()
        lower = url_str.lower()
        if any(kw in lower for kw in [".pdf", "/filesystem/", "/document", "/export"]):
            if not self._download_triggered:
                self._download_triggered = True
                self._status_label.setText(f"Downloading: {Path(url.path()).name}")
                self._web_view.page().download(url)
                if self._return_url:
                    QTimer.singleShot(300, lambda: self._web_view.setUrl(self._return_url))
        else:
            self._download_triggered = False
            self._return_url = url_str

    def _on_load_started(self) -> None:
        self._status_label.setText("Loading...")

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def _zoom_in(self) -> None:
        self._zoom_factor = min(self._zoom_factor + 0.1, 3.0)
        self._apply_zoom()

    def _zoom_out(self) -> None:
        self._zoom_factor = max(self._zoom_factor - 0.1, 0.2)
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        self._web_view.setZoomFactor(self._zoom_factor)
        self._zoom_label.setText(f"{int(self._zoom_factor * 100)}%")

    # ------------------------------------------------------------------
    # PDF download handling
    # ------------------------------------------------------------------

    def _on_download_requested(self, download: QWebEngineDownloadRequest) -> None:
        if not _coa_parser_tab.INPUT_DIR.exists():
            _coa_parser_tab.INPUT_DIR.mkdir(parents=True, exist_ok=True)

        suggested = download.suggestedFileName()
        if not suggested:
            suggested = Path(download.url().path()).name or "download.pdf"

        dest = _coa_parser_tab.INPUT_DIR / suggested
        dest = self._unique_path(dest)

        download.setDownloadDirectory(str(_coa_parser_tab.INPUT_DIR))
        download.setDownloadFileName(suggested)
        download.accept()

        self._current_download = download
        download.receivedBytesChanged.connect(self._on_download_progress)
        download.totalBytesChanged.connect(self._on_download_progress)
        download.isFinishedChanged.connect(lambda: self._on_download_finished(download, str(dest)))

        self._download_bar.setVisible(True)
        self._download_bar.setMaximum(100)
        self._download_bar.setValue(0)
        self._download_bar.setFormat(f"Downloading {suggested}  0%")
        self._status_label.setText(f"Downloading {suggested}...")

    def _on_download_progress(self) -> None:
        d = self._current_download
        if d is None:
            return
        received = d.receivedBytes()
        total = d.totalBytes()
        if total > 0:
            pct = int(received / total * 100)
            self._download_bar.setValue(pct)
            name = d.suggestedFileName() or "PDF"
            self._download_bar.setFormat(f"Downloading {name}  {pct}%")

    def _on_download_finished(self, download: QWebEngineDownloadRequest, dest: str) -> None:
        if self._detect_cancelled:
            self._current_download = None
            return
        self._download_bar.setVisible(False)
        if download.isFinished() and download.state() == QWebEngineDownloadRequest.DownloadCompleted:
            self._status_label.setText(f"Saved: {Path(dest).name}")
            self.pdf_downloaded.emit(dest)
            self._detect_completed += 1
        else:
            self._status_label.setText("Download failed or cancelled")

        self._current_download = None
        if self._detect_active:
            self._advance_detect()

    # ------------------------------------------------------------------
    # Watch mode
    # ------------------------------------------------------------------

    def _on_watch_toggled(self, active: bool) -> None:
        if active:
            self._watch_btn.setText("Stop Watch")
            self._status_label.setText("Watch active — expand a row")
            self._web_view.page().runJavaScript(_WATCHER_JS, self._on_watch_result)
        else:
            self._watch_btn.setText("Watch")
            self._status_label.setText("Watch stopped")
            self._web_view.page().runJavaScript(_WATCHER_STOP_JS)

    def _on_watch_result(self, raw: object) -> None:
        if raw == "already active":
            self._status_label.setText("Watch already active")
        elif raw == "watching":
            self._status_label.setText("Watch active — expand a row to auto-download")

    # ------------------------------------------------------------------
    # Recipe recording
    # ------------------------------------------------------------------

    def _on_record_toggled(self, active: bool) -> None:
        if active:
            self._recording_steps = []
            self._record_btn.setText("Stop Recipe")
            self._record_btn.setStyleSheet("background: #e74c3c; color: #fff;")
            self._add_step_btn.setVisible(True)
            self._status_label.setText("Recording: click 'Add Step' on each page, then 'Stop Recipe'")
        else:
            self._record_btn.setText("Record Recipe")
            self._record_btn.setStyleSheet("")
            self._add_step_btn.setVisible(False)
            self._capture_cleanup()
            if self._recording_steps:
                self._finish_recipe()
            else:
                self._status_label.setText("Recording cancelled")

    def _capture_next_step(self) -> None:
        self._add_step_btn.setEnabled(False)
        self._status_label.setText(
            f"Step {len(self._recording_steps) + 1}: click the element on the page..."
        )
        self._capture_timeout = time.monotonic() + 30
        self._capture_cleanup()
        QTimer.singleShot(150, lambda: self._web_view.page().runJavaScript(
            _CAPTURE_JS, self._on_capture_injected
        ))

    def _on_capture_injected(self, raw: object) -> None:
        QTimer.singleShot(300, self._poll_capture)

    def _poll_capture(self) -> None:
        if not self._record_btn.isChecked():
            self._add_step_btn.setEnabled(True)
            return
        if time.monotonic() > self._capture_timeout:
            self._status_label.setText("Capture timed out — try again")
            self._capture_cleanup()
            self._add_step_btn.setEnabled(True)
            return

        self._web_view.page().runJavaScript(_CAPTURE_POLL_JS, self._on_capture_poll)

    def _on_capture_poll(self, raw: object) -> None:
        if not self._record_btn.isChecked():
            self._add_step_btn.setEnabled(True)
            return

        if raw and isinstance(raw, str):
            try:
                data = json.loads(raw)
                self._recording_steps.append({
                    "selectors": data.get("selectors", []),
                    "text": data.get("text", ""),
                    "tag": data.get("tag", ""),
                    "urls": data.get("urls", []),
                    "href": data.get("href", ""),
                    "delay_ms": 5000,
                })
                step_num = len(self._recording_steps)
                self._status_label.setText(
                    f"Step {step_num} captured: \"{data.get('text', '')}\" — navigate to next page and Add Step"
                )
                self._add_step_btn.setEnabled(True)
                return
            except (json.JSONDecodeError, TypeError):
                pass

        QTimer.singleShot(300, self._poll_capture)

    def _finish_recipe(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Recipe Name",
            "Name this recipe (e.g. 'Flower COA', 'Concentrate COA'):",
        )
        if not ok or not name.strip():
            self._status_label.setText("Recipe discarded (no name)")
            self._recording_steps = []
            return

        batch_reply = QMessageBox.question(
            self, "Batch Mode",
            "Repeat the last step for ALL matching elements on the page?\n\n"
            "Yes = download every item in the list (~20 files)\n"
            "No = download only the first match",
            QMessageBox.Yes | QMessageBox.No,
        )

        recipes = _load_recipes()
        recipes.append({
            "name": name.strip(),
            "steps": self._recording_steps,
            "batch": batch_reply == QMessageBox.Yes,
        })
        _save_recipes(recipes)
        self._status_label.setText(
            f"Recipe '{name.strip()}' saved ({len(self._recording_steps)} steps)"
        )
        self._recording_steps = []

    def _capture_cleanup(self) -> None:
        self._web_view.page().runJavaScript(_CAPTURE_CLEANUP_JS)

    def _open_recipe_manager(self) -> None:
        RecipeManagerDialog(self).exec()

    def _dump_page_html(self) -> None:
        js = r"""
(function() {
    var info = {
        url: location.href,
        title: document.title,
        bodyHtml: document.body ? document.body.innerHTML.substring(0, 50000) : '(no body)',
        selectors: []
    };
    var recipes = null;
    try {
        var raw = localStorage.getItem('__coa_recipes');
        if (raw) recipes = JSON.parse(raw);
    } catch(e) {}
    info.recipes = recipes;
    return JSON.stringify(info);
})()
"""
        self._web_view.page().runJavaScript(js, self._on_dump_result)

    def _on_dump_result(self, raw: object) -> None:
        import datetime
        dump_dir = Path("_dumps")
        dump_dir.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = dump_dir / f"pagedump_{ts}.json"
        if raw and isinstance(raw, str):
            path.write_text(raw, encoding="utf-8")
            self._status_label.setText(f"Page dump saved to {path}")
            logger.info("Page dump saved to %s", path)
        else:
            self._status_label.setText("Page dump failed")

    # ------------------------------------------------------------------
    # Detection (runs all recipes)
    # ------------------------------------------------------------------

    def _detect_downloads(self) -> None:
        recipes = _load_recipes()
        if not recipes:
            QMessageBox.information(
                self, "No Recipes",
                "No recipes saved yet.\n\n"
                "1. Click 'Record Recipe'\n"
                "2. Navigate to the first page, click 'Add Step', then click the element\n"
                "3. Repeat for each step\n"
                "4. Click 'Stop Recipe' and give it a name"
            )
            return

        self._detect_active = True
        self._detect_cancelled = False
        self._job_queue = []
        self._detect_completed = 0

        for recipe in recipes:
            steps = recipe.get("steps", [])
            name = recipe.get("name", "?")
            batch = recipe.get("batch", False)

            for i, step in enumerate(steps):
                if batch and i > 0:
                    continue
                selectors = step.get("selectors", [])
                is_first = (i == 0)
                self._job_queue.append({
                    "label": f"[{name}] {step.get('text', '?')}",
                    "selectors": selectors,
                    "urls": step.get("urls", []),
                    "delay_ms": step.get("delay_ms", 5000),
                    "expand": batch and is_first,
                    "batch_followups": steps[1:] if (batch and is_first) else [],
                })

        self._total_jobs_initial = len(self._job_queue)
        self._job_expand_pending: list[str] = []
        self._detect_btn.setVisible(False)
        self._cancel_btn.setVisible(True)
        self._status_label.setText(f"Running {len(recipes)} recipe(s)...")
        self._download_bar.setMaximum(500)
        self._download_bar.setValue(0)
        self._download_bar.setFormat("0 jobs")
        self._download_bar.setVisible(True)
        self._process_next_job()

    def _process_next_job(self) -> None:
        if self._detect_cancelled:
            return
        if self._current_download is not None:
            return
        if not self._job_queue:
            self._finish_detect()
            return

        job = self._job_queue.pop(0)

        if job.get("expand"):
            self._expand_job(job)
        else:
            self._execute_job(job)

    def _expand_job(self, job: dict) -> None:
        if self._detect_cancelled:
            return
        selectors = job.get("selectors", [])
        sel = self._pick_best_selector(selectors) or self._pick_best_xpath(selectors)
        if not sel:
            self._execute_job(job)
            return
        if sel.startswith("//"):
            self._execute_job(job)
            return

        js = _COUNT_ALL_JS_T.format(sel=sel)
        self._status_label.setText(f"Counting matches for: {sel}")
        self._job_expand_pending = [job]
        self._web_view.page().runJavaScript(js, lambda count: self._on_count_result(count, job))

    def _on_count_result(self, count: object, job: dict) -> None:
        if self._detect_cancelled:
            return
        try:
            n = int(count) if count is not None else 0
        except (TypeError, ValueError):
            n = 0

        if n <= 1:
            self._execute_job(job)
            return

        label = job.get("label", "")
        selectors = job.get("selectors", [])
        sel = self._pick_best_selector(selectors)
        if not sel:
            self._execute_job(job)
            return
        delay_ms = job.get("delay_ms", 5000)
        urls = job.get("urls", [])
        followups = job.get("batch_followups", [])

        for idx in range(n - 1, -1, -1):
            for fu in reversed(followups):
                self._job_queue.insert(0, {
                    "label": f"{fu.get('text', '?')} ({idx + 1}/{n})",
                    "selectors": fu.get("selectors", []),
                    "urls": fu.get("urls", []),
                    "delay_ms": fu.get("delay_ms", 5000),
                })
            self._job_queue.insert(0, {
                "label": f"{label} ({idx + 1}/{n})",
                "sel_nth": (sel, idx),
                "delay_ms": delay_ms,
                "urls": urls,
            })

        self._download_bar.setMaximum(len(self._job_queue) + 1)
        self._download_bar.setFormat(f"1/{len(self._job_queue) + 1}")
        self._process_next_job()

    def _execute_job(self, job: dict) -> None:
        if self._detect_cancelled:
            return
        self._download_bar.setValue(self._download_bar.maximum() - len(self._job_queue))
        total = self._download_bar.maximum()
        done = total - len(self._job_queue)
        self._download_bar.setFormat(f"{done}/{total}")
        self._status_label.setText(job.get("label", ""))

        self._pending_urls = job.get("urls", [])

        sel_nth = job.get("sel_nth")
        if sel_nth:
            sel, idx = sel_nth
            self._pre_detect_url = self._web_view.url().toString()
            QTimer.singleShot(150, lambda: self._do_click_nth(sel, idx, job.get("delay_ms", 5000)))
        else:
            selectors = job.get("selectors", [])
            if not selectors:
                self._process_next_job()
                return
            self._execute_click(selectors, job.get("delay_ms", 5000))

    def _do_click_nth(self, sel: str, idx: int, delay_ms: int) -> None:
        if sel.startswith("//"):
            self._execute_xpath_click(sel, delay_ms)
        else:
            js = _NTH_CLICK_JS_T.format(sel=sel, n=idx)
            self._web_view.page().runJavaScript(js, self._on_click_result)

    def _execute_click(self, selectors: list[str], delay_ms: int) -> None:
        self._pre_detect_url = self._web_view.url().toString()
        self._pending_selectors = selectors
        self._pending_delay_ms = delay_ms
        self._try_selector(0)

    def _try_selector(self, idx: int) -> None:
        selectors = self._pending_selectors
        if idx >= len(selectors):
            self._try_url_fallback()
            return

        sel = selectors[idx]
        self._status_label.setText(f"Trying selector [{idx + 1}/{len(selectors)}]: {sel[:80]}")

        if sel.startswith("//"):
            self._execute_xpath_click_try(sel, idx)
        else:
            js = _CLICK_JS_T.format(sel=sel)
            QTimer.singleShot(150, lambda: self._do_click_try(js, idx))

    def _do_click_try(self, js: str, idx: int) -> None:
        self._web_view.page().runJavaScript(js, lambda ok: self._on_click_try(ok, idx))

    def _on_click_try(self, ok: object, idx: int) -> None:
        if ok is True or ok is None:
            QTimer.singleShot(3000, self._check_download_or_advance)
        else:
            logger.warning(f"Selector {idx} didn't match, trying next")
            self._status_label.setText(f"Selector {idx + 1} failed — trying next")
            self._try_selector(idx + 1)

    def _execute_xpath_click_try(self, xpath: str, idx: int) -> None:
        js = f"""
        (function() {{
            var result = document.evaluate(
                {json.dumps(xpath)}, document, null,
                XPathResult.FIRST_ORDERED_NODE_TYPE, null
            );
            var el = result.singleNodeValue;
            if (el) {{
                el.click();
                return true;
            }}
            return false;
        }})()
        """
        self._web_view.page().runJavaScript(js, lambda ok: self._on_click_try(ok, idx))

    def _try_url_fallback(self) -> None:
        if not self._pending_urls:
            logger.warning("All selectors failed and no URL fallback — skipping step")
            self._status_label.setText("No match — skipping")
            QTimer.singleShot(500, self._process_next_job)
            return

        url = self._pending_urls[0]
        current = self._web_view.url().toString()
        full_url = urljoin(current, url)

        self._status_label.setText(f"Downloading via URL: {url}")
        logger.info("URL fallback downloading: %s", full_url)
        self._web_view.page().download(QUrl(full_url))

    def _execute_xpath_click(self, xpath: str, delay_ms: int) -> None:
        self._pre_detect_url = self._web_view.url().toString()
        js = f"""
        (function() {{
            var result = document.evaluate(
                {json.dumps(xpath)}, document, null,
                XPathResult.FIRST_ORDERED_NODE_TYPE, null
            );
            var el = result.singleNodeValue;
            if (el) {{
                el.click();
                return true;
            }}
            return false;
        }})()
        """
        QTimer.singleShot(150, lambda: self._web_view.page().runJavaScript(js, self._on_click_result))

    def _on_click_result(self, ok: object) -> None:
        if ok is True or ok is None:
            QTimer.singleShot(3000, self._check_download_or_advance)
        else:
            logger.warning("Click returned false — trying URL fallback")
            self._try_url_fallback()

    def _check_download_or_advance(self) -> None:
        if self._detect_cancelled:
            return
        if self._current_download is not None:
            return
        self._process_next_job()

    def _advance_detect(self) -> None:
        self._process_next_job()

    def _finish_detect(self) -> None:
        self._detect_active = False
        self._cancel_btn.setVisible(False)
        self._detect_btn.setVisible(True)
        self._download_bar.setVisible(False)
        self._status_label.setText("Detection finished")

    def _cancel_detect(self) -> None:
        self._detect_cancelled = True
        self._detect_active = False
        self._job_queue.clear()
        if self._current_download is not None:
            try:
                self._current_download.cancel()
            except RuntimeError:
                pass
            self._current_download = None
        self._cancel_btn.setVisible(False)
        self._detect_btn.setVisible(True)
        self._download_bar.setVisible(False)
        self._status_label.setText("Cancelled")

    # ------------------------------------------------------------------
    # Selector helpers
    # ------------------------------------------------------------------

    def _pick_best_selector(self, selectors: list[str]) -> str | None:
        if not selectors:
            return None
        for s in selectors:
            if not s.startswith("//"):
                return s
        return None

    def _pick_best_xpath(self, selectors: list[str]) -> str | None:
        for s in selectors:
            if s.startswith("//"):
                return s
        return None

    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        counter = 1
        while True:
            candidate = path.with_name(f"{stem} ({counter}){suffix}")
            if not candidate.exists():
                return candidate
            counter += 1
