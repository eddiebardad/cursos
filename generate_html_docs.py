import os
import markdown

# Create output directory
os.makedirs('docs/html', exist_ok=True)

# Read markdown content
with open('docs/user_guide.md', 'r', encoding='utf-8') as f:
    md_content = f.read()

# Setup markdown with TOC extension
md = markdown.Markdown(extensions=['fenced_code', 'tables', 'codehilite', 'toc'])

# We must remove [TOC] from the body so it doesn't render twice
md_content = md_content.replace('[TOC]', '')

# Convert to HTML
html_body = md.convert(md_content)
toc_html = getattr(md, 'toc', '')

# HTML Template with Wiki-style CSS (Sidebar + Main Content)
html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Course Scraper Wiki</title>
    <style>
        :root {{
            --bg-color: #ffffff;
            --text-color: #333333;
            --link-color: #0366d6;
            --sidebar-bg: #f6f8fa;
            --border-color: #e1e4e8;
            --code-bg: #f6f8fa;
            --code-text: #24292e;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            background-color: var(--bg-color);
            margin: 0;
            padding: 0;
            display: flex;
            min-height: 100vh;
        }}

        /* Wiki Sidebar Navigation */
        .sidebar {{
            width: 300px;
            background-color: var(--sidebar-bg);
            border-right: 1px solid var(--border-color);
            padding: 2rem 1.5rem;
            box-sizing: border-box;
            position: sticky;
            top: 0;
            height: 100vh;
            overflow-y: auto;
        }}
        
        .sidebar h2 {{
            font-size: 1.2rem;
            margin-top: 0;
            margin-bottom: 1rem;
            color: #24292e;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border-color);
        }}

        .sidebar ul {{
            list-style: none;
            padding-left: 0;
            margin: 0;
        }}

        .sidebar ul li {{
            margin-bottom: 0.5rem;
        }}
        
        .sidebar ul ul {{
            padding-left: 1.2rem;
            margin-top: 0.25rem;
            font-size: 0.9em;
        }}

        .sidebar a {{
            color: var(--link-color);
            text-decoration: none;
            display: block;
            padding: 0.25rem 0;
        }}

        .sidebar a:hover {{
            text-decoration: underline;
        }}

        /* Main Content */
        .main-content {{
            flex: 1;
            padding: 3rem 4rem;
            max-width: 900px;
            box-sizing: border-box;
        }}

        h1, h2, h3, h4, h5, h6 {{
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
            line-height: 1.25;
        }}

        h1 {{ font-size: 2em; padding-bottom: 0.3em; border-bottom: 1px solid var(--border-color); }}
        h2 {{ font-size: 1.5em; padding-bottom: 0.3em; border-bottom: 1px solid var(--border-color); }}
        h3 {{ font-size: 1.25em; }}

        a {{ color: var(--link-color); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}

        pre {{
            background-color: var(--code-bg);
            color: var(--code-text);
            padding: 16px;
            border-radius: 6px;
            overflow-x: auto;
            font-size: 85%;
            line-height: 1.45;
        }}
        
        code {{
            font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
            background-color: rgba(27,31,35,0.05);
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-size: 85%;
        }}
        
        pre code {{
            background-color: transparent;
            padding: 0;
        }}

        hr {{
            height: 0.25em;
            padding: 0;
            margin: 24px 0;
            background-color: var(--border-color);
            border: 0;
        }}
        
        table {{
            border-spacing: 0;
            border-collapse: collapse;
            margin-top: 0;
            margin-bottom: 16px;
            width: 100%;
        }}
        
        th, td {{
            padding: 6px 13px;
            border: 1px solid #dfe2e5;
        }}
        
        th {{
            font-weight: 600;
            background-color: #f6f8fa;
        }}
        
        @media (max-width: 768px) {{
            body {{ flex-direction: column; }}
            .sidebar {{ width: 100%; height: auto; position: static; border-right: none; border-bottom: 1px solid var(--border-color); }}
            .main-content {{ padding: 2rem; }}
        }}
    </style>
</head>
<body>
    <aside class="sidebar">
        <h2>Navigation</h2>
        {toc_html}
    </aside>
    <main class="main-content">
        {html_body}
    </main>
</body>
</html>
"""

# Write to docs/html/index.html
with open('docs/html/index.html', 'w', encoding='utf-8') as f:
    f.write(html_template)

print("Wiki-style HTML User Guide generated successfully at docs/html/index.html!")
