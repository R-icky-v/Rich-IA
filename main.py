import telebot
from telebot import types
from dotenv import load_dotenv
import os
from datetime import datetime
import json
import threading
import time
import shutil
import requests 

load_dotenv()
bot = telebot.TeleBot("8149029077:AAHuHO9C4grWy4YRvc6z-d4aIrVWxtwFtXE")
# Sistema Keep-Alive para Render
KEEP_ALIVE_INTERVAL = 600  # 10 minutos (más seguro que 13)
KEEP_ALIVE_URL = None  # Se configurará automáticamente
# Estructuras en memoria:
user_notes = {}   # { user_id: [ {"tag": str, "title": str, "text": str, "ts": datetime}, ... ] }
user_names = {}   # { user_id: "Nombre" }
user_temp = {}    # { user_id: {"pending_tag": str, "pending_title": str} }

# Etiquetas disponibles con sus iconos específicos
TAG_ICONS = {
    "Trabajo": "💼",
    "Estudio": "📚",
    "Personal": "🏠",
    "Emprendimiento": "🚀",
    "Amor": "❤️",
    "Social": "👥"
}

# Sistema de respaldo mejorado
BACKUP_DIR = "backups"
MAIN_BACKUP_FILE = os.path.join(BACKUP_DIR, "rich_ai_data_backup.json")
BACKUP_INTERVAL = 300  # Segundos (5 minutos)
BACKUP_VERSIONS = 5    # Número de versiones de respaldo a mantener
SAVE_ON_CHANGES = True # Guardar en cambios importantes además del intervalo

# Sistema de imágenes - Directorio y rutas de imágenes
# Estableciendo rutas absolutas para evitar problemas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images")

# Definición de rutas absolutas para las imágenes
RICH_WELCOME_IMG = os.path.join(IMAGES_DIR, "rich_welcome.png")
RICH_THINKING_IMG = os.path.join(IMAGES_DIR, "rich_thinking.png")
RICH_SUCCESS_IMG = os.path.join(IMAGES_DIR, "rich_success.png")
RICH_SAD_IMG = os.path.join(IMAGES_DIR, "rich_sad.png")

# Asegurar que los directorios existan
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)
if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)
    print(f"⚠️ El directorio de imágenes no existía y ha sido creado: {IMAGES_DIR}")
    print("Por favor coloca las imágenes necesarias en este directorio antes de continuar.")

