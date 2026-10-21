"""
GNOME Adwaita & Yaru Design Tokens for TODO BIRD
"""

DARK_PALETTE = {
    "bg_root": "#1E1E2E",          # Main window background (Dark Catppuccin / Adwaita Dark)
    "bg_sidebar": "#181825",       # Sidebar background
    "bg_card": "#242538",          # Elevated card background
    "bg_card_hover": "#2F3149",    # Card hover
    "bg_header": "#181825",        # Headerbar background
    "bg_input": "#1E1E2E",         # Input fields background
    "text_primary": "#F3F4F6",     # High contrast primary text
    "text_secondary": "#9CA3AF",   # Muted text
    "text_muted": "#8792A6",
    "text_disabled": "#8792A6",
    "heading_primary": "#FFFFFF",
    "heading_secondary": "#DCE4F2",
    "text_on_accent": "#FFFFFF",
    "text_on_danger": "#FFFFFF",
    "text_on_warning": "#111827",
    "text_on_success": "#FFFFFF",
    "link": "#E95420",
    "link_hover": "#F97316",
    "placeholder_text": "#8792A6",
    "table_header_text": "#F3F4F6",
    "section_header_text": "#FFFFFF",
    "sidebar_text": "#9CA3AF",
    "sidebar_selected_text": "#FFFFFF",
    "border": "#374151",           # Subtle border
    "accent_default": "#E95420",   # Ubuntu Orange
    "accent_blue": "#3584E4",      # Adwaita Blue
    "accent_green": "#047857",     # Accessible Emerald
    "accent_purple": "#8B5CF6",    # Purple
    "accent_red": "#DC2626",       # Urgent Red
    "danger_hover": "#B91C1C",
}

LIGHT_PALETTE = {
    "bg_root": "#F6F6F9",          # Main window background
    "bg_sidebar": "#EBECEF",       # Sidebar background
    "bg_card": "#FFFFFF",          # Elevated card background
    "bg_card_hover": "#F0F1F5",    # Card hover
    "bg_header": "#EBECEF",        # Headerbar background
    "bg_input": "#FFFFFF",         # Input fields background
    "text_primary": "#1F2937",     # High contrast dark text
    "text_secondary": "#6B7280",   # Muted text
    "text_muted": "#64748B",
    "text_disabled": "#64748B",
    "heading_primary": "#0F172A",
    "heading_secondary": "#334155",
    "text_on_accent": "#FFFFFF",
    "text_on_danger": "#FFFFFF",
    "text_on_warning": "#111827",
    "text_on_success": "#FFFFFF",
    "link": "#E95420",
    "link_hover": "#C2410C",
    "placeholder_text": "#64748B",
    "table_header_text": "#0F172A",
    "section_header_text": "#0F172A",
    "sidebar_text": "#475569",
    "sidebar_selected_text": "#FFFFFF",
    "border": "#CBD5E1",           # Crisp high-contrast border
    "accent_default": "#E95420",   # Ubuntu Orange
    "accent_blue": "#3584E4",      # Adwaita Blue
    "accent_green": "#047857",     # Accessible Emerald
    "accent_purple": "#8B5CF6",    # Purple
    "accent_red": "#DC2626",       # Urgent Red
    "danger_hover": "#B91C1C",
}

