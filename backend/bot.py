import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
import requests
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# Configuration
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8888")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://your-mini-app-url.com")
DB_PATH = "calorie_tracker.db"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def get_user_email_by_telegram(telegram_id):
    """Internal check to link telegram_id to email."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM users WHERE telegram_id = ?", (str(telegram_id),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message and dashboard link."""
    user = update.effective_user
    email = get_user_email_by_telegram(user.id)
    
    if not email:
        welcome_text = (
            f"Hi {user.first_name}! 🥗\n\n"
            "I'm your AI Calorie Tracker. To get started, please **Register** on the web dashboard to link your account.\n\n"
            "Once you've set up your account, I'll be able to track your meals here!"
        )
        keyboard = [
            [InlineKeyboardButton("🚀 Register & Link Account", url=f"{FRONTEND_URL}/register?telegram_id={user.id}")]
        ]
    else:
        welcome_text = (
            f"Welcome back, {user.first_name}! 🥗\n\n"
            f"Connected to: {email}\n\n"
            "Just send me a photo of your food, and I'll estimate the calories for you."
        )
        keyboard = [
            [InlineKeyboardButton("📊 Open Dashboard", url=FRONTEND_URL)]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process uploaded food images."""
    user = update.effective_user
    email = get_user_email_by_telegram(user.id)
    
    if not email:
        await update.message.reply_text(
            "Please log in to the web dashboard first to link your account! 📲",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Login Here", url=FRONTEND_URL)]])
        )
        return

    photo_file = await update.message.photo[-1].get_file()
    description = update.message.caption
    status_msg = await update.message.reply_text("Thinking... 🔍🍎")
    
    file_path = f"temp_{user.id}.jpg"
    await photo_file.download_to_drive(file_path)
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (f"meal_{user.id}.jpg", f, 'image/jpeg')}
            params = {'description': description}
            response = requests.post(f"{BACKEND_URL}/upload-meal-internal/{email}", files=files, params=params)
        
        if response.status_code == 200:
            data = response.json()
            result_text = (
                f"✅ **{data.get('food')}**\n"
                f"🔥 **{data.get('calories')} kcal**\n"
                f"🥩 P: {data.get('protein')}g | 🍞 C: {data.get('carbs')}g | 🥑 F: {data.get('fat')}g\n\n"
                f"Daily Total: {data.get('total_today')} kcal"
            )
        elif response.status_code == 429:
            result_text = "⚠️ **AI Quota Limit Reached**\n\nThe app is working fine, but my AI energy is temporarily drained! This is an external limit from Google. Please try again in a few minutes. 🔋"
        else:
            result_text = "Sorry, I had trouble saving that to your account. 🥪"
            
        await status_msg.edit_text(result_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 View Stats", url=FRONTEND_URL)]]), parse_mode='Markdown')
            
    except Exception as e:
        logging.error(f"Error in handle_photo: {e}")
        await status_msg.edit_text("Oops! Something went wrong. 🛠️")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text-only meal descriptions."""
    user = update.effective_user
    email = get_user_email_by_telegram(user.id)
    
    if not email:
        return # Ignore text from unlinked users to avoid noise

    description = update.message.text
    if len(description) < 3: return # Ignore very short messages

    status_msg = await update.message.reply_text("Estimating from description... 📝🥗")
    
    try:
        # Send text-only to backend
        response = requests.post(f"{BACKEND_URL}/upload-meal-internal/{email}", data={'description': description})
        
        if response.status_code == 200:
            data = response.json()
            result_text = (
                f"✅ **{data.get('food')}** (Estimated)\n"
                f"🔥 **{data.get('calories')} kcal**\n"
                f"🥩 P: {data.get('protein')}g | 🍞 C: {data.get('carbs')}g | 🥑 F: {data.get('fat')}g\n\n"
                f"Daily Total: {data.get('total_today')} kcal"
            )
        elif response.status_code == 429:
            result_text = "⚠️ **AI Quota Limit Reached**\n\nMy brain is temporarily overloaded! This is an external limit, not an app error. Please try again in a minute or two. 🔋"
        else:
            result_text = "Sorry, I couldn't estimate that from your description. 🥪"
            
        await status_msg.edit_text(result_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 View Stats", url=FRONTEND_URL)]]), parse_mode='Markdown')
            
    except Exception as e:
        logging.error(f"Error in handle_text: {e}")
        await status_msg.edit_text("Oops! Something went wrong. 🛠️")

if __name__ == '__main__':
    if not TOKEN:
        print("Please set TELEGRAM_BOT_TOKEN in your .env file")
    else:
        application = ApplicationBuilder().token(TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
        print("Bot is running...")
        application.run_polling()
