from os import getenv
from dotenv import load_dotenv
from mssql_python import connect

# Confirguracion de los parametros de conexion a la base de datos
load_dotenv()  # Carga las variables de entorno desde el archivo .env
SQL_CONNECTION_STRING = getenv("SQL_CONNECTION_STRING")

try:
    # Establece la conexión
    conexion = connect(SQL_CONNECTION_STRING)
    cursor = conexion.cursor()
    
    # Ejecuta una consulta de ejemplo
    cursor.execute("SELECT @@version;")
    fila = cursor.fetchone()
    print(f"Versión de SQL Server: {fila[0]}")
    
    # Cierra la conexión
    cursor.close()
    conexion.close()

except Exception as e:
    print(f"Error al conectar a la base de datos: {e}")