OLED_PALETTE = {
    "bg_root": "#000000",          # Pure pitch black for OLED panels
    "bg_sidebar": "#000000",       # Pitch black sidebar
    "bg_card": "#090A0F",          # Ultra-deep dark card background
    "bg_card_hover": "#13151F",    # Deep charcoal hover
    "bg_header": "#050508",        # Pitch black header
    "bg_input": "#090A0F",         # Deep input background
    "text_primary": "#FFFFFF",     # Pure white high-contrast text
    "text_secondary": "#A0A8B8",   # Soft zinc-slate secondary text
    "text_muted": "#737B8C",
    "text_disabled": "#505666",
    "heading_primary": "#FFFFFF",
    "heading_secondary": "#E0E6F0",
    "text_on_accent": "#FFFFFF",
    "text_on_danger": "#FFFFFF",
    "text_on_warning": "#000000",
    "text_on_success": "#FFFFFF",
    "link": "#FF5D22",
    "link_hover": "#FF7A45",
    "placeholder_text": "#737B8C",
    "table_header_text": "#FFFFFF",
    "section_header_text": "#FFFFFF",
    "sidebar_text": "#A0A8B8",
    "sidebar_selected_text": "#FFFFFF",
    "border": "#282D3E",           # Subtle deep border
    "accent_default": "#FF5D22",   # Vivid OLED orange
    "accent_blue": "#3B82F6",      # Vivid Blue
    "accent_green": "#10B981",     # Vivid Emerald
    "accent_purple": "#A855F7",    # Vivid Purple
    "accent_red": "#EF4444",       # Vivid Red
    "danger_hover": "#DC2626",
}

WARM_PAPER_PALETTE = {
    "bg_root": "#F8F4EC",          # Warm cream paper background
    "bg_sidebar": "#F2EDE0",       # Parchment sidebar
    "bg_card": "#FCFBF7",          # Warm ivory elevated card
    "bg_card_hover": "#F0EAE0",    # Card hover
    "bg_header": "#F2EDE0",        # Warm parchment header
    "bg_input": "#FCFBF7",         # Input fields
    "text_primary": "#2C241D",     # Deep espresso text (low blue light, calm)
    "text_secondary": "#64584C",   # Warm walnut secondary text
    "text_muted": "#8E8172",       # Soft taupe muted text
    "text_disabled": "#B0A495",
    "heading_primary": "#1F1710",  # Dark roast coffee heading
    "heading_secondary": "#4B3E32",
    "text_on_accent": "#FFFFFF",
    "text_on_danger": "#FFFFFF",
    "text_on_warning": "#1F1710",
    "text_on_success": "#FFFFFF",
    "link": "#C85A32",             # Warm terracotta
    "link_hover": "#9E3C1B",
    "placeholder_text": "#8E8172",
    "table_header_text": "#1F1710",
    "section_header_text": "#1F1710",
    "sidebar_text": "#64584C",
    "sidebar_selected_text": "#1F1710",
    "border": "#D5CBB8",           # Warm linen border
    "accent_default": "#C85A32",   # Warm terracotta accent
    "accent_blue": "#3B7BA8",      # Slate blue
    "accent_green": "#15803D",     # Forest sage green
    "accent_purple": "#7E57C2",    # Muted lavender purple
    "accent_red": "#B91C1C",       # Crimson
    "danger_hover": "#991B1B",
}

NORD_PALETTE = {
    "bg_root": "#242933",          # Polar Night darkest base
    "bg_sidebar": "#1E222A",       # Polar Night deep sidebar
    "bg_card": "#2E3440",          # Polar Night surface 1
    "bg_card_hover": "#3B4252",    # Polar Night hover
    "bg_header": "#1E222A",        # Polar Night header
    "bg_input": "#2E3440",         # Polar Night input
    "text_primary": "#ECEFF4",     # Snow Storm crisp white text
    "text_secondary": "#D8DEE9",   # Snow Storm secondary text
    "text_muted": "#93A1B8",       # Frost muted text
    "text_disabled": "#697790",
    "heading_primary": "#FFFFFF",  # Snow Storm bright heading
    "heading_secondary": "#88C0D0",# Frost cyan heading
    "text_on_accent": "#2E3440",   # High contrast dark text on frost cyan
    "text_on_danger": "#FFFFFF",
    "text_on_warning": "#2E3440",
    "text_on_success": "#FFFFFF",
    "link": "#88C0D0",             # Frost Cyan link
    "link_hover": "#81A1C1",       # Frost Blue link hover
    "placeholder_text": "#93A1B8",
    "table_header_text": "#ECEFF4",
    "section_header_text": "#FFFFFF",
    "sidebar_text": "#D8DEE9",
    "sidebar_selected_text": "#88C0D0",
    "border": "#4C566A",           # Polar Night high-contrast border
    "accent_default": "#88C0D0",   # Frost Cyan
    "accent_blue": "#81A1C1",      # Frost Blue
    "accent_green": "#A3BE8C",     # Aurora Green
    "accent_purple": "#B48EAD",    # Aurora Purple
    "accent_red": "#BF616A",       # Aurora Red
    "danger_hover": "#A64D56",
}

