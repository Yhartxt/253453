from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_super_segura_12345'

# Configuración de MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Cambiar si tienes contraseña en XAMPP
app.config['MYSQL_DB'] = 'trigonometria_app'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# Ruta principal - Página de inicio
@app.route('/')
def index():
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

# Ruta de login/registro
@app.route('/auth')
def auth():
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('auth.html')

# API - Registro de usuario
@app.route('/api/registro', methods=['POST'])
def registro():
    data = request.get_json()
    nombre = data.get('nombre')
    email = data.get('email')
    password = data.get('password')
    
    if not nombre or not email or not password:
        return jsonify({'success': False, 'message': 'Todos los campos son requeridos'}), 400
    
    if len(password) < 8:
        return jsonify({'success': False, 'message': 'La contraseña debe tener al menos 8 caracteres'}), 400
    
    cursor = mysql.connection.cursor()
    
    # Verificar si el email ya existe
    cursor.execute('SELECT id FROM usuarios WHERE email = %s', (email,))
    if cursor.fetchone():
        return jsonify({'success': False, 'message': 'Este email ya está registrado'}), 400
    
    # Crear usuario
    password_hash = generate_password_hash(password)
    cursor.execute(
        'INSERT INTO usuarios (nombre, email, password) VALUES (%s, %s, %s)',
        (nombre, email, password_hash)
    )
    mysql.connection.commit()
    usuario_id = cursor.lastrowid
    cursor.close()
    
    # Iniciar sesión
    session['usuario_id'] = usuario_id
    session['nombre'] = nombre
    
    return jsonify({'success': True, 'message': 'Usuario registrado exitosamente'})

# API - Login
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email y contraseña son requeridos'}), 400
    
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT id, nombre, password FROM usuarios WHERE email = %s', (email,))
    usuario = cursor.fetchone()
    cursor.close()
    
    if not usuario or not check_password_hash(usuario['password'], password):
        return jsonify({'success': False, 'message': 'Email o contraseña incorrectos'}), 401
    
    # Iniciar sesión
    session['usuario_id'] = usuario['id']
    session['nombre'] = usuario['nombre']
    
    return jsonify({'success': True, 'message': 'Login exitoso'})

# API - Logout
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

# Dashboard principal
@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('auth'))
    
    return render_template('dashboard.html')

# API - Obtener datos del usuario
@app.route('/api/usuario')
def obtener_usuario():
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    
    cursor = mysql.connection.cursor()
    cursor.execute(
        'SELECT nombre, email, xp, nivel, racha_dias, ultima_actividad FROM usuarios WHERE id = %s',
        (session['usuario_id'],)
    )
    usuario = cursor.fetchone()
    
    # Actualizar racha
    if usuario:
        hoy = datetime.now().date()
        ultima = usuario['ultima_actividad']
        
        if ultima:
            if ultima < hoy:
                diferencia_dias = (hoy - ultima).days
                if diferencia_dias == 1:
                    # Continua la racha
                    cursor.execute(
                        'UPDATE usuarios SET racha_dias = racha_dias + 1, ultima_actividad = %s WHERE id = %s',
                        (hoy, session['usuario_id'])
                    )
                    usuario['racha_dias'] += 1
                elif diferencia_dias > 1:
                    # Se rompió la racha
                    cursor.execute(
                        'UPDATE usuarios SET racha_dias = 1, ultima_actividad = %s WHERE id = %s',
                        (hoy, session['usuario_id'])
                    )
                    usuario['racha_dias'] = 1
                mysql.connection.commit()
        else:
            # Primera vez
            cursor.execute(
                'UPDATE usuarios SET racha_dias = 1, ultima_actividad = %s WHERE id = %s',
                (hoy, session['usuario_id'])
            )
            usuario['racha_dias'] = 1
            mysql.connection.commit()
    
    cursor.close()
    return jsonify(usuario)

# API - Obtener lecciones con progreso
@app.route('/api/lecciones')
def obtener_lecciones():
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    
    cursor = mysql.connection.cursor()
    cursor.execute('''
        SELECT l.*, 
               COALESCE(p.completada, 0) as completada,
               COALESCE(p.puntuacion, 0) as puntuacion
        FROM lecciones l
        LEFT JOIN progreso_usuario p ON l.id = p.leccion_id AND p.usuario_id = %s
        ORDER BY l.orden
    ''', (session['usuario_id'],))
    
    lecciones = cursor.fetchall()
    
    # Determinar qué lecciones están desbloqueadas
    for i, leccion in enumerate(lecciones):
        if i == 0:
            leccion['desbloqueada'] = True
        else:
            # Desbloquear si la anterior está completada
            leccion['desbloqueada'] = lecciones[i-1]['completada']
    
    cursor.close()
    return jsonify(lecciones)

# Página de lección
@app.route('/leccion/<int:leccion_id>')
def leccion(leccion_id):
    if 'usuario_id' not in session:
        return redirect(url_for('auth'))
    
    return render_template('leccion.html', leccion_id=leccion_id)

