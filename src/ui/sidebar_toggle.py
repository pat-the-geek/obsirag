import streamlit as st


def render_sidebar_toggle_button(label: str = "☰ Menu", variant: str = "floating") -> None:
    if variant == "inline":
        button_css = """
        .obsirag-open-sidebar-btn {
            float: right;
            margin-top: 8px;
            margin-bottom: 8px;
        }
        .obsirag-open-sidebar-btn.visible {
            display: inline-block;
        }
        """
    else:
        button_css = """
        .obsirag-open-sidebar-btn {
            position: fixed;
            top: 16px;
            left: 16px;
            z-index: 9999;
        }
        .obsirag-open-sidebar-btn.visible {
            display: block;
        }
        """

    st.markdown(
        f"""
        <style>
        .obsirag-open-sidebar-btn {{
            display: none;
            background: #005fcc;
            color: #fff;
            border: none;
            border-radius: 6px;
            padding: 7px 16px;
            font-size: 1em;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            cursor: pointer;
            opacity: 0.92;
            transition: opacity 0.2s;
        }}
        .obsirag-open-sidebar-btn:hover {{ opacity: 1; background: #0074e0; }}
        {button_css}
        </style>
        <button id="obsiragOpenSidebarBtn" class="obsirag-open-sidebar-btn" onclick="window.obsiragOpenSidebar && window.obsiragOpenSidebar()">{label}</button>
        <script>
        (() => {{
            const rootDocument = window.parent?.document || document;

            function getSidebar() {{
                return rootDocument.querySelector('[data-testid="stSidebar"]')
                    || rootDocument.querySelector('section.stSidebar');
            }}

            function getExpandButton() {{
                return rootDocument.querySelector('[data-testid="stExpandSidebarButton"]')
                    || rootDocument.querySelector('[data-testid="collapsedControl"]')
                    || rootDocument.querySelector('button[aria-label="Expand sidebar"]');
            }}

            function syncVisibility() {{
                const sidebar = getSidebar();
                const openButton = document.getElementById('obsiragOpenSidebarBtn');
                if (!openButton) return;
                const isCollapsed = !sidebar
                    || sidebar.getAttribute('aria-expanded') === 'false'
                    || sidebar.offsetWidth < 60;
                openButton.classList.toggle('visible', isCollapsed);
            }}

            window.obsiragOpenSidebar = () => {{
                const expandButton = getExpandButton();
                if (expandButton) {{
                    expandButton.click();
                    window.setTimeout(syncVisibility, 150);
                    window.setTimeout(syncVisibility, 500);
                    return;
                }}

                const sidebar = getSidebar();
                if (sidebar) {{
                    sidebar.style.display = 'block';
                    sidebar.style.visibility = 'visible';
                    sidebar.style.transform = 'translateX(0)';
                    sidebar.setAttribute('aria-expanded', 'true');
                }}
                syncVisibility();
            }};

            syncVisibility();
            window.setTimeout(syncVisibility, 300);
            if (!window.__obsiragSidebarToggleInterval) {{
                window.__obsiragSidebarToggleInterval = window.setInterval(syncVisibility, 1200);
            }}
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )