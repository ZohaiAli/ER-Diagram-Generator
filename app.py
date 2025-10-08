from flask import Flask, request, send_from_directory
import sqlite3
from graphviz import Digraph
import os, time

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
STATIC_FOLDER = "static"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)


def analyze_schema(db_path):
    """Detect tables and possible many-to-many tables"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    table_names = [t[0] for t in tables]

    # Detect possible many-to-many (tables having >=2 foreign keys)
    many_to_many = []
    for name, sql in tables:
        if sql and sql.upper().count("FOREIGN KEY") >= 2:
            many_to_many.append(name)

    conn.close()
    return table_names, many_to_many


def generate_custom_er(db_path, output_path, weak_entities):
    """Generate ER diagram with solid lines and selected weak entities"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    dot = Digraph('ER_Diagram', format='png')
    dot.attr(rankdir='LR', bgcolor='white', splines='ortho')

    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()

        # Create table node
        label = f"<<TABLE BORDER='1' CELLBORDER='1' CELLSPACING='0'>"
        label += f"<TR><TD COLSPAN='2' BGCOLOR='#d9edf7'><B>{table}</B></TD></TR>"
        for col in columns:
            label += f"<TR><TD ALIGN='LEFT'>{col[1]}</TD><TD ALIGN='LEFT'>{col[2]}</TD></TR>"
        label += "</TABLE>>"

        # User-selected weak entities get double border
        shape = 'doubleoctagon' if table in weak_entities else 'rect'
        dot.node(table, label=label, shape=shape, style='filled', fillcolor='white')

    # Relationships
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
    for name, sql in cursor.fetchall():
        if sql and "FOREIGN KEY" in sql:
            for line in sql.splitlines():
                if "FOREIGN KEY" in line:
                    try:
                        parts = line.strip().split("REFERENCES")
                        fk_field = parts[0].split("(")[1].split(")")[0]
                        ref_table = parts[1].split("(")[0].strip()
                        dot.edge(name, ref_table, label=fk_field, color="black", style="solid")
                    except Exception as e:
                        print("Error parsing FK:", line, e)

    conn.close()
    dot.render(output_path, cleanup=True)
    return output_path + ".png"


@app.route('/', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST' and 'file' in request.files:
        # Step 1: Upload database
        file = request.files['file']
        filename = file.filename
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(upload_path)

        # Step 2: Get table list + many-to-many analysis
        tables, many_to_many = analyze_schema(upload_path)

        # Show selection form
        table_options = "".join(
            [f"<label><input type='checkbox' name='weak' value='{t}'> {t}</label><br>"
             for t in tables]
        )

        return f"""
        <html>
        <head>
            <title>Select Weak Entities</title>
            <style>
                body {{ font-family: Arial; text-align: center; padding: 40px; background: #f8f9fa; }}
                form {{ background: white; padding: 30px; display: inline-block; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }}
                h2 {{ color: #333; }}
                button {{ background: #007BFF; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; }}
                button:hover {{ background: #0056b3; }}
            </style>
        </head>
        <body>
            <h2>🩸 Select Weak Entities</h2>
            <form method="POST">
                <input type="hidden" name="db_path" value="{upload_path}">
                {table_options}
                <br><br>
                <button type="submit">Generate ER Diagram</button>
            </form>
        </body>
        </html>
        """

    elif request.method == 'POST' and 'db_path' in request.form:
        # Step 3: Generate ER Diagram based on user selection
        db_path = request.form['db_path']
        weak_entities = request.form.getlist('weak')

        timestamp = str(int(time.time()))
        output_file = f"diagram_{timestamp}"
        output_path = os.path.join(STATIC_FOLDER, output_file)

        # Analyze for many-to-many again (for chart display)
        _, many_to_many = analyze_schema(db_path)
        image_path = generate_custom_er(db_path, output_path, weak_entities)

        weak_html = "".join([f"<li>{w}</li>" for w in weak_entities]) or "<li>None selected</li>"
        m2m_html = "".join([f"<li>{m}</li>" for m in many_to_many]) or "<li>None detected</li>"

        return f"""
        <html>
        <head>
            <title>ER Diagram Generated</title>
            <style>
                body {{ font-family: Arial; text-align: center; padding: 40px; background: #f7f8fa; }}
                h2 {{ color: #333; }}
                .diagram-container {{
                    margin-top: 20px; background: white; border-radius: 12px;
                    box-shadow: 0 4px 10px rgba(0,0,0,0.1); padding: 20px; display: inline-block;
                }}
                .info {{
                    margin-top: 30px; text-align: left; display: inline-block;
                    background: #fff; padding: 20px; border-radius: 12px;
                    box-shadow: 0 4px 10px rgba(0,0,0,0.1); width: 60%;
                }}
                h3 {{ color: #007BFF; }}
                ul {{ line-height: 1.8; }}
                img {{ max-width: 100%; height: auto; border-radius: 8px; }}
                a.button {{ display: inline-block; padding: 10px 20px; background: #007BFF; color: white; border-radius: 6px; text-decoration: none; margin-top: 20px; }}
                a.button:hover {{ background: #0056b3; }}
            </style>
        </head>
        <body>
            <h2>✅ ER Diagram Generated Successfully!</h2>
            <div class="diagram-container">
                <img src="/{image_path}" alt="ER Diagram">
            </div>
            <div class="info">
                <h3>📘 Weak Entities (User Selected)</h3>
                <ul>{weak_html}</ul>
                <h3>🔗 Auto-Detected Many-to-Many Tables</h3>
                <ul>{m2m_html}</ul>
            </div>
            <a href="/{image_path}" class="button" download>📥 Download Diagram</a>
            <br><br>
            <a href="/">⬅️ Generate Another</a>
        </body>
        </html>
        """

    # Step 0: Upload form
    return '''
    <html>
    <head>
        <title>Upload Database</title>
        <style>
            body { font-family: Arial; background-color: #f4f6f9; text-align: center; padding: 50px; }
            form { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); display: inline-block; }
            h2 { color: #333; }
            input[type="file"] { margin: 20px 0; }
            button { background-color: #007BFF; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; }
            button:hover { background-color: #0056b3; }
        </style>
    </head>
    <body>
        <form method="POST" enctype="multipart/form-data">
            <h2>🩸 Upload your SQLite database (.db/.sqlite)</h2>
            <input type="file" name="file" accept=".db,.sqlite" required><br>
            <button type="submit">Next ➡️</button>
        </form>
    </body>
    </html>
    '''


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(STATIC_FOLDER, filename)


if __name__ == '__main__':
    app.run(debug=True)
