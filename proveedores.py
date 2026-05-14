import sqlite3
import os

# --- ESTO ES LO NUEVO: Detecta la ruta real de tu carpeta ---
carpeta_actual = os.path.dirname(os.path.abspath(__file__))
ruta_base_datos = os.path.join(carpeta_actual, 'inventario.db')

def inicializar_todo():
    # Usamos la ruta completa detectada arriba
    conexion = sqlite3.connect(ruta_base_datos)
    cursor = conexion.cursor()

    # Creamos las tablas
    cursor.execute('CREATE TABLE IF NOT EXISTS proveedores (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL UNIQUE)')
    
    cursor.execute('DROP TABLE IF EXISTS productos')
    cursor.execute('''
        CREATE TABLE productos (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            stock_actual INTEGER DEFAULT 0,
            stock_minimo INTEGER DEFAULT 0,
            id_proveedor INTEGER,
            FOREIGN KEY (id_proveedor) REFERENCES proveedores(id)
        )
    ''')

    # Insertamos un proveedor de prueba para verificar
    cursor.execute("INSERT OR IGNORE INTO proveedores (nombre) VALUES ('Proveedor Inicial')")

    conexion.commit()
    conexion.close()
    print(f"¡Éxito! Archivo creado en: {ruta_base_datos}")

import os
print("Tu carpeta actual de trabajo es:", os.getcwd())
print("El archivo debería estar en:", os.path.join(os.getcwd(), 'inventario.db'))

if __name__ == "__main__":
    inicializar_todo()