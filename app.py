import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
from datetime import datetime
from functools import wraps

#===============================
# --- CONFIGURACIÓN DE RUTAS ---
#===============================

base_dir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, 
            template_folder=os.path.join(base_dir, 'templates'),
            static_folder=os.path.join(base_dir, 'static'))

app.secret_key = 'tu_clave_secreta'

#===============================
# --- DECORADOR DE SEGURIDAD ---
#===============================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_logueado' not in session:
            flash("Por favor, inicia sesión para acceder.")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

#=================================
# --- CONEXIÓN A BASE DE DATOS ---
#=================================

def conectar_db():
    conexion = sqlite3.connect('inventario.db')
    conexion.row_factory = sqlite3.Row
    return conexion

#==============
# --- LOGIN / AUTH ---
#==============

@app.route('/') 
def index():
    return render_template('login.html')

@app.route('/auth', methods=['POST'])
def auth():
    user_input = request.form.get('usuario')
    pass_input = request.form.get('password')

    con = conectar_db()
    usuario_encontrado = con.execute(
        'SELECT * FROM usuarios WHERE usuario = ? AND password = ?', 
        (user_input, pass_input)
    ).fetchone()
    con.close()

    if usuario_encontrado:
        session['usuario_logueado'] = usuario_encontrado['usuario']
        session['rol'] = usuario_encontrado['rol']
        return redirect(url_for('dashboard'))
    else:
        flash('Credenciales incorrectas.')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada.")
    return redirect(url_for('index'))

#==================
# --- DASHBOARD ---
#==================

@app.route('/dashboard')
@login_required
def dashboard():
    rol = str(session.get('rol', '')).strip().lower()
    if rol == 'operario':
        return redirect(url_for('fabrica'))

    con = conectar_db()

    # CON ESTO ACCEDEMOS A LAS COLUMNAS POR NOMBRE

    con.row_factory = sqlite3.Row 
    
    n_stock = n_alertas = n_pendientes = n_prov = n_incidencias = 0
    recientes = []
    proveedores = [] # Lista para el desplegable del modal

    try:
        # 1. Consultas de conteo

        n_stock = con.execute('SELECT COUNT(*) FROM Productos').fetchone()[0]
        n_alertas = con.execute('SELECT COUNT(*) FROM Productos WHERE stock_actual <= stock_minimo').fetchone()[0]
        n_pendientes = con.execute("SELECT COUNT(*) FROM vales_pedido WHERE estado = 'Pendiente'").fetchone()[0]
        n_prov = con.execute('SELECT COUNT(*) FROM proveedores').fetchone()[0]
        
        # 2. CARGAMOS LOS PROVEEDORES (Para el modal de añadir producto)

        proveedores = con.execute('SELECT id, nombre FROM proveedores ORDER BY nombre ASC').fetchall()

        # 3. Consulta de Recientes

        recientes = con.execute('''
            SELECT codigo_vale, estado, Fecha 
            FROM vales_pedido 
            ORDER BY datetime(Fecha) DESC 
            LIMIT 4
        ''').fetchall()

        # 4. Consulta de incidencias

        try:
            n_incidencias = con.execute("SELECT COUNT(*) FROM incidencias WHERE resuelta = 0").fetchone()[0]
        except Exception as e_inc:
            print(f"⚠️ Nota: No se pudo cargar incidencias: {e_inc}")
            n_incidencias = 0

    except Exception as e:
        print(f"⚠️ Error Crítico Dashboard: {e}")
    finally:
        con.close()
    
    return render_template('dashboard.html', 
                            n_stock=n_stock, 
                            n_alertas=n_alertas, 
                            n_pedidos=n_pendientes, 
                            n_prov=n_prov, 
                            n_incidencias=n_incidencias,
                            recientes=recientes,
                            proveedores=proveedores) # <--- Enviamos la lista aquí

#===========================
# --- INVENTARIO (STOCK) ---
#===========================

@app.route('/inventario')
@login_required 
def stock():
    con = conectar_db()
    proveedor_id = request.args.get('proveedor_id')
    
    # Tabla: Productos (id, nombre, stock_actual, Stock_minimo, id_proveedor)
    query = '''
        SELECT p.id, p.nombre, p.stock_actual, p.Stock_minimo, prov.nombre AS nombre_proveedor
        FROM Productos p
        JOIN proveedores prov ON p.id_proveedor = prov.id
    '''
    params = []
    if proveedor_id:
        query += " WHERE p.id_proveedor = ?"
        params.append(proveedor_id)
    
    productos = con.execute(query, params).fetchall()
    proveedores = con.execute('SELECT * FROM proveedores').fetchall()
    con.close()
    
    return render_template('stock.html', productos=productos, proveedores=proveedores)