# Función para enviar mensajes con imágenes
def send_message_with_image(chat_id, text, image_path, reply_markup=None, parse_mode="Markdown"):
    """
    Envía un mensaje con una imagen adjunta

    Args:
        chat_id: ID del chat
        text: Texto del mensaje
        image_path: Ruta a la imagen a enviar
        reply_markup: Teclado opcional
        parse_mode: Modo de parseo del texto

    Returns:
        Message: Objeto mensaje enviado
    """
    try:
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                return bot.send_photo(
                    chat_id, 
                    photo, 
                    caption=text, 
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
        else:
            print(f"⚠️ Imagen no encontrada: {image_path}")
            # Caer de vuelta a envío de mensaje sin imagen
            return bot.send_message(
                chat_id,
                text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"❌ Error al enviar imagen {image_path}: {e}")
        # En caso de error, enviar solo el mensaje
        return bot.send_message(
            chat_id,
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )

# --- SISTEMA DE RESPALDO MEJORADO ---
def save_backup(force_rotation=False):
    """Guarda los datos en un archivo JSON como respaldo con sistema de rotación"""
    backup_data = {
        "user_notes": {},
        "user_names": user_names,
        "backup_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Convertir los objetos datetime a string para serialización JSON
    for user_id, notes in user_notes.items():
        backup_data["user_notes"][str(user_id)] = []
        for note in notes:
            note_copy = note.copy()
            note_copy["ts"] = note_copy["ts"].strftime("%Y-%m-%d %H:%M:%S")
            backup_data["user_notes"][str(user_id)].append(note_copy)

    try:
        # Primero guardar en un archivo temporal para evitar corrupción
        temp_file = os.path.join(BACKUP_DIR, "temp_backup.json")
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)

        # Si el guardado fue exitoso, mover el archivo temporal al archivo principal
        shutil.move(temp_file, MAIN_BACKUP_FILE)

        # Realizar rotación de respaldos si es necesario
        if force_rotation or datetime.now().hour % 6 == 0:  # Rotar cada 6 horas o cuando se fuerce
            rotate_backups()

        print(f"✅ Respaldo guardado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return True
    except Exception as e:
        print(f"❌ Error al guardar respaldo: {e}")
        return False

def rotate_backups():
    """Crea un sistema de rotación de respaldos para mantener múltiples versiones"""
    try:
        # Mover versiones antiguas
        for i in range(BACKUP_VERSIONS-1, 0, -1):
            old_backup = os.path.join(BACKUP_DIR, f"rich_ai_data_backup.{i}.json")
            new_backup = os.path.join(BACKUP_DIR, f"rich_ai_data_backup.{i+1}.json")
            if os.path.exists(old_backup):
                shutil.move(old_backup, new_backup)

        # Copiar el respaldo actual como versión 1
        if os.path.exists(MAIN_BACKUP_FILE):
            backup_1 = os.path.join(BACKUP_DIR, "rich_ai_data_backup.1.json")
            shutil.copy2(MAIN_BACKUP_FILE, backup_1)

        print(f"🔄 Rotación de respaldos completada: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"⚠️ Error en rotación de respaldos: {e}")

def load_backup():
    """Carga los datos desde el archivo de respaldo con sistema de recuperación"""
    global user_notes, user_names

    if not os.path.exists(MAIN_BACKUP_FILE):
        # Intentar buscar en versiones de respaldo si el principal no existe
        backup_found = False
        for i in range(1, BACKUP_VERSIONS + 1):
            backup_file = os.path.join(BACKUP_DIR, f"rich_ai_data_backup.{i}.json")
            if os.path.exists(backup_file):
                print(f"⚠️ Respaldo principal no encontrado. Intentando recuperar versión {i}.")
                if load_backup_file(backup_file):
                    # Si se recuperó correctamente, guardar como archivo principal
                    shutil.copy2(backup_file, MAIN_BACKUP_FILE)
                    backup_found = True
                    break

        if not backup_found:
            print("⚠️ No se encontró ningún archivo de respaldo válido. Iniciando con datos vacíos.")
            return False
    else:
        return load_backup_file(MAIN_BACKUP_FILE)

def load_backup_file(file_path):
    """Carga un archivo de respaldo específico"""
    global user_notes, user_names

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)

        # Restaurar nombres de usuario
        user_names = backup_data.get("user_names", {})

        # Restaurar notas con conversión de string a datetime
        notes_data = backup_data.get("user_notes", {})
        for user_id_str, notes in notes_data.items():
            user_id = int(user_id_str)  # Convertir ID de string a int
            user_notes[user_id] = []
            for note in notes:
                note_copy = note.copy()
                note_copy["ts"] = datetime.strptime(note_copy["ts"], "%Y-%m-%d %H:%M:%S")
                user_notes[user_id].append(note_copy)

        backup_time = backup_data.get("backup_timestamp", "desconocido")
        print(f"✅ Datos restaurados desde respaldo ({backup_time}): {len(user_names)} usuarios, {sum(len(notes) for notes in user_notes.values())} notas")
        return True
    except Exception as e:
        print(f"❌ Error al cargar respaldo {file_path}: {e}")
        return False

def backup_scheduler():
    """Función para programar respaldos periódicos con manejo de errores"""
    consecutive_failures = 0
    while True:
        try:
            time.sleep(BACKUP_INTERVAL)
            success = save_backup(False)  # Respaldo normal

            if success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1

            # Si hay muchos fallos consecutivos, forzar rotación
            if consecutive_failures >= 3:
                print("⚠️ Múltiples fallos de respaldo detectados. Forzando rotación.")
                save_backup(True)  # Forzar rotación
                consecutive_failures = 0

        except Exception as e:
            print(f"❗ Error crítico en el planificador de respaldos: {e}")
            time.sleep(60)  # Esperar un minuto antes de reintentar en caso de error crítico

def keep_alive_scheduler():
    """Función para mantener el servicio activo enviando pings periódicos"""
    global KEEP_ALIVE_URL
    
    # Configurar URL automáticamente desde variable de entorno
    if not KEEP_ALIVE_URL:
        # Priorizar la URL de Render automática
        render_external_url = os.environ.get("RENDER_EXTERNAL_URL")
        app_name = os.environ.get("RENDER_SERVICE_NAME") 
        
        if render_external_url:
            KEEP_ALIVE_URL = render_external_url
            print(f"🌐 URL keep-alive configurada automáticamente: {KEEP_ALIVE_URL}")
        elif app_name:
            KEEP_ALIVE_URL = f"https://{app_name}.onrender.com"
            print(f"🌐 URL keep-alive generada desde nombre del servicio: {KEEP_ALIVE_URL}")
        else:
            print("⚠️ IMPORTANTE: No se pudo configurar la URL automáticamente.")
            print("⚠️ Configura la variable RENDER_EXTERNAL_URL en Render o actualiza KEEP_ALIVE_URL manualmente")
            return  # Salir si no se puede configurar la URL
    
    consecutive_failures = 0
    print(f"🔄 Keep-alive iniciado. URL objetivo: {KEEP_ALIVE_URL}")
    
    while True:
        try:
            time.sleep(KEEP_ALIVE_INTERVAL)
            
            # Hacer ping al endpoint de salud
            response = requests.get(f"{KEEP_ALIVE_URL}/health", timeout=30)
            
            if response.status_code == 200:
                print(f"✅ Keep-alive exitoso: {datetime.now().strftime('%H:%M:%S')}")
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                print(f"⚠️ Keep-alive falló (código {response.status_code}). Fallos consecutivos: {consecutive_failures}")
                
        except requests.RequestException as e:
            consecutive_failures += 1
            print(f"❗ Error en keep-alive: {str(e)[:100]}... Fallos consecutivos: {consecutive_failures}")
            
        except Exception as e:
            print(f"❗ Error crítico en keep-alive: {e}")
            time.sleep(60)  # Esperar más tiempo en caso de error crítico
            
        # Si hay muchos fallos, esperar más tiempo antes del siguiente intento
        if consecutive_failures >= 5:  # Reducido de 3 a 5 para ser menos agresivo
            print("⚠️ Múltiples fallos de keep-alive. Esperando 3 minutos adicionales.")
            time.sleep(180)  # 3 minutos adicionales (reducido de 5)
            consecutive_failures = 0  # Resetear contador después de la pausa


# --- FUNCIONES PARA PRESENTACIÓN MEJORADA (SIN FORMATO TARJETA) ---
def format_note(note, index=None):
    """Crea una presentación de nota sin formato tarjeta pero con emojis"""
    title = note['title']
    tag = note['tag']
    text = note['text']
    ts = note['ts'].strftime("%Y-%m-%d %H:%M")
    tag_icon = TAG_ICONS.get(tag, "🔖")

    # Crear un snippet del texto (primeros 60 caracteres)
    snippet = text[:60] + "..." if len(text) > 60 else text

    # Construir el mensaje
    index_text = f"{index}. " if index is not None else ""

    formatted_note = (
        "✨ ¡Aquí tienes tu nota guardada! ✨\n"
        "➖➖➖➖➖➖➖➖➖➖➖➖\n"
        f"🔢​ Numero : {index_text}\n"
        f"📌 Titulo : **{title}**\n"
        f"{tag_icon} Etiqueta : {tag}\n"
        f"📝 Contenido : {snippet}\n"
        f"🕒 Guardada el : {ts}\n"
        "¡Espero que te sea útil! 😊\n"
        "➖➖➖➖➖➖➖➖➖➖➖➖\n"
    )

    return formatted_note

def create_search_results(notes, date_str=None, name=None):
    """Crea una presentación mejorada para resultados de búsqueda"""
    if not notes:
        if date_str:
            return f"¡Hola! 😊 No encontré ninguna nota para el {date_str}. ¡Quizás es un buen día para planificar algo nuevo! 📝✨"
        return "¡Hola! 😼 Parece que aún no tienes ninguna nota. ¡Anímate a escribir tu primera idea! 💡"

    header = ""
    if date_str:
        header = f"¡Hola, {name}! 😊 Aquí tienes las notas que encontré para el {date_str}:\n\n"
    elif name:
        header = f"📋 ¡Hola 😊, {name}! Aquí están todas tus notas guardadas:\n\n"

    formatted_notes = []
    for i, nota in enumerate(notes, start=1):
        formatted_notes.append(format_note(nota, i))

    footer = "\n\n✨ ¡Sigue organizando tu éxito con Rich AI! 🌟 ¡Siempre aquí para ti! 🤗"

    return header + "\n\n".join(formatted_notes) + footer

# --- HELPERS ---
def make_main_menu(user_name):
    kb = types.InlineKeyboardMarkup()
    # Primera fila: añadir y ver
    kb.add(
        types.InlineKeyboardButton("📝 Añadir nota", callback_data="add_note"),
        types.InlineKeyboardButton("📋 Ver notas", callback_data="show_notes")
    )
    # Segunda fila: borrar y buscar
    kb.add(
        types.InlineKeyboardButton("🗑️ Borrar nota", callback_data="delete_note"),
        types.InlineKeyboardButton("🔍 Buscar nota", callback_data="search_note")
    )
    # Tercera fila: sobre nosotros
    kb.add(
        types.InlineKeyboardButton("💡 Sobre mí", callback_data="about_me")
    )
    return kb

def make_tags_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    for tag in TAG_ICONS.keys():
        icon = TAG_ICONS[tag]
        kb.add(types.InlineKeyboardButton(f"{icon} {tag}", callback_data=f"tag{tag}"))
    return kb

# --- HANDLER PARA NOMBRE ---
def process_name(message):
    user_id = message.from_user.id
    name = message.text.strip()
    if not name:
        msg = bot.send_message(
            message.chat.id,
            "❗ Error: No recibí tu nombre. Por favor, vuelve a intentarlo. 🥺",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_name)
        return
    user_names[user_id] = name
    user_notes.setdefault(user_id, [])

    # Guardar respaldo cuando se añade un nuevo usuario
    if SAVE_ON_CHANGES:
        save_backup()

    welcome_text = (
    f"¡Hola, {name}! 😊 ¡Qué alegría tenerte por aquí!\n\n"
    "Soy Rich IA, tu compañero virtual listo para ayudarte a organizar tus ideas y ser tu apoyo en el día a día. 💖\n"
    "Imagina este espacio como tu bloc de notas personal donde cada pensamiento es bienvenido y cuidado. ✨\n\n"
    "¿Qué te gustaría hacer hoy? ¡Estoy aquí para escucharte! 🤗"
    )
    # Usar imagen de bienvenida
    send_message_with_image(
        message.chat.id,
        welcome_text,
        RICH_WELCOME_IMG,
        reply_markup=make_main_menu(name),
        parse_mode="Markdown"
    )

# --- HANDLERS PRINCIPALES ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    if user_id not in user_names:
        # Primera interacción - usar imagen de bienvenida
        msg = send_message_with_image(
            message.chat.id,
            "¡Hola! 😼 ¡Qué genial tenerte aquí! 😊 Soy Rich IA, tu nuevo amigo y asistente de notas.\n\n"
            "Para que pueda conocerte mejor y hacer nuestra experiencia más personalizada, ¿me dirías tu nombre? 👀​ ",
            RICH_WELCOME_IMG,
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_name)
    else:
        name = user_names[user_id]
        greeting = (
            f"¡Hola otra vez, {name}! 😺 ¡Qué alegría tenerte de vuelta!\n\n"
            "Estoy aquí, listo para seguir siendo tu compañero para organizar esas ideas geniales y ayudarte a alcanzar todas tus metas. ¡Vamos con todo! 💪🏆💡"
        )
        # Usuario recurrente - usar imagen de bienvenida
        send_message_with_image(
            message.chat.id,
            greeting,
            RICH_WELCOME_IMG,
            reply_markup=make_main_menu(name),
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['backup'])
def manual_backup(message):
    """Permite a un administrador forzar un respaldo manualmente"""
    # En un sistema real, deberías verificar si el usuario es administrador
    # Por simplicidad, permitimos que cualquier usuario ejecute el comando
    user_id = message.from_user.id
    if user_id in user_names:
        bot.send_message(
            message.chat.id,
            "⏳ Realizando respaldo manual de los datos...",
            parse_mode="Markdown"
        )
        if save_backup(True):  # Forzar rotación
            # Usar imagen de éxito para el respaldo exitoso
            send_message_with_image(
                message.chat.id,
                "✅ Respaldo completado correctamente.\n"
                f"📊 Usuarios: {len(user_names)}, Notas: {sum(len(notes) for notes in user_notes.values())}",
                RICH_SUCCESS_IMG,
                parse_mode="Markdown"
            )
        else:
            # Usar imagen triste para el error
            send_message_with_image(
                message.chat.id,
                "❌ Error al realizar el respaldo manual.",
                RICH_SAD_IMG,
                parse_mode="Markdown"
            )

# --- CALLBACK QUERIES ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    name = user_names.get(user_id, "amigo")
    data = call.data

    if data == "add_note":
        prompt = (
            f"¡Excelente, {name}! 😊 Ahora, para que puedas organizar tus ideas de la mejor manera, elige una etiqueta para tu nueva nota: 😼\n\n"
            "¿En qué categoría te gustaría guardarla? ​💭"
        )
        # Usar imagen pensativa al iniciar creación de nota
        send_message_with_image(
            call.message.chat.id,
            prompt,
            RICH_THINKING_IMG,
            reply_markup=make_tags_menu(),
            parse_mode="Markdown"
        )

    elif data.startswith("tag"):
        tag = data[3:]  # Asumiendo que "tag" tiene 3 caracteres
        user_temp[user_id] = {"pending_tag": tag}
        msg_text = (
            f"¡Perfecto! ✨ La etiqueta '{tag}' {TAG_ICONS.get(tag, '🔖')} ha sido seleccionada. ¡Excelente elección! ✅\n\n"
            f"Y ahora, {name}, ¿qué título le pondrás a esta increíble nota? 📌 ¡Estoy ansioso por ver tus ideas! ✨"
        )
        # Usar imagen pensativa mientras espera el título
        msg = send_message_with_image(
            call.message.chat.id,
            msg_text,
            RICH_THINKING_IMG,
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_note_title)

    elif data == "show_notes":
        notas = user_notes.get(user_id, [])
        if not notas:
            bot.answer_callback_query(
                call.id,
                "📭 No hay notas registradas. ¡Inicia tu primera nota cuando gustes! ✨",
                show_alert=True
            )
            # Usar imagen triste cuando no hay notas
            send_message_with_image(
                call.message.chat.id,
                "📭 No hay notas registradas. ¡Inicia tu primera nota cuando gustes! ✨",
                RICH_SAD_IMG,
                parse_mode="Markdown",
                reply_markup=make_main_menu(name)
            )
        else:
            # Formato mejorado sin tarjetas y usar imagen de éxito al mostrar notas
            formatted_notes = create_search_results(notas, None, name)
            send_message_with_image(
                call.message.chat.id,
                formatted_notes,
                RICH_SUCCESS_IMG,
                parse_mode="Markdown"
            )
            send_message_with_image(
                call.message.chat.id,
                "¿Se te ocurre alguna otra cosa que quieras hacer? 😊 ¡Estoy aquí para seguir ayudándote con tus ideas! ✨",
                RICH_WELCOME_IMG,
                reply_markup=make_main_menu(name),
                parse_mode="Markdown"
            )

    elif data == "delete_note":
        notas = user_notes.get(user_id, [])
        if not notas:
            bot.answer_callback_query(
                call.id,
                "¡Hola! 😊 Parece que Rich IA aún no tiene notas para eliminar. ¡Anímate a escribir algo cuando tengas una idea! ✨",
                show_alert=True
            )
            # Usar imagen triste cuando no hay notas para eliminar
            send_message_with_image(
                call.message.chat.id,
                f"¡Hola, {name}! 😊 Parece que aún no tienes notas para eliminar. ¡Anímate a crear una cuando tengas alguna idea! ✨ ¡Estoy aquí para ayudarte!",
                RICH_SAD_IMG,
                reply_markup=make_main_menu(name),
                parse_mode="Markdown"
            )
            return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for idx, nota in enumerate(notas, start=1):
            tag_icon = TAG_ICONS.get(nota['tag'], "🔖")
            snippet = (nota['title'][:20] + "…") if len(nota['title']) > 20 else nota['title']
            kb.add(types.InlineKeyboardButton(
                f"{idx}. {tag_icon} {snippet}", callback_data=f"del{idx-1}"
            ))
        kb.add(types.InlineKeyboardButton("↩️ Volver", callback_data="back_to_main"))
        # Usar imagen pensativa al mostrar menú de eliminación
        send_message_with_image(
            call.message.chat.id,
            f"¡Entendido, {name}! 👌 ¿Cuál de estas notas deseas eliminar? 🗑️ ¡Solo házmelo saber!",
            RICH_THINKING_IMG,
            parse_mode="Markdown",
            reply_markup=kb
        )

    elif data == "search_note":
        # Usar imagen pensativa para la búsqueda
        msg = send_message_with_image(
            call.message.chat.id,
            f"¡Claro, {name}! 😊 Para encontrar tus notas por fecha, ¿podrías decirme qué día buscas en formato AAAA-MM-DD? 📅 ¡Así podré ayudarte mejor!",
            RICH_THINKING_IMG,
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_search_date)

    elif data == "about_me":
        about_text = (
            "¡Hola! 👋 Somos el Equipo IODs (Index of Dreams), un grupo de personas con un sueño: crear herramientas que te hagan la vida más fácil. ✨\n\n"
            "Gracias por ser parte de la aventura Rich IA. ¡Tu confianza nos impulsa a seguir creando cosas increíbles para ti! 😊🙏\n\n"
            "¡Conéctate con nosotros en nuestras redes! Nos encanta saber de ti:\n"
            "• 🐦 Tiktok: https://tiktok.com/@iods.index\n"
            "• 💻 Facebook: https://www.facebook.com/iods.index\n"
            "• 📸 Instagram: https://www.instagram.com/iods.index?igsh=aTZhOGR1eG1jZDh5\n\n"
            "¡Juntos soñamos más grande! 🚀 ¡Gracias por tu apoyo! 💖"
)
        # Usar imagen de bienvenida para el apartado "Sobre mí"
        send_message_with_image(
            call.message.chat.id,
            about_text,
            RICH_WELCOME_IMG,
            parse_mode="Markdown",
            reply_markup=make_main_menu(name)
        )

    elif data == "back_to_main":
        # Usar imagen de bienvenida para el menú principal
        send_message_with_image(
            call.message.chat.id,
            f"📱 Menú principal — {name}: 👇",
            RICH_WELCOME_IMG,
            parse_mode="Markdown",
            reply_markup=make_main_menu(name)
        )

    elif data.startswith("del"):
        idx = int(data[3:])  # Asumiendo que "del" tiene 3 caracteres
        notas = user_notes.get(user_id, []) 
        if 0 <= idx < len(notas):
            deleted_note = notas.pop(idx)
            bot.answer_callback_query(call.id, "¡Hecho! ✅ ¡Nota eliminada! 🎉 ¡Tu espacio está un poquito más limpio! ✨")
            # Guardar respaldo después de eliminar
            if SAVE_ON_CHANGES:
                save_backup()

            # Mostrar la nota eliminada con formato mejorado y usar imagen triste
            deleted_formatted = format_note(deleted_note)
            send_message_with_image(
                call.message.chat.id,
                f"¡Listo, {name}! 😊 La nota ha sido eliminada sin problemas. ¡Adiós, adiós! 👋\n\n{deleted_formatted}",
                RICH_SAD_IMG,
                parse_mode="Markdown",
                reply_markup=make_main_menu(name)
            )
        else:
            # Usar imagen triste para el error
            send_message_with_image(
                call.message.chat.id,
                f"{name}, hubo un error al eliminar la nota. Inténtalo de nuevo. ⚠️",
                RICH_SAD_IMG,
                parse_mode="Markdown",
                reply_markup=make_main_menu(name)
            )

# --- FUNCIONES DE PROCESO DE TÍTULO Y CONTENIDO ---
def process_note_title(message):
    user_id = message.from_user.id
    name = user_names.get(user_id, "amigo")
    title = message.text.strip()
    if not title:
        # Usar imagen triste para el error
        msg = send_message_with_image(
            message.chat.id,
            "¡Mmm, parece que hubo un pequeño problema con el título! 🤔 ¿Podrías ingresarlo de nuevo, por favor? 😊 ¡Así tu nota quedará perfectamente organizada!",
            RICH_SAD_IMG,
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_note_title)
        return
    user_temp[user_id]['pending_title'] = title
    msg_text = (
        f"¡Genial, {name}! 😊 El título '{title}' quedó perfecto. ✅ ¡Ya casi estamos!\n\n"
        "Ahora, cuéntame, ¿qué quieres plasmar en esta nota tan importante? 📝 ¡Estoy listo para leerte! ✨"
    )
    # Usar imagen pensativa mientras espera el contenido
    msg = send_message_with_image(
        message.chat.id,
        msg_text,
        RICH_THINKING_IMG,
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_note_content)

def process_note_content(message):
    user_id = message.from_user.id
    name = user_names.get(user_id, "amigo")
    content = message.text.strip()
    temp = user_temp.get(user_id, {})
    tag = temp.get('pending_tag')
    title = temp.get('pending_title')
    if not tag or not title:
        # Usar imagen triste para el error
        send_message_with_image(
            message.chat.id,
            "❌ Ha ocurrido un error. Regresando al menú principal.",
            RICH_SAD_IMG,
            reply_markup=make_main_menu(name),
            parse_mode="Markdown"
        )
        return
    if not content:
        # Usar imagen triste para el error
        msg = send_message_with_image(
            message.chat.id,
        "¡Un momento! 😊 Parece que el contenido de tu nota está vacío. ¿Podrías agregar algunas ideas o detalles? 📝 ¡Estoy seguro de que tienes algo genial para escribir!",
            RICH_SAD_IMG,
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_note_content)
        return
    nota = {"tag": tag, "title": title, "text": content, "ts": datetime.now()}
    user_notes.setdefault(user_id, []).append(nota)
    user_temp.pop(user_id, None)

    # Guardar respaldo después de añadir una nota
    if SAVE_ON_CHANGES:
        save_backup()

    # Crear formato para la nueva nota
    note_formatted = format_note(nota)

    final_msg = (
        f"¡Felicidades, {name}! 🎉 Tu nota ha sido guardada exitosamente. ¡Qué bien! 😊\n\n"
        f"Aquí está tu creación:\n\n"
        f"{note_formatted}\n\n"
        "¡Gracias por permitirme ser parte de esto! ¡Confía siempre en Rich IA! 🌟 ¡Estoy aquí para ti! 🤗"
    )
    # Usar imagen de éxito al guardar la nota
    send_message_with_image(
        message.chat.id,
        final_msg,
        RICH_SUCCESS_IMG,
        parse_mode="Markdown",
        reply_markup=make_main_menu(name)
    )

# --- FUNCIONES DE PROCESO DE FECHA ---
def process_search_date(message):
    user_id = message.from_user.id
    name = user_names.get(user_id, "amigo")
    date_str = message.text.strip()
    try:
        search_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        msg = bot.send_message(
            message.chat.id,
        "¡Ups! 😅 Parece que el formato de la fecha no es el correcto. Por favor, asegúrate de usar el formato AAAA-MM-DD. 🙏 ¡Así podremos buscar tu nota sin problemas! 📅",
        )
        bot.register_next_step_handler(msg, process_search_date)
        return
    notas = user_notes.get(user_id, [])
    filtered = [n for n in notas if n['ts'].date() == search_date]

    # Usar formato mejorado para los resultados de búsqueda
    formatted_results = create_search_results(filtered, date_str, name)
    bot.send_message(
        message.chat.id,
        formatted_results,
        parse_mode="Markdown"
    )

    bot.send_message(
        message.chat.id,
        "¿Qué nuevas ideas tienes en mente ahora? 💡 ¡Cuéntame! 👇",
        reply_markup=make_main_menu(name)
    )

# Agregar esto al final de tu archivo, justo antes del bloque "if __name__ == "__main__":"
def setup_web_server():
    """Configura un servidor web simple para mantener el servicio activo en Render"""
    try:
        from flask import Flask, jsonify
        import threading
        
        app = Flask(__name__)
        
        @app.route('/')
        def index():
            stats = {
                "status": "activo",
                "usuarios": len(user_names),
                "notas_totales": sum(len(notes) for notes in user_notes.values()),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": "Rich AI v1.0"
            }
            return f"""
            ¡Rich AI está activo! 🚀<br>
            Status: {stats['status']}<br>
            Usuarios: {stats['usuarios']}<br>
            Notas: {stats['notas_totales']}<br>
            Última actualización: {stats['timestamp']}
            """
        
        @app.route('/health')
        def health():
            return jsonify({
                "status": "OK", 
                "timestamp": datetime.now().isoformat(),
                "service": "Rich AI Bot"
            }), 200
        
        @app.route('/ping')
        def ping():
            return jsonify({"response": "pong", "timestamp": datetime.now().isoformat()}), 200
        
        # Configuración de puerto más robusta
        port = int(os.environ.get("PORT", 10000))  # Render usa 10000 por defecto
        
        def run_server():
            # Configuración de producción para Render
            app.run(
                host="0.0.0.0", 
                port=port, 
                debug=False, 
                use_reloader=False,
                threaded=True  # Importante para manejar múltiples requests
            )
        
        # Iniciar el servidor web en un hilo separado
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        print(f"🌐 Servidor web iniciado en 0.0.0.0:{port}")
        
        # Esperar un momento para que el servidor se inicie
        time.sleep(2)
        return True
        
    except ImportError as e:
        print(f"⚠️ Error de importación: {e}")
        print("⚠️ Para desplegar en Render, asegúrate de tener Flask en requirements.txt")
        return False
    except Exception as e:
        print(f"❌ Error al iniciar servidor web: {e}")
        return False
# --- INICIAR POLLING ---

# Modificar la sección final del código:
if __name__ == "__main__":
    print("🚀 Rich AI arrancando...")
    load_dotenv()
    load_backup()
    save_backup()

    # Iniciar servidor web para Render (SOLO UNA VEZ)
    web_server_started = setup_web_server()
    
    # Iniciar hilo para respaldos automáticos
    backup_thread = threading.Thread(target=backup_scheduler, daemon=True)
    backup_thread.start()
    
    # Iniciar hilo para keep-alive solo si el servidor web se inició correctamente
    if web_server_started:
        keep_alive_thread = threading.Thread(target=keep_alive_scheduler, daemon=True)
        keep_alive_thread.start()
        print("🔄 Sistema keep-alive iniciado")
    else:
        print("⚠️ Keep-alive no iniciado - servidor web no disponible")

    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("🛑 Apagado manual detectado. Guardando respaldo final...")
        save_backup(True)
        print("✅ Respaldo final completado. ¡Hasta pronto! 👋")
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        print("⚠️ Intentando guardar respaldo de emergencia...")
        save_backup(True)