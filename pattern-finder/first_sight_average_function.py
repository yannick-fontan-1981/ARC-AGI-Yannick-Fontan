import sqlite3

def create_first_sight_average_function_table(conn):
    """
    Crée la table first_sight_average_function si elle n'existe pas,
    avec toutes les colonnes de first_sight_analysis,
    mais remplace 'filename' par 'function' et supprime 'trainId'.
    """
    cur = conn.cursor()

    # 1️⃣ Récupérer les colonnes de first_sight_analysis
    cur.execute("PRAGMA table_info(first_sight_analysis)")
    columns = [row[1] for row in cur.fetchall()]

    # 2️⃣ Exclure 'filename' et 'trainId', ajouter 'function'
    exclude_cols = {"filename", "trainId"}
    numeric_cols = [c for c in columns if c not in exclude_cols]
    column_definitions = ", ".join([f"{col} REAL" for col in numeric_cols])

    # 3️⃣ Créer la nouvelle table
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS first_sight_average_function (
            function TEXT PRIMARY KEY,
            {column_definitions}
        );
    """)
    conn.commit()

def populate_first_sight_average_function(conn):
    """
    Calcule les moyennes des colonnes de first_sight_analysis en fonction des fonctions
    utilisées dans solutions et les insère dans first_sight_average_function.
    """
    cur = conn.cursor()

    # 1️⃣ Récupérer les colonnes numériques de first_sight_analysis
    cur.execute("PRAGMA table_info(first_sight_analysis)")
    columns = [row[1] for row in cur.fetchall()]
    exclude_cols = {"filename", "trainId"}
    numeric_cols = [c for c in columns if c not in exclude_cols]

    # 2️⃣ Récupérer toutes les fonctions distinctes utilisées dans solutions
    cur.execute("SELECT DISTINCT function FROM solutions")
    functions = [row[0] for row in cur.fetchall()]

    for function in functions:
        # 3️⃣ Trouver les fichiers (filenames) qui utilisent cette fonction
        cur.execute("""
            SELECT DISTINCT filename FROM solutions WHERE function = ?
        """, (function,))
        filenames = [row[0] for row in cur.fetchall()]

        if not filenames:
            continue  # Si aucune correspondance, passer à la suivante

        # 4️⃣ Calculer la moyenne de chaque colonne pour ces fichiers
        col_averages = []
        for col in numeric_cols:
            cur.execute(f"""
                SELECT AVG({col}) FROM first_sight_analysis
                WHERE filename IN ({",".join(["?"] * len(filenames))})
            """, filenames)
            avg_value = cur.fetchone()[0]
            col_averages.append(avg_value if avg_value is not None else 0)  # Remplir avec 0 si NULL

        # 5️⃣ Insérer la moyenne dans first_sight_average_function
        cur.execute(f"""
            INSERT INTO first_sight_average_function (function, {", ".join(numeric_cols)})
            VALUES (?, {", ".join(["?"] * len(numeric_cols))})
            ON CONFLICT(function) DO UPDATE SET
            {", ".join([f"{col} = excluded.{col}" for col in numeric_cols])}
        """, [function] + col_averages)

    conn.commit()

def main(db_path="../db/database.db"):
    conn = sqlite3.connect(db_path)
    create_first_sight_average_function_table(conn)
    populate_first_sight_average_function(conn)
    conn.close()
    print("✅ Table first_sight_average_function mise à jour avec les moyennes.")

if __name__ == "__main__":
    main()
