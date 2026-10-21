import re

with open('todo_bird_app/views/dashboard_view.py', 'r') as f:
    content = f.read()

# 1. Remove incremental layout additions
additions = [
    r'self\.layout\.addWidget\(self\.greeting_card\)',
    r'self\.layout\.addLayout\(self\.row1_grid\)',
    r'self\.layout\.addLayout\(self\.row2_grid\)',
    r'self\.cockpit_layout\.addLayout\(split_diag\)',  # Don't add split_diag to cockpit
    r'self\.layout\.addWidget\(self\.cockpit_container\)',
    r'mid_row\.addWidget\(self\.focus_next_card, 1\)',
    r'mid_row\.addWidget\(self\.workload_card, 1\)',
    r'self\.layout\.addLayout\(mid_row\)',
    r'self\.layout\.addLayout\(self\.charts_row\)',
    r'bottom_row\.addWidget\(self\.timeline_card, 1\)',
    r'bottom_row\.addWidget\(self\.projects_card, 1\)',
    r'self\.layout\.addLayout\(bottom_row\)',
    r'self\.layout\.addWidget\(quick_nav_card\)'
]

for p in additions:
    content = re.sub(r'^[ \t]*' + p + r'\n?', '', content, flags=re.MULTILINE)

# 2. Insert master assembly block before scroll.setWidget(self.content_widget)
master_assembly = """
        # --- MASTER LAYOUT ASSEMBLY ---
        self.layout.addWidget(self.greeting_card)
        
        # ROW 1: Executive Status Cards (Row1 + Row2 combined)
        self.layout.addLayout(self.row1_grid)
        self.layout.addLayout(self.row2_grid)
        
        # ROW 2: Schedule / Forecast + Execution
        self.layout.addWidget(self.cockpit_container)
        
        # ROW 3: Charts
        self.layout.addLayout(self.charts_row)
        
        # ROW 4: Risk / Blockers + Action Center
        row4 = QHBoxLayout()
        row4.setSpacing(14)
        row4.addWidget(self.risk_quality_card, 1)
        row4.addWidget(self.attention_card, 1)
        row4.addWidget(self.focus_next_card, 1)
        self.layout.addLayout(row4)
        
        # ROW 5: Details table / WBS summary / Workload
        row5 = QHBoxLayout()
        row5.setSpacing(14)
        row5.addWidget(self.workload_card, 1)
        row5.addWidget(self.timeline_card, 1)
        row5.addWidget(self.projects_card, 1)
        self.layout.addLayout(row5)
        
        # Quick Nav
        self.layout.addWidget(quick_nav_card)
        self.layout.addStretch(1)

        scroll.setWidget(self.content_widget)
"""
content = content.replace("        scroll.setWidget(self.content_widget)", master_assembly)

with open('todo_bird_app/views/dashboard_view.py', 'w') as f:
    f.write(content)