#================
# --- PEDIDOS ---
#================

@app.route('/pedidos')
@login_required
def pedido():
    con = conectar_db()
    productos = con.execute('SELECT id, nombre FROM Productos').fetchall()
    
    # Generador de Código de Vale
    fecha_hoy = datetime.now().strftime('%Y%m%d')
    prefijo = f"V-{fecha_hoy}-"
    resultado = con.execute("SELECT COUNT(*) FROM vales_pedido WHERE codigo_vale LIKE ?", (f"{prefijo}%",)).fetchone()
    contador = resultado[0] + 1
    sugerencia_id = f"{prefijo}{contador:03d}"
    
    pedidos = con.execute('SELECT * FROM vales_pedido ORDER BY Fecha DESC').fetchall()
    con.close()
    return render_template('pedido.html', productos=productos, pedidos=pedidos, 
                           sugerencia_id=sugerencia_id, fecha_actual=datetime.now().strftime('%d/%m/%Y'))

#=======================
# --- GUARDAR PEDIDO ---
#=======================

@app.route('/guardar_pedido', methods=['POST'])
@login_required
def guardar_pedido():
    con = conectar_db()
    con.row_factory = sqlite3.Row # Para acceder por nombre de columna
    try:
        data = request.get_json()
        codigo_vale = data.get('id_vale')
        items = data.get('items')

        print(f"DEBUG: Intentando guardar vale {codigo_vale} con {len(items)} items")

        # 1. Validar existencias y límites ANTES de insertar nada
        for p in items:
            id_prod = p.get('id')
            cantidad_solicitada = int(p.get('cantidad'))

            # Consultamos los límites actuales del producto
            prod_info = con.execute('''
                SELECT nombre, stock_actual, stock_maximo 
                FROM Productos WHERE id = ?
            ''', (id_prod,)).fetchone()

            if prod_info:
                espacio_disponible = prod_info['stock_maximo'] - prod_info['stock_actual']
                
                if cantidad_solicitada > espacio_disponible:
                    # Si supera el máximo, lanzamos un error descriptivo
                    raise ValueError(
                        f"Capacidad excedida para '{prod_info['nombre']}'. "
                        f"Disponible: {espacio_disponible}, Solicitado: {cantidad_solicitada}"
                    )

        # 2. Si todas las validaciones pasan, insertamos Cabecera
        con.execute('''
            INSERT INTO vales_pedido (codigo_vale, Fecha, estado) 
            VALUES (?, datetime('now', 'localtime'), ?)
        ''', (codigo_vale, 'Pendiente'))

        # 3. Insertar Líneas
        for p in items:
            id_prod = p.get('id') 
            cantidad = p.get('cantidad')
            
            con.execute('''
                INSERT INTO lineas_vale (codigo_vale, id_producto, cantidad) 
                VALUES (?, ?, ?)
            ''', (codigo_vale, id_prod, cantidad))
        
        con.commit()
        print("✅ Vale guardado correctamente y validado contra stock máximo")
        return jsonify({"status": "success"}), 200

    except ValueError as ve:
        # (stock superado)
        con.rollback()
        print(f"⚠️ VALIDACIÓN FALLIDA: {str(ve)}")
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        con.rollback()
        print(f" STOCK MAXIMO ALCANZADO: {str(e)}")
        return jsonify({"status": "error", "message": "Esta cantidad supera es stock máximo del producto"}), 500
    finally:
        con.close()

#===========================
# --- FÁBRICA (OPERARIO) ---
#===========================

@app.route('/fabrica')
@login_required
def fabrica():
    return render_template('fabrica.html')

#====================
# --- BUSCAR VALE ---
#====================

