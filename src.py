from os import getenv, name as osName
from datetime import datetime
from dotenv import load_dotenv
from mssql_python import connect
import subprocess, time

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.pdfgen import canvas

ansiBlue = "\033[1;34m"
ansiGreen = "\033[1;32m"
ansiYellow = "\033[1;33m"
ansiRed = "\033[1;31m"
ansiMagenta = "\033[1;35m"
ansiReset = "\033[0m"
ansiBold = "\033[1m"

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.savedPageStates = []

    def showPage(self):
        self.savedPageStates.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        numPages = len(self.savedPageStates)
        for state in self.savedPageStates:
            self.__dict__.update(state)
            self.drawPageDecorations(numPages)
            super().showPage()
        super().save()

    def drawPageDecorations(self, pageCount):
        self.saveState()
        if self._pageNumber > 1:
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.75)
            self.line(54, 738, 558, 738)
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#1A365D"))
            self.drawString(54, 744, "StreamUCV — REPORTE TÉCNICO DE LA BASE DE DATOS")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#718096"))
            self.line(54, 54, 558, 54)
            pageText = f"Página {self._pageNumber} de {pageCount}"
            self.drawRightString(558, 42, pageText)
        self.restoreState()


def clearScreen():
    subprocess.run(["clear"] if osName != "nt" else ["cls"], shell=True if osName == "nt" else False)


def getRestrictionType(restrictionTypeString):
    mapping = {
        "PRIMARY_KEY_CONSTRAINT": "Clave Primaria",
        "FOREIGN_KEY_CONSTRAINT": "Clave Foránea",
        "UNIQUE_CONSTRAINT": "Restricción de Unicidad",
        "CHECK_CONSTRAINT": "Restricción de Comprobación"
    }
    return mapping.get(restrictionTypeString, "Otro Tipo de Restricción")


def getTriggerType(triggerTypeString):
    if not triggerTypeString:
        return "Otro"
    val = triggerTypeString.replace("INSERT", "Inserción").replace("UPDATE", "Actualización").replace("DELETE", "Eliminación")
    val = val.replace("AFTER", "AFTER (Después)").replace("INSTEAD OF", "INSTEAD OF (En lugar de)")
    return val


