Stock & Roll
Sistema web de gestión de inventario y trazabilidad en tiempo real desarrollado para el Proyecto de Fin de Grado (SMR).

Descripción
Stock & Roll es una solución de gestión logística basada en arquitectura cliente-servidor que permite la sincronización síncrona de inventarios entre fábrica y oficina, optimizando tiempos de registro y eliminando el uso de papel.

Tecnologías Utilizadas
Backend: Python 3.10 con framework Flask.

Base de Datos: SQLite.

Infraestructura: Virtualización con VirtualBox (Modo Puente).

Frontend: HTML5, CSS3 (Diseño responsivo).

Guía de Ejecución
1. Requisitos previos
Tener instalado Python 3.x en el sistema.

2. Configuración del entorno
Abre una terminal en la carpeta raíz del proyecto.

Crea un entorno virtual:

Bash
python -m venv venv
# En Windows:
venv\Scripts\activate
Instala las dependencias necesarias:

Bash
pip install flask

3. Ejecución del Servidor
Para lanzar la aplicación y permitir conexiones desde otros dispositivos:

Bash
python app.py
El servidor estará escuchando en http://0.0.0.0:5001.

Configuración de Red para Pruebas
Para que el servidor sea accesible desde otros nodos:

Asegúrate de que el equipo esté conectado a la misma red.

Verifica la IP local con ipconfig.

Accede desde cualquier navegador utilizando: http://[IP_DEL_SERVIDOR]:5001

Nota: Se requiere tener abierto el puerto TCP 5001 en el Firewall del sistema.