@app.route('/buscar_vale/<codigo>')
@login_required
def buscar_vale(codigo):
    con = conectar_db()
    con.row_factory = sqlite3.Row
    codigo = codigo.strip()
    try:
        vale = con.execute('SELECT * FROM vales_pedido WHERE codigo_vale = ?', (codigo,)).fetchone()
        if not vale:
            return jsonify({"success": False, "message": "Vale no encontrado"})

        # Cruce entre lineas_vale y Productos
        productos = con.execute('''
            SELECT p.nombre, p.id, lv.cantidad AS cantidad_pedida
            FROM lineas_vale lv
            JOIN Productos p ON lv.id_producto = p.id
            WHERE lv.codigo_vale = ?
        ''', (codigo,)).fetchall()

        lista_prods = [dict(ix) for ix in productos]
        if not lista_prods:
            return jsonify({"success": False, "message": "El vale no tiene líneas cargadas"})

        return {"success": True, "codigo": vale['codigo_vale'], "productos": lista_prods}
    finally:
        con.close()

#=============================
# --- CONFIRMAR MOVIMIENTO ---
#=============================

@app.route('/confirmar_movimiento', methods=['POST'])
@login_required
def confirmar_movimiento():
    datos = request.json
    codigo_vale = datos.get('codigo_vale', '').strip()
    items = datos.get('items', [])
    modo = datos.get('modo', 'entrada') # <--- Capturamos si es entrada o salida
    texto_incidencia = datos.get('incidencia', '').strip()

    con = conectar_db()
    try:
        # 1. DefinE el multiplicador (1 para sumar, -1 para restar)
        multiplicador = 1 if modo == 'entrada' else -1

        # 2. Actualiza stock con el multiplicador
        for item in items:
            # Si es salida, suma un número negativo, lo cual resta: stock + (-cantidad)
            con.execute('''
                UPDATE Productos 
                SET stock_actual = stock_actual + (? * ?) 
                WHERE id = ?
            ''', (item['cantidad'], multiplicador, item['id_producto']))

        # 3. Registra el vale como procesado
        con.execute("UPDATE vales_pedido SET estado = 'PROCESADO' WHERE codigo_vale = ?", (codigo_vale,))

        # 4. Guarda incidencia si existe
        if texto_incidencia:
            con.execute('''
                INSERT INTO incidencias (codigo_vale, descripcion, fecha, resuelta)
                VALUES (?, ?, datetime('now', 'localtime'), 0)
            ''', (codigo_vale, texto_incidencia))

        con.commit()
        return jsonify({"success": True})
    except Exception as e:
        con.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        con.close()

#====================
# --- PROVEEDORES ---
#====================

@app.route('/proveedores')
@login_required
def proveedores():
    con = conectar_db()
    datos = con.execute('SELECT * FROM proveedores').fetchall()
    con.close()
    return render_template('proveedores1.html', proveedores=datos)

#====================
# --- INCIDENCIAS ---
#====================

@app.route('/incidencias')
@login_required
def gestion_incidencias():
    con = conectar_db()
    # Accede a las columnas por nombre: inc['id']
    con.row_factory = sqlite3.Row 
    
    try:
        # Obtiene solo las que no están resueltas (resuelta = 0)
        res = con.execute('SELECT * FROM incidencias WHERE resuelta = 0 ORDER BY fecha DESC').fetchall()
        lista_incidencias = [dict(row) for row in res]
        n_incidencias = len(lista_incidencias)
    except Exception as e:
        print(f"⚠️ Error cargando incidencias: {e}")
        lista_incidencias = []
        n_incidencias = 0
    finally:
        con.close()
    
    return render_template('incidencias.html', 
                           lista_incidencias=lista_incidencias, 
                           n_incidencias=n_incidencias)

# 1. ESTA RUTA SOLO MUESTRA LA LISTA

#=========================
# --- CREAR INCIDENCIA ---
#=========================

@app.route('/crear_incidencia', methods=['POST'])
@login_required
def crear_incidencia():
    datos = request.json
    codigo_vale = datos.get('codigo_vale')
    descripcion = datos.get('descripcion')
    
    con = conectar_db()
    try:
        # Insertamos la incidencia con resuelta = 0 (pendiente)
        con.execute('''
            INSERT INTO incidencias (codigo_vale, descripcion, fecha, resuelta)
            VALUES (?, ?, datetime('now', 'localtime'), 0)
        ''', (codigo_vale, descripcion))
        con.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error al crear incidencia: {e}")
        return jsonify({"success": False, "message": str(e)})
    finally:
        con.close()