THEME_PALETTES = {
    "dark": DARK_PALETTE,
    "light": LIGHT_PALETTE,
    "oled": OLED_PALETTE,
    "warm_paper": WARM_PAPER_PALETTE,
    "nord": NORD_PALETTE,
}


# ---------------------------------------------------------------------------
# Dashboard Visual Polish — Card System / Spacing / Typography / Semantic
# (Mission: DASHBOARD VISUAL POLISH, visual-only. The DARK_PALETTE and
# LIGHT_PALETTE dicts above are untouched; the module-level constants below
# give dashboard views/widgets a single source of truth for spacing scale,
# card geometry, type hierarchy and the restrained semantic color set.
# Nothing here performs math, I/O, or signal work — pure static data.)
# ---------------------------------------------------------------------------

# Spacing scale in pixels (mission scale: 4/8/12/16/20/24/32/40).
SPACING_SCALE = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
    "2xl": 24,
    "3xl": 32,
    "4xl": 40,
}

# Card geometry: restrained radii + padding steps drawn from SPACING_SCALE.
CARD_RADIUS = {
    "sm": 8,
    "md": 12,
}

CARD_PADDING = {
    "compact": 12,
    "comfortable": 16,
    "spacious": 24,
}

# Card section gaps (horizontal/vertical rhythm between dashboard cards).
CARD_GAP = {
    "tight": 8,
    "normal": 12,
    "loose": 16,
}

# Typography hierarchy: point size + weight per role.
# Sizes mirror ui.design_tokens.DesignTokens (11/13/15/18/24).
TYPOGRAPHY_HIERARCHY = {
    "display": {"size": 24, "weight": 700},
    "heading": {"size": 18, "weight": 700},
    "title": {"size": 15, "weight": 600},
    "body": {"size": 13, "weight": 400},
    "caption": {"size": 11, "weight": 500},
    "kpi_value": {"size": 24, "weight": 700},
    "kpi_label": {"size": 11, "weight": 500},
    "section_header": {"size": 13, "weight": 700},
}

# Semantic relative typography scale (delta_pt relative to user base font)
SEMANTIC_TYPOGRAPHY_ROLES = {
    "display": {"delta_pt": 14, "weight": "bold", "approx_pt": 24},
    "page_title": {"delta_pt": 8, "weight": "bold", "approx_pt": 18},
    "section_title": {"delta_pt": 4, "weight": "semibold", "approx_pt": 15},
    "card_title": {"delta_pt": 2, "weight": "semibold", "approx_pt": 13},
    "body": {"delta_pt": 0, "weight": "normal", "approx_pt": 11},
    "secondary_body": {"delta_pt": 0, "weight": "normal", "approx_pt": 11},
    "metadata": {"delta_pt": -1, "weight": "medium", "approx_pt": 10},
    "caption": {"delta_pt": -2, "weight": "medium", "approx_pt": 9},
}

# Restrained semantic colors for dashboard visuals (status + accents only).
# Reuses the canonical palette hues: Ubuntu Orange accent, Adwaita Blue,
# accessible Emerald green, urgent Red.
SEMANTIC_COLORS = {
    "accent": "#E95420",
    "blue": "#3584E4",
    "green": "#047857",
    "red": "#DC2626",
}

# Dashboard card defaults: radius/padding/gap composed from the scales above.
DASHBOARD_CARD_DEFAULTS = {
    "radius": 12,
    "padding": 16,
    "gap": 12,
}

