import logging
import os
import random
from datetime import datetime, timedelta, time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Configuración
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
SCOPES = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/spreadsheets']

# Días permitidos por vendedor
DIAS_POR_VENDEDOR = {
    "tdt": [0, 2],   # Lunes y Miércoles
    "nhn": [3],      # Jueves
    "cla": [0, 2],   # Lunes y Miércoles
    "nt": [1]        # Martes
}

def get_credentials():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

def crear_eventos_aleatorios_y_sheets(fecha_inicio, fecha_fin, descripcion, hora_evento, cantidad_eventos, plan, vendedor):
    creds = get_credentials()
    calendar_service = build('calendar', 'v3', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    sheet_id = "181dqhlWu8aAzmUfnjeYil16drYHT6zIpBiiSelCC0QA"
    hoja = "Hoja 1"

    dias_permitidos = DIAS_POR_VENDEDOR.get(vendedor.lower(), list(range(7)))
    fechas_validas = [
        fecha_inicio + timedelta(days=i)
        for i in range((fecha_fin - fecha_inicio).days + 1)
        if (fecha_inicio + timedelta(days=i)).weekday() in dias_permitidos
    ]

    if len(fechas_validas) < cantidad_eventos:
        raise ValueError("No hay suficientes días válidos para este vendedor en el rango dado.")

    fechas_evento = sorted(random.sample(fechas_validas, cantidad_eventos))
    eventos_creados = []

    for fecha in fechas_evento:
        inicio_datetime = datetime.combine(fecha, hora_evento)
        fin_datetime = inicio_datetime + timedelta(hours=1)
        evento = {
            'summary': descripcion,
            'start': {
                'dateTime': inicio_datetime.isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            },
            'end': {
                'dateTime': fin_datetime.isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            }
        }
        calendar_service.events().insert(calendarId='primary', body=evento).execute()
        eventos_creados.append(inicio_datetime.strftime("%d-%m %H:%M"))

    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{hoja}!A1:D1",
        valueInputOption="RAW",
        body={"values": [["Publicidad", "Paquete", "Vendedor", "Fecha inicio"]]}
    ).execute()

    fila = [[descripcion, plan, vendedor.upper(), fecha_inicio.strftime("%d-%m")]]
    sheets_service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{hoja}!A2",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": fila}
    ).execute()

    return eventos_creados

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hola! Enviame el rango de fechas, descripción, horario, vendedor y plan.\n"
        "Formato:\n`"
        "DD-MM, DD-MM, descripcion, HHhs o HH:MMhs, vendedor, plan`\n"
        "Ejemplo:\n`"
        "14-05, 20-05, Campaña X, 19:30hs, TDT, intermedio`\n"
        "Planes: basico (2), intermedio (4), avanzado (6).\n"
        "Vendedores: TDT, NHN, CLA, NT.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        texto = update.message.text
        partes = [p.strip() for p in texto.split(",")]
        if len(partes) != 6:
            await update.message.reply_text("❌ Formato incorrecto. Usá /start para ver el formato correcto.")
            return

        fecha_inicio_str, fecha_fin_str, descripcion, horario_str, vendedor, plan = partes
        anio = datetime.now().year
        fecha_inicio = datetime.strptime(f"{fecha_inicio_str}-{anio}", "%d-%m-%Y")
        fecha_fin = datetime.strptime(f"{fecha_fin_str}-{anio}", "%d-%m-%Y")

        if not horario_str.endswith("hs"):
            raise ValueError("El horario debe terminar en 'hs'.")

        hora_str = horario_str[:-2]  # quitar 'hs'
        if ":" in hora_str:
            hora, minuto = map(int, hora_str.split(":"))
        else:
            hora = int(hora_str)
            minuto = 0

        if not (0 <= hora <= 23 and 0 <= minuto <= 59):
            raise ValueError("Horario inválido.")

        hora_evento = time(hour=hora, minute=minuto)

        plan = plan.lower()
        cantidad_eventos = {"basico": 2, "intermedio": 4, "avanzado": 6}.get(plan)
        if not cantidad_eventos:
            raise ValueError("Plan inválido.")

        fechas = crear_eventos_aleatorios_y_sheets(
            fecha_inicio, fecha_fin, descripcion, hora_evento, cantidad_eventos, plan, vendedor
        )

        if fechas:
            await update.message.reply_text("✅ Eventos creados:\n" + "\n".join(f"- {f}" for f in fechas))
        else:
            await update.message.reply_text("❌ No se pudieron crear eventos.")

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

def main():
    with open("token.txt") as f:
        TOKEN = f.read().strip()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