# API - Obtener contenido de lección
@app.route('/api/leccion/<int:leccion_id>')
def obtener_leccion(leccion_id):
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM lecciones WHERE id = %s', (leccion_id,))
    leccion = cursor.fetchone()
    
    if not leccion:
        return jsonify({'success': False, 'message': 'Lección no encontrada'}), 404
    
    cursor.close()
    return jsonify(leccion)

# Página de ejercicios
@app.route('/ejercicios/<int:leccion_id>')
def ejercicios(leccion_id):
    if 'usuario_id' not in session:
        return redirect(url_for('auth'))
    
    return render_template('ejercicios.html', leccion_id=leccion_id)

# API - Obtener ejercicios de una lección
@app.route('/api/ejercicios/<int:leccion_id>')
def obtener_ejercicios(leccion_id):
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM ejercicios WHERE leccion_id = %s ORDER BY id', (leccion_id,))
    ejercicios = cursor.fetchall()
    
    # Parsear JSON de opciones
    for ejercicio in ejercicios:
        if ejercicio['opciones']:
            ejercicio['opciones'] = json.loads(ejercicio['opciones'])
    
    cursor.close()
    return jsonify(ejercicios)

# API - Verificar respuesta
@app.route('/api/verificar_respuesta', methods=['POST'])
def verificar_respuesta():
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    
    data = request.get_json()
    ejercicio_id = data.get('ejercicio_id')
    respuesta = data.get('respuesta')
    
    cursor = mysql.connection.cursor()
    cursor.execute(
        'SELECT respuesta_correcta, explicacion, puntos FROM ejercicios WHERE id = %s',
        (ejercicio_id,)
    )
    ejercicio = cursor.fetchone()
    
    if not ejercicio:
        return jsonify({'success': False, 'message': 'Ejercicio no encontrado'}), 404
    
    correcta = respuesta.strip() == ejercicio['respuesta_correcta'].strip()
    
    # Guardar respuesta
    cursor.execute(
        'INSERT INTO respuestas_usuario (usuario_id, ejercicio_id, respuesta_dada, correcta) VALUES (%s, %s, %s, %s)',
        (session['usuario_id'], ejercicio_id, respuesta, correcta)
    )
    
    # Si es correcta, sumar puntos
    if correcta:
        cursor.execute(
            'UPDATE usuarios SET xp = xp + %s WHERE id = %s',
            (ejercicio['puntos'], session['usuario_id'])
        )
        
        # Actualizar nivel (cada 100 XP = 1 nivel)
        cursor.execute('SELECT xp FROM usuarios WHERE id = %s', (session['usuario_id'],))
        nuevo_xp = cursor.fetchone()['xp']
        nuevo_nivel = (nuevo_xp // 100) + 1
        cursor.execute('UPDATE usuarios SET nivel = %s WHERE id = %s', (nuevo_nivel, session['usuario_id']))
    
    mysql.connection.commit()
    cursor.close()
    
    return jsonify({
        'correcta': correcta,
        'explicacion': ejercicio['explicacion'],
        'puntos': ejercicio['puntos'] if correcta else 0
    })

# API - Completar lección
@app.route('/api/completar_leccion', methods=['POST'])
def completar_leccion():
    if 'usuario_id' not in session:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    
    data = request.get_json()
    leccion_id = data.get('leccion_id')
    puntuacion = data.get('puntuacion', 0)
    
    cursor = mysql.connection.cursor()
    
    # Verificar si ya existe progreso
    cursor.execute(
        'SELECT id FROM progreso_usuario WHERE usuario_id = %s AND leccion_id = %s',
        (session['usuario_id'], leccion_id)
    )
    progreso = cursor.fetchone()
    
    if progreso:
        # Actualizar
        cursor.execute(
            'UPDATE progreso_usuario SET completada = 1, puntuacion = %s, fecha_completado = NOW() WHERE usuario_id = %s AND leccion_id = %s',
            (puntuacion, session['usuario_id'], leccion_id)
        )
    else:
        # Crear
        cursor.execute(
            'INSERT INTO progreso_usuario (usuario_id, leccion_id, completada, puntuacion, fecha_completado) VALUES (%s, %s, 1, %s, NOW())',
            (session['usuario_id'], leccion_id, puntuacion)
        )
    
    # Sumar XP de la lección
    cursor.execute('SELECT xp_recompensa FROM lecciones WHERE id = %s', (leccion_id,))
    xp_recompensa = cursor.fetchone()['xp_recompensa']
    
    cursor.execute(
        'UPDATE usuarios SET xp = xp + %s WHERE id = %s',
        (xp_recompensa, session['usuario_id'])
    )
    
    mysql.connection.commit()
    cursor.close()
    
    return jsonify({'success': True, 'xp_ganado': xp_recompensa})

if __name__ == '__main__':
    app.run(debug=True, port=5000)