def getDictionaryData():
    load_dotenv()
    sqlConnectionString = getenv("SQL_CONNECTION_STRING")
    schemaName = getenv("SCHEMA_NAME")

    if not sqlConnectionString:
        raise ValueError("The SQL_CONNECTION_STRING variable is not defined in the .env file")

    if not schemaName:
        raise ValueError("The SCHEMA_NAME variable is not defined in the .env file")

    data = {}
    connection = None
    cursor = None

    try:
        connection = connect(sqlConnectionString)
        cursor = connection.cursor()

        cursor.execute("SELECT DB_NAME() AS DatabaseName")
        data["dbName"] = cursor.fetchone()[0]
        data["schemaName"] = schemaName

        cursor.execute(f"SELECT COUNT(*) AS Cantidad_Tablas FROM sys.tables WHERE SCHEMA_NAME(schema_id) = '{schemaName}'")
        data["totalTables"] = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT 
                t.name AS Nombre_Tabla, 
                COUNT(i.name) AS Cantidad_Indices 
            FROM sys.tables t 
            LEFT JOIN sys.indexes i ON t.object_id = i.object_id 
            WHERE SCHEMA_NAME(t.schema_id) = '{schemaName}'
            GROUP BY t.name
        """)
        data["indexSummary"] = cursor.fetchall()

        cursor.execute(f"""
            SELECT 
                t.name AS Nombre_Tabla, 
                i.name AS Nombre_Indice, 
                i.type_desc AS Tipo_Indice, 
                STRING_AGG(c.name, ', ') AS Columnas, 
                i.is_unique AS Es_Unico 
            FROM sys.tables t 
            JOIN sys.indexes i ON t.object_id = i.object_id 
            JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id 
            JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id 
            WHERE SCHEMA_NAME(t.schema_id) = '{schemaName}'
            GROUP BY t.name, i.name, i.type_desc, i.is_unique
        """)
        data["indexDetails"] = cursor.fetchall()

        cursor.execute(f"""
            SELECT 
                t.name AS Tabla_Asociada, 
                o.name AS Nombre_Restriccion, 
                o.type_desc AS Tipo_Restriccion 
            FROM sys.objects o 
            JOIN sys.tables t ON o.parent_object_id = t.object_id
            WHERE SCHEMA_NAME(t.schema_id) = '{schemaName}'
              AND o.type_desc LIKE '%_CONSTRAINT'
        """)
        data["constraints"] = cursor.fetchall()

        cursor.execute(f"""
            SELECT 
                tr.name AS Nombre_Trigger, 
                t.name AS Tabla_Asociada, 
                CASE WHEN tr.is_disabled = 1 THEN 'INACTIVO' ELSE 'ACTIVO' END AS Estado, 
                tr.create_date AS Fecha_Creacion, 
                tr.modify_date AS Fecha_Modificacion,
                (CASE WHEN tr.is_instead_of_trigger = 1 THEN 'INSTEAD OF ' ELSE 'AFTER ' END + 
                 (SELECT STRING_AGG(te.type_desc, ', ') 
                  FROM sys.trigger_events te 
                  WHERE te.object_id = tr.object_id)) AS Tipo_Trigger
            FROM sys.triggers tr 
            LEFT JOIN sys.tables t ON tr.parent_id = t.object_id
            WHERE SCHEMA_NAME(t.schema_id) = '{schemaName}'
        """)
        data["triggers"] = cursor.fetchall()

        cursor.execute(f"""
            WITH SumaColumnas AS (
                SELECT object_id, SUM(max_length) AS Tamano_Registro_Bytes
                FROM sys.columns
                GROUP BY object_id
            ),
            ConteoRegistros AS (
                SELECT object_id, [rows] AS Numero_Registros
                FROM sys.partitions
                WHERE index_id <= 1
            )
            SELECT t.name AS Tabla,
            (sc.Tamano_Registro_Bytes * cr.Numero_Registros) AS Tamano_Tabla_Bytes,
            CAST((sc.Tamano_Registro_Bytes * cr.Numero_Registros) / 1024.0 AS DECIMAL(10,2)) AS Tamano_Tabla_KB
            FROM sys.tables t
            JOIN SumaColumnas sc ON t.object_id = sc.object_id
            JOIN ConteoRegistros cr ON t.object_id = cr.object_id
            WHERE SCHEMA_NAME(t.schema_id) = '{schemaName}'
        """)
        data["tableSizes"] = cursor.fetchall()

        cursor.execute(f"""
            SELECT 
                t.name AS Tabla, 
                SUM(c.max_length) AS Tamano_Registro_Bytes 
            FROM sys.tables t 
            JOIN sys.columns c ON t.object_id = c.object_id 
            WHERE SCHEMA_NAME(t.schema_id) = '{schemaName}'
            GROUP BY t.name;
        """)
        data["recordSizes"] = cursor.fetchall()

        cursor.execute(f"""
            SELECT 
                t.name AS Tabla, 
                c.name AS Columna, 
                ty.name AS Tipo_Dato, 
                c.max_length AS Tamano_Bytes 
            FROM sys.columns c 
            JOIN sys.tables t ON c.object_id = t.object_id 
            JOIN sys.types ty ON c.user_type_id=ty.user_type_id
            WHERE SCHEMA_NAME(t.schema_id) = '{schemaName}'
        """)
        data["columnSizes"] = cursor.fetchall()

        cursor.execute(f"""
            WITH SumaColumnas AS (
                SELECT object_id, SUM(max_length) AS Tamano_Registro_Bytes
                FROM sys.columns
                GROUP BY object_id
            )
            SELECT
            t.name AS Tabla,
            FLOOR(8192/sc.Tamano_Registro_Bytes) AS Factor_Bloqueo_Tabla
            FROM sys.tables t
            JOIN SumaColumnas sc ON t.object_id = sc.object_id
            WHERE SCHEMA_NAME(t.schema_id) = '{schemaName}'
        """)
        data["blockingFactors"] = cursor.fetchall()

        cursor.execute(f"""
            WITH ColumnaClave AS (
                SELECT
                    i.object_id,
                    i.index_id,
                    SUM(c.max_length) AS Tamano_Clave_Bytes
                FROM sys.indexes i
                JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                GROUP BY i.object_id, i.index_id
            )
            SELECT
                t.name AS Tabla,
                i.name AS Nombre_Indice,
                COALESCE(cc.Tamano_Clave_Bytes, 4) AS Tamano_Clave_Bytes,
                FLOOR(8192 / (8 + COALESCE(cc.Tamano_Clave_Bytes, 4))) AS Factor_Bloqueo_Indice
            FROM sys.tables t
            JOIN sys.indexes i ON t.object_id = i.object_id
            LEFT JOIN ColumnaClave cc ON i.object_id = cc.object_id AND i.index_id = cc.index_id
            WHERE SCHEMA_NAME(t.schema_id) = '{schemaName}' AND i.type_desc <> 'HEAP'
        """)
        data["indexBlockingFactors"] = cursor.fetchall()

        cursor.execute(f"""
            SELECT 
                t.name AS Tabla, 
                SUM(p.rows) AS Cantidad_Registros 
            FROM sys.tables t 
            JOIN sys.partitions p ON t.object_id = p.object_id 
            WHERE p.index_id <= 1 AND SCHEMA_NAME(t.schema_id) = '{schemaName}'
            GROUP BY t.name;
        """)
        data["rowCounts"] = cursor.fetchall()

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return data


def createBulletPoint(bulletTitle, bulletBody, styleCell, styleCellBold):
    return Table(
        [[Paragraph("&bull;", styleCellBold), Paragraph(f"<b>{bulletTitle}:</b> {bulletBody}", styleCell)]],
        colWidths=[15, 489],
        style=TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ])
    )


def generatePdfReport(data, outputFilename="report.pdf"):
    doc = SimpleDocTemplate(
        outputFilename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=72,
        bottomMargin=72
    )

    styles = getSampleStyleSheet()

    styleTitle = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1A365D'),
        spaceAfter=15
    )

    styleH2 = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#2B6CB0'),
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    styleBody = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#2D3748'),
        spaceAfter=10
    )

    styleCell = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#2D3748')
    )

    styleCellBold = ParagraphStyle(
        'CellTextBold',
        parent=styleCell,
        fontName='Helvetica-Bold'
    )

    styleHeaderCell = ParagraphStyle(
        'HeaderCell',
        parent=styleCell,
        fontName='Helvetica-Bold',
        textColor=colors.white
    )

    flowables = []
    flowables.append(Paragraph(f"Reporte Técnico de la Base de Datos '{data['dbName']}'", styleTitle))

    metadataData = [
        [Paragraph("Base de Datos Analizada:", styleCellBold), Paragraph(data['dbName'], styleCell)],
        [Paragraph("Esquema de Trabajo:", styleCellBold), Paragraph(data['schemaName'], styleCell)],
        [Paragraph("Fecha del Diagnóstico:", styleCellBold), Paragraph(datetime.now().strftime("%d/%m/%Y — %H:%M"), styleCell)],
        [Paragraph("Total de Tablas Detectadas:", styleCellBold), Paragraph(str(data['totalTables']), styleCell)]
    ]
    metadataTable = Table(metadataData, colWidths=[150, 354])
    metadataTable.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    flowables.append(metadataTable)

    sec1Flowables = []
    sec1Flowables.append(Paragraph("1. Tablas e Índices del Sistema", styleH2))

    totalIndexes = sum(row[1] for row in data["indexSummary"])
    sec1Intro = (
        f"La base de datos analizada contiene una <b>cantidad total de {data['totalTables']} tablas</b> estructuradas "
        f"dentro del esquema de trabajo '{data['schemaName']}'. Se ha detectado una <b>cantidad total de {totalIndexes} índices</b> "
        f"configurados a lo largo de estas tablas. A continuación, se detalla la cantidad de índices "
        f"definidos individualmente para cada una de las tablas, junto con su composición física."
    )
    sec1Flowables.append(Paragraph(sec1Intro, styleBody))

    indicesHeaders = ["Tabla", "Índice", "Tipo de Índice", "Columnas Asociadas", "Es Único"]
    indicesRows = [ [Paragraph(h, styleHeaderCell) for h in indicesHeaders] ]

    for tableRes in data["indexSummary"]:
        tableName, _ = tableRes
        indexesOfTable = [idx for idx in data["indexDetails"] if idx[0] == tableName]

        if not indexesOfTable:
            indicesRows.append([
                Paragraph(tableName, styleCellBold),
                Paragraph("'HEAP'", styleCell),
                Paragraph("Sin índices (Heap)", styleCell),
                Paragraph("—", styleCell),
                Paragraph("No", styleCell)
            ])
        else:
            for idx in indexesOfTable:
                _, idxName, idxType, cols, isUnique = idx
                indicesRows.append([
                    Paragraph(tableName, styleCellBold),
                    Paragraph(idxName, styleCell),
                    Paragraph("Agrupado" if idxType == "CLUSTERED" else "No agrupado", styleCell),
                    Paragraph(cols, styleCell),
                    Paragraph("Sí" if isUnique else "No", styleCell)
                ])

    tableIndices = Table(indicesRows, colWidths=[84, 130, 90, 150, 50])
    tableIndices.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    sec1Flowables.append(tableIndices)
    flowables.append(KeepTogether(sec1Flowables))

    sec2Flowables = []
    sec2Flowables.append(Paragraph("2. Restricciones del Esquema de Datos", styleH2))

    sec2Intro = (
        f"Se detectó una <b>cantidad total de {len(data['constraints'])} restricciones</b> de integridad física "
        f"aplicadas en el esquema de la base de datos. Estas reglas garantizan que las relaciones lógicas y límites "
        f"de valores se mantengan estables durante las transacciones en el motor."
    )
    sec2Flowables.append(Paragraph(sec2Intro, styleBody))

    restrHeaders = ["Tabla Asociada", "Nombre de la Restricción", "Tipo de Restricción"]
    restrRows = [ [Paragraph(h, styleHeaderCell) for h in restrHeaders] ]

    for row in data["constraints"]:
        associatedTable, restName, restType = row
        restrRows.append([
            Paragraph(associatedTable, styleCellBold),
            Paragraph(restName, styleCell),
            Paragraph(getRestrictionType(restType), styleCell)
        ])

    tableRestr = Table(restrRows, colWidths=[152, 200, 152])
    tableRestr.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    sec2Flowables.append(tableRestr)
    flowables.append(KeepTogether(sec2Flowables))
    flowables.append(Spacer(1, 20))

    sec3Flowables = []
    sec3Flowables.append(Paragraph("3. Disparadores (Triggers) Registrados", styleH2))

    sec3Intro = (
        f"El esquema cuenta actualmente con una <b>cantidad de {len(data['triggers'])} disparadores</b> (triggers) "
        f"de usuario definidos. A continuación se detalla el estado operativo, tipo y última fecha de modificación "
        f"de cada uno de estos procesos automatizados."
    )
    sec3Flowables.append(Paragraph(sec3Intro, styleBody))

    if not data["triggers"]:
        sec3Flowables.append(Paragraph("<i>No se encontraron disparadores (triggers) definidos en el repositorio de datos actual.</i>", styleBody))
    else:
        trigHeaders = ["Nombre del Trigger", "Tabla Asociada", "Tipo", "Estado", "Fecha de Modificación"]
        trigRows = [ [Paragraph(h, styleHeaderCell) for h in trigHeaders] ]

        for row in data["triggers"]:
            trigName, tabName, status, _, modDate, triggerType = row
            dateStr = modDate.strftime("%Y-%m-%d %H:%M") if isinstance(modDate, datetime) else str(modDate)
            trigRows.append([
                Paragraph(trigName, styleCellBold),
                Paragraph(tabName, styleCell),
                Paragraph(getTriggerType(triggerType), styleCell),
                Paragraph(status, styleCell),
                Paragraph(dateStr, styleCell)
            ])

        tableTrig = Table(trigRows, colWidths=[124, 100, 100, 70, 110])
        tableTrig.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        sec3Flowables.append(tableTrig)

    flowables.append(KeepTogether(sec3Flowables))
    flowables.append(Spacer(1, 20))

    sec4Flowables = []
    sec4Flowables.append(Paragraph("4. Estructura Física y Dimensiones del Esquema", styleH2))
    sec4Flowables.append(Paragraph("A continuación se muestra el desglose del tamaño real asignado a cada columna detectada en la base de datos de acuerdo a su tipo de datos. Los campos extensibles de tamaño variable que registran un tamaño máximo interno en el motor de base de datos se normalizan a efectos prácticos con un valor de visualización nominal.", styleBody))

    colHeaders = ["Tabla", "Columna", "Tipo de Dato", "Tamaño (Bytes)"]
    colRows = [ [Paragraph(h, styleHeaderCell) for h in colHeaders] ]
    for row in data["columnSizes"]:
        tName, colName, typeName, maxLength = row
        sizeStr = "MAX (8000)" if maxLength == -1 else str(maxLength)
        colRows.append([
            Paragraph(tName, styleCellBold),
            Paragraph(colName, styleCell),
            Paragraph(typeName, styleCell),
            Paragraph(sizeStr, styleCell)
        ])

    tableCols = Table(colRows, colWidths=[154, 150, 120, 80])
    tableCols.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    sec4Flowables.append(tableCols)
    flowables.append(KeepTogether(sec4Flowables))
    flowables.append(Spacer(1, 20))

    sec5Flowables = []
    sec5Flowables.append(Paragraph("5. Capacidad de Almacenamiento y Factor de Bloqueo", styleH2))

    explanationBlock = (
        "Se evalúan las capacidades de almacenamiento físico considerando un tamaño de bloque o página de datos "
        "estándar de 8 KB (8192 Bytes). El factor de bloqueo representa la cantidad de registros fijos e indexables "
        "que pueden ser almacenados de forma consecutiva dentro de una única página lógica de datos. Las fórmulas "
        "aplicadas corresponden a los siguientes criterios de optimización teórica:"
    )
    sec5Flowables.append(Paragraph(explanationBlock, styleBody))

    storageHeaders = ["Tabla", "Tamaño Tabla (Bytes)", "Tamaño Tabla (KB)", "Reg. Size (Bytes)", "Fbt"]
    storageRows = [ [Paragraph(h, styleHeaderCell) for h in storageHeaders] ]

    blockingFactorsMap = {b[0]: b[1] for b in data["blockingFactors"]}
    recordSizesMap = {r[0]: r[1] for r in data["recordSizes"]}

    for row in data["tableSizes"]:
        tName, sizeBytes, sizeKb = row
        recordSize = recordSizesMap.get(tName, 1)
        fbt = blockingFactorsMap.get(tName, 1)

        storageRows.append([
            Paragraph(tName, styleCellBold),
            Paragraph(str(sizeBytes), styleCell),
            Paragraph(str(sizeKb) + " KB", styleCell),
            Paragraph(str(recordSize), styleCell),
            Paragraph(str(fbt), styleCell)
        ])

    tableStorage = Table(storageRows, colWidths=[134, 100, 100, 100, 70])
    tableStorage.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))

    indexStorageHeaders = ["Tabla", "Nombre del Índice", "Ancho Clave (Bytes)", "Fbi (Índice)"]
    indexStorageRows = [ [Paragraph(h, styleHeaderCell) for h in indexStorageHeaders] ]

    for row in data["indexBlockingFactors"]:
        tName, idxName, keySize, fbi = row
        indexStorageRows.append([
            Paragraph(tName, styleCellBold),
            Paragraph(idxName, styleCell),
            Paragraph(str(keySize), styleCell),
            Paragraph(str(fbi), styleCell)
        ])

    tableIndexStorage = Table(indexStorageRows, colWidths=[124, 180, 100, 100])
    tableIndexStorage.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))

    sec5Flowables.append(Paragraph("<b>Capacidad de Almacenamiento de las Tablas:</b>", styleBody))
    sec5Flowables.append(tableStorage)
    sec5Flowables.append(Spacer(1, 15))
    sec5Flowables.append(Paragraph("<b>Factores de Bloqueo por Índice Individual:</b>", styleBody))
    sec5Flowables.append(tableIndexStorage)
    flowables.append(KeepTogether(sec5Flowables))
    flowables.append(Spacer(1, 20))

    sec6Flowables = []
    sec6Flowables.append(Paragraph("6. Modelado de Accesos a Disco y Costos de Tiempo", styleH2))

    costExplanation = (
        "De acuerdo con los requerimientos técnicos fijados por la dirección tecnológica, se modelan los accesos "
        "a disco físicos (lectura de páginas) estimando una velocidad de transferencia teórica estándar de 17 MB/s. "
        "Se evalúan y contrastan dos escenarios lógicos para consultas de igualdad sobre un campo clave:"
    )
    sec6Flowables.append(Paragraph(costExplanation, styleBody))

    sec6Flowables.append(createBulletPoint(
        "Búsqueda Secuencial (Table Scan)",
        "Se deben leer e inspeccionar la totalidad de las páginas de datos en el archivo físico de la tabla. El costo total en accesos equivale a la totalidad de las páginas asignadas.",
        styleCell,
        styleCellBold
    ))
    sec6Flowables.append(Spacer(1, 4))
    sec6Flowables.append(createBulletPoint(
        "Búsqueda Indexada (Index Access)",
        "Si existe un índice, se asume un acceso constante por niveles a través de la altura del árbol B+ más la lectura del registro final de datos en la página de datos. Costo constante de 3 páginas físicas de E/S.",
        styleCell,
        styleCellBold
    ))
    sec6Flowables.append(Spacer(1, 10))

    costHeaders = ["Tabla", "E/S Table Scan", "Tiempo Scan", "E/S Indexada", "Tiempo Indexado"]
    costRows = [ [Paragraph(h, styleHeaderCell) for h in costHeaders] ]

    indexCountsMap = {r[0]: r[1] for r in data["indexSummary"]}
    rowCountsMap = {r[0]: r[1] for r in data["rowCounts"]}

    for row in data["tableSizes"]:
        tName, _, _ = row
        recordSize = recordSizesMap.get(tName, 1)
        rowNum = rowCountsMap.get(tName, 0)
        hasIndex = indexCountsMap.get(tName, 0) > 0

        fbt = blockingFactorsMap.get(tName, max(1, 8192 // recordSize))
        totalPages = max(1, -(-rowNum // fbt))

        scanAccesses = totalPages
        scanTimeMs = (scanAccesses * 8192) / (17 * 1024 * 1024) * 1000

        if hasIndex:
            idxAccesses = 3
            idxTimeMs = (idxAccesses * 8192) / (17 * 1024 * 1024) * 1000
        else:
            idxAccesses = scanAccesses
            idxTimeMs = scanTimeMs

        scanTimeStr = f"{scanTimeMs:.4f} ms" if scanTimeMs >= 0.0001 else "< 0.0001 ms"
        idxTimeStr = f"{idxTimeMs:.4f} ms" if idxTimeMs >= 0.0001 else "< 0.0001 ms"
        idxAccessStr = str(idxAccesses) if hasIndex else f"{idxAccesses} (Sin Índice)"

        costRows.append([
            Paragraph(tName, styleCellBold),
            Paragraph(str(scanAccesses), styleCell),
            Paragraph(scanTimeStr, styleCell),
            Paragraph(idxAccessStr, styleCell),
            Paragraph(idxTimeStr, styleCell)
        ])

    tableCosts = Table(costRows, colWidths=[104, 100, 100, 100, 100])
    tableCosts.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A365D')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    sec6Flowables.append(tableCosts)
    flowables.append(KeepTogether(sec6Flowables))

    doc.build(flowables, canvasmaker=NumberedCanvas)


def runCostSimulationMenu(data):
    clearScreen()
    print(f"\n{ansiBlue}╒════════════════════════════════════════════════════════╕{ansiReset}")
    print(f"{ansiBlue}│            {ansiReset}SIMULACIÓN INTERACTIVA DE COSTOS{ansiBlue}            │{ansiReset}")
    print(f"{ansiBlue}╘════════════════════════════════════════════════════════╛{ansiReset}\n")
    print(f"Tablas disponibles en el esquema '{data['schemaName']}':")

    rowCountsMap = {r[0]: r[1] for r in data["rowCounts"]}
    blockingFactorsMap = {b[0]: (b[1], b[2]) for b in data["blockingFactors"]}
    recordSizesMap = {r[0]: r[1] for r in data["recordSizes"]}

    tableList = sorted(list(recordSizesMap.keys()))
    for i, tName in enumerate(tableList, start=1):
        print(f"  {ansiBold}{i}.{ansiReset} {tName}")

    try:
        choice = int(input(f"\n{ansiBold}Seleccione el número de la tabla a consultar: {ansiReset}"))
        if choice < 1 or choice > len(tableList):
            print(f"{ansiRed}[ERROR]{ansiReset} Selección fuera de rango.")
            input(f"\n{ansiBold}Presione Enter para continuar...{ansiReset}")
            return

        selectedTableName = tableList[choice - 1]

        validColumns = [row[1].lower() for row in data["columnSizes"] if row[0] == selectedTableName]
        print(f"Columnas válidas en la tabla '{selectedTableName}': {ansiMagenta}{', '.join(validColumns)}{ansiReset}")

        columnNameInput = input(f"{ansiBold}Ingrese la columna para la condición de igualdad: {ansiReset}").strip().lower()

        if columnNameInput not in validColumns:
            print(f"\n{ansiRed}[ERROR]{ansiReset} La columna '{columnNameInput}' no existe en la tabla «{selectedTableName}».")
            input(f"\n{ansiBold}Presione Enter para regresar...{ansiReset}")
            return

        indexedColumns = []
        for row in data["indexDetails"]:
            if row[0] == selectedTableName:
                for c in row[3].split(","):
                    indexedColumns.append(c.strip().lower())

        hasIndex = columnNameInput in indexedColumns
        rowNum = rowCountsMap.get(selectedTableName, 0)
        recordSize = recordSizesMap.get(selectedTableName, 1)
        fbt, _ = blockingFactorsMap.get(selectedTableName, (max(1, 8192 // recordSize), 682))
        totalPages = max(1, -(-rowNum // fbt))

        print(f"\n{ansiBlue}RESULTADOS DE AUDITORÍA FÍSICA DE ACCESO:{ansiReset}")

        scanAccesses = totalPages
        scanTimeMs = (scanAccesses * 8192) / (17 * 1024 * 1024) * 1000
        print(f"\n{ansiBold}[BÚSQUEDA SECUENCIAL (TABLE SCAN)]{ansiReset}")
        print(f"  - Costo de Entrada/Salida: {ansiRed}{scanAccesses}{ansiReset} páginas leídas de disco.")
        print(f"  - Tiempo estimado de respuesta: {ansiRed}{scanTimeMs:.4f} ms{ansiReset}.")

        print(f"\n{ansiBold}[BÚSQUEDA INDEXADA (INDEX ACCESS)]{ansiReset}")
        if hasIndex:
            idxAccesses = 3
            idxTimeMs = (idxAccesses * 8192) / (17 * 1024 * 1024) * 1000
            print(f"  - Se ha detectado un índice, asumiendo la estructura B+ Tree para {ansiMagenta}'{columnNameInput}'{ansiReset}.")
            print(f"  - Costo de Entrada/Salida optimizado: {ansiGreen}{idxAccesses}{ansiReset} páginas leídas de disco.")
            print(f"  - Tiempo estimado de respuesta optimizado: {ansiGreen}{idxTimeMs:.4f} ms{ansiReset}.")
        else:
            print(f"  - No se detectaron índices para la columna {ansiMagenta}'{columnNameInput}'{ansiReset} en el Diccionario de Datos.")
            print("  - El motor se ve obligado a degradar la consulta a un escaneo secuencial físico.")
            print(f"  - Costo de Entrada/Salida: {ansiRed}{scanAccesses}{ansiReset} páginas leídas.")
            print(f"  - Tiempo estimado de respuesta: {ansiRed}{scanTimeMs:.4f} ms{ansiReset}.")

    except Exception as e:
        print(f"{ansiRed}[ERROR]{ansiReset} Entrada inválida durante el procesamiento: {e}")

    input(f"\n{ansiBold}Presione Enter para regresar al menú principal...{ansiReset}")


if __name__ == "__main__":
    clearScreen()

    try:
        databaseData = getDictionaryData()
    except Exception as e:
        print(f"\n{ansiRed}[ERROR CRÍTICO]{ansiReset} No se pudo conectar al repositorio.")
        print(f"Detalle del error: {e}")
        exit(1)

    while True:
        clearScreen()
        print(f"\n{ansiBlue}╒════════════════════════════════════════════════════════╕{ansiReset}")
        print(f"{ansiBlue}│      {ansiReset}STREAMUCV — INTERFAZ ADMINISTRATIVA DE DATOS{ansiBlue}      │{ansiReset}")
        print(f"{ansiBlue}╘════════════════════════════════════════════════════════╛{ansiReset}\n")
        print(" 1. Generar reporte formal de diagnóstico de almacenamiento")
        print(" 2. Simular costos de Entrada/Salida en consultas de igualdad")
        print(" 3. Salir del sistema\n")

        userChoice = input(f"{ansiBold}Ingrese una opción (1-3): {ansiReset}").strip()

        if userChoice == "1":
            try:
                databaseData = getDictionaryData()
                generatePdfReport(databaseData)
                print(f"{ansiGreen}[ÉXITO]{ansiReset} El archivo 'report.pdf' se ha generado correctamente.")
            except Exception as e:
                print(f"{ansiRed}[ERROR] Error al maquetar el documento: {e}{ansiReset}")
            input(f"\n{ansiBold}Presione Enter para continuar...{ansiReset}")

        elif userChoice == "2":
            try:
                databaseData = getDictionaryData()
                runCostSimulationMenu(databaseData)
            except Exception as e:
                print(f"{ansiRed}[ERROR] Error al sincronizar metadatos: {e}{ansiReset}")

        elif userChoice == "3":
            clearScreen()
            print("Cerrando sesión administrativa de StreamUCV...")
            break
