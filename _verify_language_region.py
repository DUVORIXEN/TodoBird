#!/usr/bin/env python3
"""Verify the language & region feature end-to-end, offscreen."""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("TODO_BIRD_SYNC_APPEARANCE", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))


from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

app = QApplication(sys.argv)

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.services.language_service import LanguageService

db = DatabaseManager(":memory:")
sm = SettingsManager(db, config_dir="/tmp/tb_lang_cfg")
tc = ThemeController(sm)
app.theme_controller = tc

# ------------------------------------------------------------------
# 1. LanguageService core semantics
# ------------------------------------------------------------------
svc = LanguageService.instance(sm)
code = svc.initialize()
check("Default language is English", code == "en", code)
check("English passthrough is exact", svc.t("Dashboard") == "Dashboard")

svc.set_language("es")
check("Spanish nav translation", svc.t("Dashboard") == "Panel", svc.t("Dashboard"))
check("Unknown string falls back to English", svc.t("Not In Any Pack 123") == "Not In Any Pack 123")
check("Coverage is complete for es", abs(svc.coverage() - 1.0) < 1e-9, f"{svc.coverage():.2f}")
check("Setting persisted", str(sm.get("ui_language")) == "es", str(sm.get("ui_language")))

svc.set_language("ar")
check("Arabic flagged RTL", LanguageService.is_rtl("ar"))
check("App layout direction switched to RTL",
      app.layoutDirection() == Qt.RightToLeft, str(app.layoutDirection()))
check("Arabic translation", svc.t("Settings") == "الإعدادات", svc.t("Settings"))

svc.set_language("en")
check("Layout returns to LTR", app.layoutDirection() == Qt.LeftToRight)

# every pack covers every reference string
from todo_bird_app.services.language_service import REFERENCE_STRINGS
all_covered = True
for lc, *_ in LanguageService.available_languages():
    if lc == "en":
        continue
    pack = svc._load_pack(lc)
    missing = [s for s in REFERENCE_STRINGS if s not in pack]
    if missing:
        all_covered = False
        print("  missing in", lc, ":", missing[:4])
check("All 10 packs fully cover the reference set", all_covered)
svc.set_language("en")

# ------------------------------------------------------------------
# 2. Region service
# ------------------------------------------------------------------
from todo_bird_app.services.region_service import RegionService

countries = RegionService.available_countries()
check("Country catalog loaded from system tzdb", len(countries) >= 200, f"{len(countries)} countries")
check("Country list includes India", any(c == "IN" for c, _n, _f in countries))
profile_in = RegionService.profile_for("IN")
profile_sa = RegionService.profile_for("SA")
check("India profile: Mon-Fri, 24h, DMY",
      list(profile_in.working_days) == [0, 1, 2, 3, 4] and profile_in.use_24h and profile_in.date_style == "dmy")
check("Saudi profile: Sun-Thu work week",
      list(profile_sa.working_days) == [6, 0, 1, 2, 3], str(list(profile_sa.working_days)))
check("Unknown country falls back to defaults",
      RegionService.profile_for("ZZ").date_style == "dmy")

applied = RegionService.apply_region_defaults(sm, "SA")
week = set(WorkingWeekCheck := __import__("todo_bird_app.services.working_week", fromlist=["WorkingWeekService"]).WorkingWeekService(sm).get_working_weekdays())
check("Region defaults apply working week (Saudi Sun-Thu)",
      week == {6, 0, 1, 2, 3}, str(sorted(week)))
check("Region defaults apply 12/24h", bool(sm.get("region_use_24h")) is True)

# ------------------------------------------------------------------
# 3. Full app chrome: language switch retranslates live
# ------------------------------------------------------------------
from todo_bird_app.views import main_window as mw_module

mw_module.MainWindow._evaluate_startup_greeting = lambda self: None
win = mw_module.MainWindow(db, sm, tc)
win.show()
app.processEvents()

hb = win.headerbar
check("Header shows language button", hasattr(hb, "language_btn") and hb.language_btn.isVisible(),
      hb.language_btn.text())
check("English chrome at startup", hb.add_btn.text().endswith("New Task"), hb.add_btn.text())

# Simulate the user picking Hindi from the header-bar menu
hb.language_selected.emit("hi")
app.processEvents()

check("Header button shows HI", "HI" in hb.language_btn.text(), hb.language_btn.text())
check("New Task translated to Hindi", hb.add_btn.text() == "+  नया कार्य", hb.add_btn.text())
check("World Clock translated to Hindi", "विश्व घड़ी" in hb.clock_btn.text(), hb.clock_btn.text())

sidebar_titles = {k: item.label_text for k, item in win.sidebar._all_item_widgets.get("vertical", {}).items()}
check("Sidebar translated to Hindi",
      sidebar_titles.get("dashboard") == "डैशबोर्ड" and sidebar_titles.get("today") == "आज",
      str({k: sidebar_titles.get(k) for k in ("dashboard", "today", "settings")}))

settings_view = win.settings_view
tab_texts = [settings_view.settings_tabs.tabText(i) for i in range(settings_view.settings_tabs.count())]
check("Settings tabs translated to Hindi", tab_texts[6] == "डैशबोर्ड", str(tab_texts))

menu_labels = [a.text() for a in win.menuBar().actions()]
check("Menu bar translated to Hindi", any("फ़ाइल" in m for m in menu_labels), str(menu_labels))

# Switch to Spanish, then back to English via the same path
hb.language_selected.emit("es")
app.processEvents()
check("Spanish applied live", hb.add_btn.text() == "+  Nueva tarea", hb.add_btn.text())
hb.language_selected.emit("en")
app.processEvents()
check("English restored live", hb.add_btn.text().endswith("New Task"), hb.add_btn.text())
check("Language persisted through switches", str(sm.get("ui_language")) == "en")

# ------------------------------------------------------------------
# 4. Startup in a non-English language (persisted before launch)
# ------------------------------------------------------------------
sm.set("ui_language", "te")
win2 = mw_module.MainWindow(db, sm, tc)
win2.show()
app.processEvents()
check("Startup renders Telugu chrome", "కొత్త పని" in win2.headerbar.add_btn.text(),
      win2.headerbar.add_btn.text())
sb2 = {k: i.label_text for k, i in win2.sidebar._all_item_widgets.get("vertical", {}).items()}
check("Startup renders Telugu sidebar", sb2.get("settings") == "సెట్టింగ్‌లు", sb2.get("settings", ""))
sm.set("ui_language", "en")
win2.close()
win.close()

# ------------------------------------------------------------------
# 5. Add-world-clock dialog preselects the region country
# ------------------------------------------------------------------
from todo_bird_app.widgets.add_world_clock_dialog import AddWorldClockDialog

sm.set("region_country", "JP")
dlg = AddWorldClockDialog(is_dark=True, accent_color="#3584E4", region_country="JP")
check("Dialog pre-seeds region country search", dlg.search_edit.text() == "Japan",
      dlg.search_edit.text())

print()
failed = [r for r in results if not r[1]]
print(f"{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