#Lista de las incidencias por resolver
@app.route('/incidencias')
@login_required
def incidencias(): # Nombre simple y único
    con = conectar_db()
    con.row_factory = sqlite3.Row
    # Solo muestra las no resueltas
    res = con.execute('SELECT * FROM incidencias WHERE resuelta = 0 ORDER BY fecha DESC').fetchall()
    lista = [dict(row) for row in res]
    n_incidencias = len(lista)
    con.close()
    return render_template('incidencias.html', lista_incidencias=lista, n_incidencias=n_incidencias)

#ESTA RUTA ELIMINA LA INCIDENCIA Y TE DEJA EN LA MISMA PÁGINA
@app.route('/resolver_incidencia/<int:id>', methods=['POST'])
@login_required
def resolver_incidencia(id):
    con = conectar_db()
    try:
        # La marcamos como resuelta para que desaparezca de la vista
        con.execute('UPDATE incidencias SET resuelta = 1 WHERE id = ?', (id,))
        con.commit()
    finally:
        con.close()
    # Volvemos a la lista, que ahora tendrá una fila menos
    return redirect(url_for('incidencias'))

#==================
# --- ANALITICA ---
#==================

@app.route('/analitica')
@login_required
def analitica():
    con = conectar_db()
    con.row_factory = sqlite3.Row
    
    # KPI: Capacidad del Almacén
    capacidad = con.execute('''
        SELECT 
            SUM(stock_actual) as total_actual, 
            SUM(stock_maximo) as total_maximo 
        FROM Productos
    ''').fetchone()
    
    t_actual = capacidad['total_actual'] or 0
    t_maximo = capacidad['total_maximo'] or 1 
    porcentaje_ocupacion = round((t_actual / t_maximo) * 100, 1)

    # KPI: Pedidos del mes actual
    pedidos_mes = con.execute('''
        SELECT COUNT(*) as total FROM vales_pedido 
        WHERE strftime('%m', Fecha) = strftime('%m', 'now')
    ''').fetchone()['total']

    # --- LÓGICA DE 12 MESES PARA LA GRÁFICA ---
    
    # Estructura fija de los 12 meses
    nombres = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
    # Creamos un diccionario base: {'01': {'mes': 'ENE', 'cantidad': 0}, ...}
    stats_map = {str(i).zfill(2): {"mes": nombres[i-1], "cantidad": 0} for i in range(1, 13)}

    # 2. Obtenemos datos de la DB (quitamos el LIMIT y el CASE largo para hacerlo más eficiente)
    # Extraemos el número del mes directamente del código_vale (posiciones 7 y 8)
    datos_db = con.execute('''
        SELECT 
            substr(codigo_vale, 7, 2) as mes_num,
            COUNT(*) as total
        FROM lineas_vale
        GROUP BY mes_num
    ''').fetchall()

    # 3. Volcamos los datos reales sobre nuestro mapa de 12 meses
    for fila in datos_db:
        m_num = fila['mes_num']
        if m_num in stats_map:
            stats_map[m_num]['cantidad'] = fila['total']

    # 4. Convertimos el diccionario en una lista ordenada del 01 al 12
    stats_grafica = [stats_map[str(i).zfill(2)] for i in range(1, 13)]

    # --- FIN LÓGICA GRÁFICA ---

    # Ranking: Top 5 productos más pedidos
    ranking = con.execute('''
        SELECT p.nombre, SUM(l.cantidad) as total_vendido
        FROM lineas_vale l
        JOIN Productos p ON l.id_producto = p.id
        GROUP BY p.id
        ORDER BY total_vendido DESC
        LIMIT 3
    ''').fetchall()
# 2. STOCK MUERTO (Los 5 menos vendidos, incluyendo los de 0 ventas)
    # Usamos LEFT JOIN para que salgan productos aunque no tengan registros en lineas_vale
    stock_muerto = con.execute('''
        SELECT p.nombre, COALESCE(SUM(l.cantidad), 0) as total_vendido
        FROM Productos p
        LEFT JOIN lineas_vale l ON p.id = l.id_producto
        GROUP BY p.id
        ORDER BY total_vendido ASC
        LIMIT 3
    ''').fetchall()

    con.close()
    
    return render_template('analitica.html', 
                            porcentaje=porcentaje_ocupacion,
                            t_actual=t_actual,
                            t_maximo=t_maximo,
                            pedidos_mes=pedidos_mes,
                            ranking=ranking,
                            stock_muerto=stock_muerto,  # <--- Enviamos la nueva lista
                            stats_grafica=stats_grafica)
    con.close()
    
    return render_template('analitica.html', 
                           porcentaje=porcentaje_ocupacion,
                           t_actual=t_actual,
                           t_maximo=t_maximo,
                           pedidos_mes=pedidos_mes,
                           ranking=ranking,
                           stats_grafica=stats_grafica)

