from os import getenv
from dotenv import load_dotenv
from mssql_python import connect
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph

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

    # Nombre de las tablas e índices existentes en la base de datos
    text = f"1. Nombre de las tablas e índices existentes en la base de datos."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading2']))

    cursor.execute(
        "SELECT " \
            "t.name AS Nombre_Tabla, " \
            "CASE WHEN i.name IS NULL THEN 'HEAP' ELSE i.name END AS Nombre_Indice " \
        "FROM sys.tables t " \
        "JOIN sys.indexes i ON t.object_id = i.object_id"
    )
    rows = cursor.fetchall()

    text = f"Se encontraron los siguientes nombres de tablas e índices en la base de datos."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))

    for row in rows:
        text = f"   - {row[0]} - {row[1]}"
        flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))

    # Cantidad total de tablas
    text = f"2. Cantidad total de tablas."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading2']))
    cursor.execute(
        "SELECT COUNT(*) AS Cantidad_Tablas " \
        "FROM sys.tables"
    )
    rows = cursor.fetchall()
    text = f"Se encontraron {rows[0][0]} tablas dentro del esquema."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))

    # Cantidad total de índices definidos por tabla
    text = f"3. Cantidad total de índices definidos por tabla:"
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading2']))
    cursor.execute(
        "SELECT " \
            "t.name AS Nombre_Tabla, " \
            "COUNT(i.name) AS Cantidad_Indices " \
        "FROM sys.tables t " \
        "LEFT JOIN sys.indexes i ON t.object_id = i.object_id " \
        "GROUP BY t.name"
    )
    rows = cursor.fetchall()

    text = f"Se encontraron {len(rows)} tablas con índices:"
    flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))
    for row in rows:
        text = f"   - {row[0]} - {row[1]} índices"
        flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))

    # Nombre, tabla asociada y tipo de las restricciones existentes en el esquema
    text = f"4. Restricciones existentes en el esquema:"
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading2']))
    cursor.execute(
        "SELECT " \
            "o.name AS Nombre_Restriccion, " \
            "t.name AS Tabla_Asociada, " \
            "o.type_desc AS Tipo_Restriccion " \
        "FROM sys.objects o " \
        "JOIN sys.tables t ON o.parent_object_id = t.object_id;"
    )
    rows = cursor.fetchall()
    text = f"Se encontraron {len(rows)} restricciones en el esquema."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))
    for row in rows:
        text = f"   - {row[0]} - {row[1]} - {row[2]}"
        flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))

    # Columnas, unicidad e información relevante disponible en el Diccionario de Datos relacionada a cada índice creado en el esquema.
    text = f"5. Información de índices creada en el esquema."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading2']))
    cursor.execute(
        "SELECT " \
            "i.name AS Nombre_Indice, " \
            "i.type_desc AS Tipo_Indice, " \
            "t.name AS Nombre_Tabla, " \
            "c.name AS Columna, " \
            "i.is_unique AS Es_Unico " \
        "FROM sys.tables t " \
        "JOIN sys.indexes i ON t.object_id = i.object_id " \
        "JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id " \
        "JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id"
    )
    rows = cursor.fetchall()
    text = f"Se encontraron {len(rows)} índices en el esquema."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))
    for row in rows:
        text = f"   - {row[0]} - {row[1]} - {row[2]} - {row[3]} - {'Sí' if row[4] else 'No'}"
        flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))
    
    # Nombre, tipo, estado y tabla activadora de cada trigger existente en el esquema.
    text = f"6. Triggers existentes en el esquema."
    flowables.append(Paragraph(text, getSampleStyleSheet()['Heading2']))
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
        text = f"   - {row[0]} - {row[1]} - {row[2]} - Creado: {row[3]} - Modificado: {row[4]}"
        flowables.append(Paragraph(text, getSampleStyleSheet()['Normal']))

    # Construye el pdf con la información obtenida
    pdf.build(flowables)

    # Cierra la conexión
    cursor.close()
    connection.close()

except Exception as e:
    print(f"Error al conectar a la base de datos: {e}")