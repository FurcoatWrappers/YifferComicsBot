import telebot
from telebot import types

import yiffer

from typing import List

import os
from dotenv import load_dotenv
load_dotenv()

"""
Commands:

start - Begin a conversation with the bot. /start
help - Get a list of commands. /help
comics - Browse comics by page number: /comics <page_number>
search - Search for comics by name. Returns suggestions: /search <name>
keywords - Get the keywords: /keywords
searchkeywords - Search for comics by keyword. Returns suggestions: /searchkeywords <keyword>
comic - Get all the pages of specified comic. Name must be an exact match: /comic <name>
"""



token = os.getenv("BOT_TOKEN")
if not token:
    print("Bot token is not defined. Please make a .env file with BOT_TOKEN=\"0123456789:YOUR_TOKEN_HERE\" (YifferComicsBot/src/.env)")
    quit()

bot = telebot.TeleBot(token)

from telebot.types import InputMediaPhoto

def send_comic_query_to_chat(chat_id, comics: List[yiffer.ComicData]) -> None:
    # Send all the thumbnails as a media group.
    # Add the name, artist, page count, state, and tags to the caption.
    media = []
    for comic in comics:
        media.append(InputMediaPhoto(comic.thumbnail, caption=f"{comic.name} - {comic.artist}\nPages: {comic.numberOfPages}\nState: {comic.state}\nTag: {', '.join(comic.tag)}"))

    bot.send_media_group(chat_id, media)

    # Add a keyboard with buttons to view each comic.
    keyboard = types.InlineKeyboardMarkup()
    for comic in comics:
        keyboard.add(types.InlineKeyboardButton(text=comic.name, callback_data=f"comic:{comic.name}"))
    
    bot.send_message(chat_id, "Select a comic to view:", reply_markup=keyboard)

def send_comic_to_chat(chat_id, comic_name: str) -> None:
    comic = yiffer.ComicData.load_from_db(comic_name)
    if comic is None:
        bot.send_message(chat_id, "Comic not found.")
        return
    bot.send_message(chat_id, f"Loading comic: {comic.name} - {comic.artist}\nPages: {comic.numberOfPages}\nState: {comic.state}\nTag: {', '.join(comic.tag)}")
    image_urls = comic.pages
    # We have to paginate because media max size is 10.
    page_size = 10
    media_groups = [image_urls[i:i + page_size] for i in range(0, len(image_urls), page_size)]
    for media_group in media_groups:
        media = [InputMediaPhoto(url) for url in media_group]
        if media:
            bot.send_media_group(chat_id, media)


# View Comic Callback
@bot.callback_query_handler(func=lambda call: call.data.startswith("comic:"))
def callback_query(call):
    comic_name = call.data.split(":")[1]
    comic = yiffer.ComicData.load_from_db(comic_name)
    if comic is None:
        bot.send_message(call.message.chat.id, "Comic not found.")
        return
    send_comic_to_chat(call.message.chat.id, comic_name)

@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.send_message(message.chat.id, "Welcome to YifferComicBot! \n\nUse /help to see the commands available.")

@bot.message_handler(commands=['help'])
def cmd_help(message):
    command_text = "\n\n\t".join([f"{cmd.command} - {cmd.description}" for cmd in bot.get_my_commands()])
    bot.send_message(message.chat.id, command_text)

@bot.message_handler(commands=['comics'])
def cmd_comics(message):
    args = message.text.split(" ")[1:]
    if len(args) == 0:
        bot.send_message(message.chat.id, f"Please specify a page number. Pages: 1-{yiffer.ComicData.get_max_page_number()}.")
        return
    page_number = args[0]
    if not page_number.isdigit():
        bot.send_message(message.chat.id, "Please specify a valid page number.")
        return
    
    comics = yiffer.ComicData.search_comics_by_page(int(page_number))

    if len(comics) == 0:
        bot.send_message(message.chat.id, "No comics found.")
        return
    
    bot.send_message(message.chat.id, f"Page {page_number} of {yiffer.ComicData.get_max_page_number()}:")
    
    send_comic_query_to_chat(message.chat.id, comics)

@bot.message_handler(commands=['search'])
def cmd_search(message):
    args = message.text.split(" ")[1:]
    if len(args) == 0:
        bot.send_message(message.chat.id, "Please specify a comic name.")
        return
    query = " ".join(args)
    comics = yiffer.ComicData.search_comics_by_name(query)
    if len(comics) == 0:
        bot.send_message(message.chat.id, "No comics found.")
        return
    bot.send_message(message.chat.id, f"Search results for '{query}':")
    send_comic_query_to_chat(message.chat.id, comics)
    
@bot.message_handler(commands=['keywords'])
def cmd_keywords(message):
    keywords_query = yiffer.ComicData.get_keywords_by_count() # [(str, int), (str, int), ...]
    # Paginate the keywords.
    # Send 10 at a time. 
    # Add buttons to go left and right through the keywords.
    
    


bot.infinity_polling()