#========================
# --- NUEVO PROVEEDOR ---
#========================

@app.route('/actualizar_proveedor', methods=['POST'])
@login_required
def actualizar_proveedor():
    # Esto imprime en la terminal todo lo que llega del formulario
    print("Datos recibidos:", request.form) 

    id_prov = request.form.get('id')
    nombre = request.form.get('nombre')
    categoria = request.form.get('categoria')
    contacto = request.form.get('contacto')

    # Imprimimos variables individuales para ver si alguna llega vacía (None)
    print(f"ID: {id_prov}, Nombre: {nombre}, Cat: {categoria}, Tel: {contacto}")

    con = conectar_db()
    try:
        con.execute('''
            REPLACE INTO proveedores (id, nombre, categoria, contacto)
            VALUES (?, ?, ?, ?)
        ''', (id_prov, nombre, categoria, contacto))
        con.commit()
        print("¡Guardado con éxito en la base de datos!")
    except Exception as e:
        print(f"ERROR DE SQL: {e}")
    finally:
        con.close()
    
    return redirect(url_for('proveedores'))

#============================
# --- ACTUALIZAR PRODUCTO ---
#============================

@app.route('/actualizar_producto', methods=['POST'])
@login_required
def actualizar_producto():
    id_prod = request.form.get('id')
    nombre = request.form.get('nombre')
    # Convertimos a int para poder comparar (importante manejar el error si vienen vacíos)
    try:
        s_actual = int(request.form.get('stock_actual') or 0)
        s_maximo = int(request.form.get('stock_maximo') or 0)
        s_minimo = int(request.form.get('stock_minimo') or 0)
    except ValueError:
        return "Error: Los valores de stock deben ser numéricos", 400

    id_proveedor = request.form.get('id_proveedor')

    # LÓGICA DE CONTROL: Si el actual supera al máximo, lo igualamos al máximo
    if s_actual > s_maximo:
        s_actual = s_maximo
        print(f"Aviso: Stock de {nombre} limitado al máximo permitido ({s_maximo}).")

    con = conectar_db()
    try:
        con.execute('''
            REPLACE INTO Productos (id, nombre, stock_actual, stock_minimo, id_proveedor, stock_maximo)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (id_prod, nombre, s_actual, s_minimo, id_proveedor, s_maximo))
        con.commit()
    except Exception as e:
        print(f"ERROR DE SQL: {e}")
    finally:
        con.close()
    
    return redirect(url_for('dashboard'))


@app.route('/api/pedidos_mes/<mes>')
@login_required
def api_pedidos_mes(mes):
    # Diccionario para convertir el nombre del mes a número
    meses_map = {"ENE":"01", "FEB":"02", "MAR":"03", "ABR":"04", "MAY":"05", "JUN":"06",
                 "JUL":"07", "AGO":"08", "SEP":"09", "OCT":"10", "NOV":"11", "DIC":"12"}
    
    num_mes = meses_map.get(mes.upper(), "01")
    
    con = conectar_db()
    con.row_factory = sqlite3.Row
    
    # Buscamos los vales reales de ese mes
    pedidos = con.execute('''
        SELECT Fecha, codigo_vale 
        FROM vales_pedido 
        WHERE strftime('%m', Fecha) = ?
        ORDER BY Fecha DESC
    ''', (num_mes,)).fetchall()
    
    con.close()
    
    # Convertimos a lista de diccionarios para enviar como JSON
    lista_pedidos = [{"fecha": p["Fecha"], "codigo": p["codigo_vale"]} for p in pedidos]
    return jsonify(lista_pedidos)


@app.route('/test-menu')
def test_menu():
    return render_template('test_pagina.html')




    
from flask import Flask, render_template 

if __name__ == '__main__':
   app.run(debug=True, host='0.0.0.0', port=5001)

#==============================================================
# --- EL PUERTO UTILIZADO PARA EJECUTAR EL PROGRAMA ES 5001 ---
#==============================================================