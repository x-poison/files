import os
import pymongo
import telebot
from telebot import types
from flask import Flask, request, abort
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')
ALLOWED_CHANNEL_ID = os.getenv('ALLOWED_CHANNEL_ID') 
ALLOWED_USER_ID = int(os.getenv('ALLOWED_USER_ID'))

try:
    client = pymongo.MongoClient(MONGO_URI)
    db = client['Hospital']
    collection = db['links']
    print("Successfully connected to MongoDB.")
except Exception as e:
    print(f"Error connecting to MongoDB: {str(e)}")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

STATE_NONE = 'none'
STATE_AWAITING_LINK = 'awaiting_link'
STATE_AWAITING_PASSKEY = 'awaiting_passkey'
STATE_AWAITING_DOWNLOAD_PASSKEY = 'awaiting_download_passkey'

user_states = {}

def is_user_in_channel(user_id):
    try:
        chat_member = bot.get_chat_member(ALLOWED_CHANNEL_ID, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Error checking user membership: {str(e)}")
        return False

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type != 'private':
        bot_username = bot.get_me().username
        private_chat_url = f"https://t.me/{bot_username}?start=private"
        private_chat_button = types.InlineKeyboardButton("start", url=private_chat_url)
        markup = types.InlineKeyboardMarkup()
        markup.add(private_chat_button)
        bot.send_message(message.chat.id, "Send this in pm, Please!", reply_markup=markup)
        return

    if is_user_in_channel(message.from_user.id):
        markup = types.InlineKeyboardMarkup(row_width=2)
        download_button = types.InlineKeyboardButton('Download', callback_data='download')
        upload_button = types.InlineKeyboardButton('Upload', callback_data='upload')
        help_button = types.InlineKeyboardButton('Help', callback_data='help')
        markup.add(download_button, upload_button, help_button)
        bot.send_message(message.chat.id, "Welcome Please choose Bellow!", reply_markup=markup)
    else:
        join_channel_url = f"https://t.me/abdulmods1"
        join_button = types.InlineKeyboardButton("Join Channel", url=join_channel_url)
        markup = types.InlineKeyboardMarkup()
        markup.add(join_button)
        bot.send_message(message.chat.id, "You must join our channel to use this bot. Please click the button below to join:", reply_markup=markup)

@bot.message_handler(commands=['db'])
def show_db_entries(message):
    if message.chat.type != 'private':
        bot.send_message(message.chat.id, "This bot can only be used in private messages.")
        return

    if message.from_user.id != ALLOWED_USER_ID:
        bot.send_message(message.chat.id, "You are not authorized to use this command.")
        return

    try:
        entries = collection.find()
        if collection.count_documents({}) == 0:
            bot.send_message(message.chat.id, "No entries in the database.")
        else:
            response = "Entries in the database:\n"
            for entry in entries:
                response += f"Link: {entry['link']}, Passkey: {entry['passkey']}\n"
            bot.send_message(message.chat.id, response)
    except Exception as e:
        bot.send_message(message.chat.id, f"Error retrieving entries from database: {str(e)}")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.message.chat.type != 'private':
        bot.send_message(call.message.chat.id, "This bot can only be used in private messages.")
        return

    if call.data == 'help':
        help_text = ("This bot provides the following functionalities:\n"
                     "1. **Download**: Download files (requires validation).\n"
                     "2. **Upload**: Upload files (requires validation).\n"
                     "3. **Help**: Get information about how to use this bot.")
        bot.send_message(call.message.chat.id, help_text, parse_mode='Markdown')
    elif call.data == 'download':
        handle_download(call.message.chat.id)
    elif call.data == 'upload':
        handle_upload(call.message.chat.id)

def handle_download(chat_id):
    bot.send_message(chat_id, "Please enter the passkey to download the link.")
    user_states[chat_id] = {'state': STATE_AWAITING_DOWNLOAD_PASSKEY}

def handle_upload(chat_id):
    bot.send_message(chat_id, "Please send the link you want to upload.")
    user_states[chat_id] = {'state': STATE_AWAITING_LINK}

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state', STATE_NONE) in [STATE_AWAITING_LINK, STATE_AWAITING_PASSKEY, STATE_AWAITING_DOWNLOAD_PASSKEY])
def handle_message(message):
    if message.chat.type != 'private':
        bot.send_message(message.chat.id, "This bot can only be used in private messages.")
        return

    try:
        state = user_states.get(message.chat.id, {'state': STATE_NONE})
        chat_id = message.chat.id

        if state['state'] == STATE_AWAITING_LINK:
            state.update({'state': STATE_AWAITING_PASSKEY, 'link': message.text})
            bot.send_message(chat_id, "Please send the passkey for the link.")
            user_states[chat_id] = state
        elif state['state'] == STATE_AWAITING_PASSKEY:
            link = state.get('link')
            passkey = message.text
            try:
                result = collection.insert_one({'link': link, 'passkey': passkey})
                if result.inserted_id:
                    bot.send_message(chat_id, "Link and passkey have been saved to the database.")
                else:
                    bot.send_message(chat_id, "Failed to save link and passkey to the database.")
            except Exception as e:
                bot.send_message(chat_id, f"Error inserting data into database: {str(e)}")
                print(f"Error inserting data into database: {str(e)}")
            finally:
                user_states[chat_id] = {'state': STATE_NONE}
        elif state['state'] == STATE_AWAITING_DOWNLOAD_PASSKEY:
            passkey = message.text
            try:
                entry = collection.find_one({'passkey': passkey})
                if entry:
                    bot.send_message(chat_id, f"Here is your download link: {entry['link']}")
                else:
                    bot.send_message(chat_id, "Invalid passkey. Please try again.")
            except Exception as e:
                bot.send_message(chat_id, f"Error retrieving data from database: {str(e)}")
            finally:
                user_states[chat_id] = {'state': STATE_NONE}
    except KeyError:
        bot.send_message(chat_id, "An unexpected error occurred. Please try again.")
        user_states[chat_id] = {'state': STATE_NONE}
    except Exception as e:
        print(f"Error handling message: {str(e)}")
        bot.send_message(chat_id, "An unexpected error occurred. Please try again.")
        user_states[chat_id] = {'state': STATE_NONE}

@app.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '!', 200

@app.route('/')
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"https://{os.getenv('VERCEL_URL')}/{BOT_TOKEN}")
    return '!', 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
