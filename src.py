from os import getenv
from dotenv import load_dotenv
from mssql_python import connect
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

def tipo_restriccion(tipo):
    if tipo == "PRIMARY_KEY_CONSTRAINT":
        return "Clave Primaria"
    elif tipo == "FOREIGN_KEY_CONSTRAINT":
        return "Clave Foránea"
    elif tipo == "UNIQUE_CONSTRAINT":
        return "Restricción de Unicidad"
    elif tipo == "CHECK_CONSTRAINT":
        return "Restricción de Comprobación"
    else:
        return "Otro Tipo de Restricción"
    
one_tab = ParagraphStyle(
    'OneTab',
    parent=getSampleStyleSheet()['Normal'],
    leftIndent=20,      # Shoves the entire paragraph right by 20 points
)

two_tab = ParagraphStyle(
    'TwoTab',
    parent=getSampleStyleSheet()['Normal'],
    leftIndent=40,      # Shoves the entire paragraph right by 40 points
)

# Confirguracion de los parametros de conexion a la base de datos
load_dotenv()  # Carga las variables de entorno desde el archivo .env
SQL_CONNECTION_STRING = getenv("SQL_CONNECTION_STRING")

try:
    # Establece la conexión
    connection = connect(SQL_CONNECTION_STRING)
    cursor = connection.cursor()

    # Obtiene el nombre de la base de datos y esquema
    cursor.execute(
        "SELECT " \
            "DB_NAME() AS DatabaseName"
    )
    rows = cursor.fetchall()
    
    # Crea un documento PDF y array de elementos para el informe
    pdf = SimpleDocTemplate("report.pdf")
    flowables = []

    # Escribe el título del informe
    text = f"Reporte técnico de la base de datos {rows[0][0]}"
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading1']))

    text = f"Al analizar la base de datos {rows[0][0]}, se encontraron los siguientes aspectos relevantes relacionados a su estructura y organización."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))

    text = f"1. Tablas e índices."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading2']))

    # Cantidad total de tablas
    cursor.execute(
        "SELECT COUNT(*) AS Cantidad_Tablas " \
        "FROM sys.tables"
    )
    rows = cursor.fetchall()

    text = f"La base de datos cuenta con {rows[0][0]} tablas de usuario definidas dentro del esquema."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))
    flowables.append(Spacer(1, 5))

    # Nombre de las tablas y cantidad de índices existentes en la base de datos
    cursor.execute(
        "SELECT " \
            "t.name AS Nombre_Tabla, " \
            "COUNT(i.name) AS Cantidad_Indices " \
        "FROM sys.tables t " \
        "LEFT JOIN sys.indexes i ON t.object_id = i.object_id " \
        "GROUP BY t.name"
    )
    rows = cursor.fetchall()

    # Columnas, unicidad e información relevante disponible en el Diccionario de Datos relacionada a cada índice creado en el esquema.
    cursor.execute(
        "SELECT " \
            "t.name AS Nombre_Tabla, " \
            "i.name AS Nombre_Indice, " \
            "i.type_desc AS Tipo_Indice, " \
            "STRING_AGG(c.name, ', ') AS Columnas, " \
            "i.is_unique AS Es_Unico " \
        "FROM sys.tables t " \
        "JOIN sys.indexes i ON t.object_id = i.object_id " \
        "JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id " \
        "JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id " \
        "GROUP BY t.name, i.name, i.type_desc, i.is_unique "
    )
    rows2 = cursor.fetchall()

    for row in rows:
        text = f"- {row[0]} con {row[1]} {'índices' if row[1] != 1 else 'índice'}{':' if row[1] > 0 else ''}"
        flowables.append(Paragraph(text, one_tab))
        for row2 in rows2:
            if row2[0] == row[0]:
                text = f"- {row2[1]}: Índice {'agrupado' if row2[2] == 'CLUSTERED' else 'no agrupado'}, {'único' if row2[3] else 'no Único'}, asociado a {row2[3]}"
                flowables.append(Paragraph(text, two_tab))
        flowables.append(Spacer(1, 5))

    text = f"2. Restricciones."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading2']))
    
    # Nombre, tabla asociada y tipo de las restricciones existentes en el esquema
    cursor.execute(
        "SELECT " \
            "t.name AS Tabla_Asociada, " \
            "o.name AS Nombre_Restriccion, " \
            "o.type_desc AS Tipo_Restriccion " \
        "FROM sys.objects o " \
        "JOIN sys.tables t ON o.parent_object_id = t.object_id;"
    )
    rows = cursor.fetchall()

    text = f"En cuanto a las restricciones existentes en el esquema, se encontraron {len(rows)} restricciones incluyendo claves primarias, claves foráneas, restricciones de unicidad y restricciones de comprobación."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))
    flowables.append(Spacer(1, 5))

    table_name = ""
    for row in rows:
        if row[0] != table_name:
            table_name = row[0]
            text = f"- Tabla {row[0]}: {'Sin restricciones' if row[1] is None else ''}"
            flowables.append(Paragraph(text, one_tab))
            if row[1]:
                    text = f"- {row[1]}: {tipo_restriccion(row[2])}"
                    flowables.append(Paragraph(text, two_tab))
            flowables.append(Spacer(1, 5)) 
        else:
            text = f"- {row[1]}: {tipo_restriccion(row[2])}"
            flowables.append(Paragraph(text, two_tab))
            flowables.append(Spacer(1, 5))

    text = f"3. Triggers."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading2']))

    # Nombre, tipo, estado y tabla activadora de cada trigger existente en el esquema.
    cursor.execute(
        "SELECT " \
            "tr.name AS Nombre_Trigger, " \
            "t.name AS Tabla_Asociada, " \
            "CASE WHEN tr.is_disabled = 1 THEN 'INACTIVO' ELSE 'ACTIVO' END AS Estado, " \
            "tr.create_date AS Fecha_Creacion, " \
            "tr.modify_date AS Fecha_Modificacion " \
        "FROM sys.triggers tr " \
        "LEFT JOIN sys.tables t ON tr.parent_id = t.object_id;"
    )
    rows = cursor.fetchall()

    text = f"Se encontraron {len(rows)} triggers en el esquema."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))

    for row in rows:
        text = f"- {row[0]} asociado a {row[1]}, actualmente {row[2].lower()} creado el {row[3]} y modificado por última vez el {row[4]}"
        flowables.append(Paragraph(text, one_tab))

    # Construye el pdf con la información obtenida
    pdf.build(flowables)

    # Cierra la conexión
    cursor.close()
    connection.close()

except Exception as e:
    print(f"Error al conectar a la base de datos: {e}")