import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from discord.ext import commands
import discord
import asyncio
from dotenv import load_dotenv

load_dotenv(dotenv_path="token.env")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

logging.basicConfig(level=logging.INFO)

telegram_bot = Bot(token=TELEGRAM_TOKEN)
telegram_dispatcher = Dispatcher()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
discord_bot = commands.Bot(command_prefix="!", intents=intents)

message_queue = asyncio.Queue()


@telegram_dispatcher.message()
async def handle_telegram_message(message: Message):
    if message.chat.id == TELEGRAM_CHAT_ID:
        sender_name = f"Telegram:\n{message.from_user.full_name or 'Unknown'}:"

        if message.text:
            if message.text.startswith("!"):
                full_message = f"{sender_name}\n{message.text}"
                await message_queue.put(("tg_to_ds", full_message))
            else:
                logging.info("Сообщение пропущено, так как не начинается с '!'")

        elif message.photo or (message.document and message.document.mime_type.startswith("image/")):
            file_id = message.photo[-1].file_id if message.photo else message.document.file_id
            file = await telegram_bot.get_file(file_id)
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
            await message_queue.put(("tg_to_ds_media", (file_url, sender_name)))

        logging.info(f"Сообщение из Telegram обработано: {sender_name}")

@discord_bot.event
async def on_ready():
    print(f"Discord бот {discord_bot.user} готов к работе.")


@discord_bot.event
async def on_message(message):
    if message.channel.id == DISCORD_CHANNEL_ID and not message.author.bot:
        sender_name = f"Discord:\n{message.author.name}:"
        text = message.content if message.content else "[Пустое сообщение]"

        full_message = f"{sender_name}\n{text}"
        await message_queue.put(("ds_to_tg", full_message))

        if message.attachments:
            for attachment in message.attachments:
                file_url = attachment.url.split("?")[0]
                if file_url.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
                    await message_queue.put(("ds_to_tg_media", (attachment.url, sender_name)))
                else:
                    logging.info(f"Неподдерживаемый тип файла: {attachment.url}")

    await discord_bot.process_commands(message)


async def forward_messages():
    while True:
        direction, data = await message_queue.get()

        if direction == "tg_to_ds":
            channel = discord_bot.get_channel(DISCORD_CHANNEL_ID)
            if channel:
                await channel.send(data)

        elif direction == "tg_to_ds_media":
            file_url, sender_name = data
            channel = discord_bot.get_channel(DISCORD_CHANNEL_ID)
            if channel:
                embed = discord.Embed(description=f"Из Telegram от {sender_name}")
                embed.set_image(url=file_url)
                await channel.send(embed=embed)

        elif direction == "ds_to_tg":
            await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=data)

        elif direction == "ds_to_tg_media":
            file_url, sender_name = data
            caption = f"{sender_name}\n[Изображение]"
            await telegram_bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=file_url, caption=caption)

        await asyncio.sleep(1)


async def main():
    telegram_task = telegram_dispatcher.start_polling(telegram_bot)
    discord_task = discord_bot.start(DISCORD_TOKEN)
    forward_task = forward_messages()

    await asyncio.gather(telegram_task, discord_task, forward_task)


if __name__ == "__main__":
    asyncio.run(main())
