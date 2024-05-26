import os
import pytz
import json
import logging
import sqlite3
import asyncio
import hashlib
import requests
import datetime
import aiosqlite

from openai import OpenAI
from yaml import safe_load
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import Message, CallbackQuery
from keyboards import Inline
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import ChatTypeFilter
from aiogram.contrib.fsm_storage.memory import MemoryStorage
# from aiogram.contrib.fsm_storage.mongo import MongoStorage      # Can be used for safe storing FSMContext data
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.utils.exceptions import BotBlocked, MessageCantBeDeleted

from bs4 import BeautifulSoup
from typing import Union, List, Tuple

requests.packages.urllib3.disable_warnings()
tz = pytz.timezone('Etc/GMT-7')
load_dotenv('secret.env')


class HWUpdate(StatesGroup):
    waiting_for_content = State()
    waiting_for_subject = State()
    wait_for_more_media = State()


class Texts:
    def __init__(self):
        with open('texts.yaml', 'r', encoding='utf-8') as file:
            data = safe_load(file)
        
        for key, value in data.items():
            setattr(self, key, value)


client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)

storage = MemoryStorage()
# storage = MongoStorage(host='localhost', db_name='helpus3')

# HH or xhelpus
TEXT = Texts()
ADMIN = int(os.environ.get('admin_id'))
TOKEN = os.environ.get("xhelpus")
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=storage)
dp.setup_middleware(LoggingMiddleware())
logging.basicConfig(level=logging.INFO)

day_translation = {
    "Monday": "Понедельник",
    "Tuesday": "Вторник",
    "Wednesday": "Среда",
    "Thursday": "Четверг",
    "Friday": "Пятница",
    "Saturday": "Суббота",
    "Sunday": "Воскресенье"
}

reversed_translation = {v: k for k, v in day_translation.items()}


class AlbumMiddleware(BaseMiddleware):
    """This middleware is for capturing media groups."""

    album_data: dict = {}

    def __init__(self, latency: Union[int, float] = 0.01):
        """
        You can provide custom latency to make sure
        albums are handled properly in highload.
        """
        self.latency = latency
        super().__init__()

    async def on_process_message(self, message: Message, data: dict):
        if not message.media_group_id:
            return

        try:
            self.album_data[message.media_group_id].append(message)
            raise CancelHandler()  # Tell aiogram to cancel handler for this group element
        except KeyError:
            self.album_data[message.media_group_id] = [message]
            await asyncio.sleep(self.latency)

            message.conf["is_last"] = True
            data["album"] = self.album_data[message.media_group_id]

    async def on_post_process_message(self, message: Message, result: dict, data: dict):
        """Clean up after handling our album."""
        if message.media_group_id and message.conf.get("is_last"):
            del self.album_data[message.media_group_id]


# Working with user object without direct using sql
class User:
    def __init__(self, user_id=None, name=None, **kwargs):
        self.id = kwargs.get('id', None)
        self.user_id = kwargs.get('user_id', None) if not user_id else user_id
        self.user_class = kwargs.get('class', None)
        self.group_name_2 = kwargs.get('group_name_2', None)
        self.group_name_3 = kwargs.get('group_name_3', None)
        self.notice_dayend = kwargs.get('notice_dayend', None)
        self.notice_daystart = kwargs.get('notice_daystart', None)
        self.name = kwargs.get('name', None) if not name else name
        self.schedule_view = kwargs.get('schedule_view', None)
        self.hw_view = kwargs.get('hw_view', None)
        self.firstSchedule = kwargs.get('firstSchedule', None)
        self.status = kwargs.get('status', None)
        self.fstUPD = kwargs.get('fstUPD', None)
        self.hwUpd = kwargs.get('hwUpd', None)
        self.hideAlert = kwargs.get('hideAlert', None)
        self.temp_class = kwargs.get('temp_class', None)
        self.showClass = kwargs.get('showClass', None)
        self.delprelesson = kwargs.get('delprelesson', None)
        self.temp_scdView = kwargs.get('temp_scdView', None)
        self.interactions = kwargs.get('interactions', None)
        self.fstArchive = kwargs.get('fstArchive', None)
        self.lastMessageType = kwargs.get('lastMessageType', None)
        self.lastMessageId = kwargs.get('lastMessageId', None)

    @classmethod
    async def loaduser(cls, user_id: int, lcolumns=None):
        if lcolumns is None:
            columns = '*'
        else:
            columns = ', '.join(lcolumns)
            
        async with aiosqlite.connect('settings.db') as conn:
            cur = await conn.cursor()
            await cur.execute(f"SELECT {columns} FROM preferences WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
        
            if row:
                if columns == '*':
                    await cur.execute('PRAGMA TABLE_INFO(preferences)')
                    column_names = [tup[1] for tup in await cur.fetchall()]
                    data = dict(zip(column_names, row))
                else:
                    data = dict(zip(lcolumns, row))
                
                return cls(**data)
            else: 
                return None
        
    async def updateuser(self, condition: dict = None):
        if condition is None:
            condition = {'user_id': self.user_id}
        data = self.__dict__.copy()
        data['class'] = data.pop('user_class')
        datastr = ', '.join([f'{col} = ?' for col in data])
        condstr = ' AND '.join([f'{col} = ?' for col in condition])
        
        async with aiosqlite.connect('settings.db') as conn:
            cur = await conn.cursor()
            await cur.execute(f"UPDATE preferences SET {datastr} WHERE {condstr}", (*data.values(), *condition.values()))
            await conn.commit()
    
    @classmethod
    async def createuser(cls, user_id: int, name=None):
        async with aiosqlite.connect('settings.db') as conn:
            cur = await conn.cursor()
            await cur.execute("INSERT INTO preferences (user_id, name) VALUES (?, ?)", (user_id, name))
            await conn.commit()

        return await cls.loaduser(user_id)


# Decorator function to check if user is registered
def registration_check(func):
    async def wrapper(*args, **kwargs):
        if isinstance(args[0], Message):  # Getting user's id, name and message object
            message = args[0]
            user_id = message.from_user.id
            name = message.from_user.full_name
        elif isinstance(args[0], CallbackQuery):
            callback = args[0]
            message = callback.message
            user_id = callback.from_user.id
            name = callback.from_user.full_name

        print((user_id, name))

        user = await User.loaduser(user_id)

        if not user:
            user = await User.createuser(user_id, name)

            if message.chat.type == 'private':
                await message.answer(text = TEXT.settings['greetings'],
                                     reply_markup=Inline.inline_start_command('settings'), parse_mode='Markdown')
            else:
                await message.reply('Я вижу, что ты хочешь добавить домашку! Давай сначала [зарегистрируемся](https://t.me/helputils_bot)',
                                    parse_mode='Markdown')
                
            if isinstance(args[0], CallbackQuery):
                await args[0].answer('Сначала зарегистрируйся!')
        
        else:
            if user.status:
                if isinstance(args[0], CallbackQuery):
                    await callback.answer('Тебе ограничен доступ, свяжись с @laughin_me', show_alert=True)
                else:
                    await message.answer('Тебе ограничен доступ, свяжись с @laughin_me')
                return
            
            else:
                if name != user.name:
                    user.name = name

                kwargs['user'] = user
                await func(*args, **kwargs)

        user.lastMessageType, user.lastMessageId, user.interactions = (func.__name__, message.message_id, 'interactions + 1')
        await user.updateuser()

    return wrapper


async def on_startup(_):
    botUser = await bot.get_me()
    print(f'Bot {botUser.full_name} is now online!')


@dp.message_handler(ChatTypeFilter(types.ChatType.PRIVATE), commands=['start'])
@registration_check
async def start(message: Message, **kwargs):
    if message.chat.type == 'private':
        await message.answer(TEXT.main_menu, reply_markup=Inline.commands_inline(), parse_mode='Markdown')


def escapeMd2(text: str) -> str:
    """Escape all characters reserved by Telegram's MarkdownV2."""
    characters_to_escape = ['(', ')', '.', '-']

    for char in characters_to_escape:
        text = text.replace(char, '\\' + char)

    return text


# Schedule message text constructor
async def get_schedule(day_schedule: List[Tuple], cur: sqlite3.Cursor, view='lessons') -> str:
    """
    Assembling text for a message with a school schedule.
    Example for pairs:\n
    🗓 Расписание на Понедельник (12.05):

    1-2. Геометрия-Алгебра ➗
    8:30-10:00 Рожнева М.С. спортзал

    3-4. География 🌍
    10:15-11:45 Джабиева Е.Ю. 113к.

    Args:
        - day_schedule (list[tuple]): the day's schedule, lesson by lesson in tuple format.
        It is obtained by querying school_schedule.db, this way:\n
        SELECT lesson_name, start_time, end_time, teacher_name, classroom, non_original

        - cur (cursor): avoid reconnecting to db

        - view (lessons/pairs): schedule being parsed depending on what type of view chosen

    Returns:
        str: formatted schedule string
    """

    relevant_lessons = []
    for day in day_schedule:
    # for i in sorted(day_schedule, key=lambda x: int(x[6])): # old lessons sorting method
        # if (i[-1] == group_name_2 or i[-1] is None) and i[0] is not None:
        await cur.execute(f'SELECT emojiName FROM lessons WHERE lesson_name = "{day[0]}"')
        lesson = (await cur.fetchone())[0]
        relevant_lessons.append((lesson, *day[1:6]))
    
    if view == 'pairs':

        schedule = []
        index = 0
        while index < len(relevant_lessons):
            lesson, start, end, teacher, room, removed = relevant_lessons[index]

            # Если следующий урок существует и у него такой же учитель, как и у текущего урока
            if index + 1 < len(relevant_lessons) and teacher == relevant_lessons[index + 1][3]:
                next_lesson = relevant_lessons[index + 1]

                currentlesson = lesson.split()[0]  # Removing emoji
                
                if not removed and not next_lesson[5]:
                    schedule.append(f"*{index+1}-{index+2}. {lesson if lesson == next_lesson[0] else f'{currentlesson}-{next_lesson[0]}'}*\n"
                                    f"_{start}-{next_lesson[2]} {teacher}_ *{room}*{'к.' if room.isnumeric() else ''}")
                else:
                    schedule.append(f"~{index+1}-{index+2}. {lesson if lesson == next_lesson[0] else f'{currentlesson}-{next_lesson[0]}'}~\n"
                                    f"~{start}\\~{next_lesson[2]} {teacher} {room}{'к.' if room.isnumeric() else ''}~")

                index += 2  # Пропускаем следующий урок, так как мы его уже обработали
            else:
                if not removed:
                    schedule.append(f"*{index+1}. {lesson.capitalize()}*\n"
                                    f"_{start}-{end} {teacher}_ *{room}*{'к.' if room.isnumeric() else ''}")
                else:
                    schedule.append(f"~{index+1}. {lesson.capitalize()}~\n"
                                    f"~{start}\\~{end} {teacher} {room}{'к.' if room.isnumeric() else ''}~")

                index += 1
    
    else:

        schedule = [
            (
                f"*{index+1}. {lesson.capitalize()}*\n_{start}-{end} {teacher}_ *{room}*{'к.' if room.isnumeric() else ''}"
                if not removed
                else f"~{index+1}. {lesson.capitalize()}~\n~{start}-{end} {teacher} {room}{'к.' if room.isnumeric() else ''}~"
            )

            for index, (lesson, start, end, teacher, room, removed) in enumerate(relevant_lessons)
        ]
        
    return '\n\n'.join(schedule)


async def monday_period(cur: sqlite3.Cursor):
    await cur.execute('SELECT value FROM period WHERE prefix = "b"')
    begin = tz.localize(datetime.datetime.strptime((await cur.fetchone())[0], '%d.%m.%Y'))
    tomorrow = (datetime.datetime.now(tz) + datetime.timedelta(1))

    if tomorrow >= begin:
        return f'🗓 *Расписание на Понедельник ({tomorrow.strftime("%d.%m")}):*'
    else:
        return f'🗓 *Расписание на Понедельник ({(datetime.datetime.now(tz) - datetime.timedelta(days=5)).strftime("%d.%m")}):*'
    

############ SCHEDULE COMMAND ############
@dp.message_handler(ChatTypeFilter(types.ChatType.PRIVATE), commands=['schedule'])
@dp.callback_query_handler(lambda callback: callback.data.startswith('schedule'))
@registration_check
async def schedule(input: CallbackQuery | Message, user: User, **kwargs):
    if isinstance(input, CallbackQuery): await input.answer()
    data = 'today'

    if not user.temp_class:
        user.temp_class = user.user_class
        
    if not user.temp_scdView:
        user.temp_scdView = user.schedule_view
    await user.updateuser()

    if isinstance(input, CallbackQuery):
        if input.data.startswith('schedule_view'):
            user.temp_scdView = 'pairs' if user.temp_scdView=='lessons' else 'lessons'
            user.schedule_view = user.temp_scdView
            await user.updateuser()

            day = input.data.split('_')[-1]
            is_tomorrow = False

            if day != day_translation[datetime.datetime.now(tz).strftime('%A')]: is_tomorrow=True

            async with aiosqlite.connect('school_schedule.db') as conn:
                cur = await conn.cursor()
                await cur.execute(f'''SELECT lesson_name, start_time, end_time, teacher_name, classroom, non_original FROM "{user.temp_class}"
                                  WHERE day_name = "{day}" AND (group_name = "{user.group_name_2}" OR group_name IS NULL) AND lesson_name IS NOT NULL ORDER BY lesson_number''')
                
                await input.message.edit_text(
                    escapeMd2(f'🗓 *Расписание на {f"сегодня ({day})" if not is_tomorrow else f"завтра ({day})"}:* \n'
                    + await get_schedule(await cur.fetchall(), cur, user.temp_scdView)), parse_mode='MarkdownV2',
                    reply_markup=Inline.schedule(f'today_{day}', True, user.temp_scdView, user.temp_class if user.showClass else False)
                    )
            return
    

        elif input.data.startswith('schedule_class'):
            if input.data.split('_')[-1] == 'scd':
                await input.message.edit_text(TEXT.schedule['class'], 
                        reply_markup=await Inline.settings(input.from_user.id, 'choose_class_scd'))
                return
            else:
                user.temp_class = input.data.split('_')[-1]
                if not user.temp_scdView: user.temp_scdView = 'lessons'
                if not user.temp_class.startswith(('9', '10', '11')):
                    print('how does he does it?')
                    user.temp_scdView = 'lessons'
                else:
                    user.temp_scdView = user.schedule_view
                await user.updateuser()
                        
                changeBtn = False if user.firstSchedule or not user.temp_class.startswith(('9', '10', '11')) else True 
                        
                day = day_translation[datetime.datetime.now(tz).strftime("%A")]
                is_tomorrow = False
                async with aiosqlite.connect('school_schedule.db') as conn:
                    cur = await conn.cursor()
                    await cur.execute(f'SELECT end_time FROM "{user.temp_class}" WHERE day_name = ?', (day,))
                    times = sorted([time for (time,) in await cur.fetchall()], key=lambda x: tz.localize(datetime.datetime.strptime(x, '%H:%M')))
                    if times:
                        end_time = times[-1]
                        print(times, end_time, sep='\n')
                        if datetime.datetime.strptime(end_time, '%H:%M').time() < datetime.datetime.now(tz).time():
                            day = day_translation[(datetime.datetime.now(tz) + datetime.timedelta(days=1)).strftime("%A")]
                            is_tomorrow = True

                    if day == 'Воскресенье': 
                        day = 'Понедельник'
                        text = await monday_period(cur)
                    else:
                        if not is_tomorrow: text = f'🗓 *Расписание на сегодня ({day}):*'
                        else: text = f'🗓 *Расписание на завтра ({day}):*'

                    await cur.execute(f'''SELECT lesson_name, start_time, end_time, teacher_name, classroom, non_original FROM "{user.temp_class}"
                                      WHERE day_name = "{day}" AND (group_name = "{user.group_name_2}" OR group_name IS NULL) AND lesson_name IS NOT NULL ORDER BY lesson_number''')
                    
                    await input.message.edit_text(
                        escapeMd2(text+'\n\n' + await get_schedule(await cur.fetchall(), cur, user.temp_scdView)),
                        parse_mode='MarkdownV2',
                        reply_markup=Inline.schedule(f'today_{day}', changeBtn, user.temp_scdView, user.temp_class if user.showClass else False)
                        )
                return
    
        data = input.data.split('_')


    changeBtn = False
    if not user.firstSchedule:
        if not user.temp_scdView:
            user.temp_scdView = 'lessons'
        if user.temp_class.startswith(('9', '10', '11')):
            changeBtn = True

        
    print(data)
    async with aiosqlite.connect('school_schedule.db') as conn:
        cur = await conn.cursor()
        if isinstance(input, Message) or data[1] == 'today':

            day = day_translation[datetime.datetime.now(tz).strftime("%A")]

            is_tomorrow = False

            await cur.execute(f'SELECT end_time FROM "{user.temp_class}" WHERE day_name = ?', (day,))
            times = sorted([time for (time,) in await cur.fetchall()], key=lambda x: tz.localize(datetime.datetime.strptime(x, '%H:%M')))
            if times:
                end_time = times[-1]
                print(times, end_time, sep='\n')
                if datetime.datetime.strptime(end_time, '%H:%M').time() < datetime.datetime.now(tz).time():
                    day = day_translation[(datetime.datetime.now(tz) + datetime.timedelta(days=1)).strftime("%A")]
                    is_tomorrow = True

            if day == 'Воскресенье':
                day = 'Понедельник'
                text = await monday_period(cur)
            else:
                if not is_tomorrow:
                    text = f'🗓 *Расписание на сегодня ({day}):*'
                else:
                    text = f'🗓 *Расписание на завтра ({day}):*'

            await cur.execute(f'''SELECT lesson_name, start_time, end_time, teacher_name, classroom, non_original FROM "{user.temp_class}"
                              WHERE day_name = "{day}" AND (group_name = "{user.group_name_2}" OR group_name IS NULL) AND lesson_name IS NOT NULL ORDER BY lesson_number''')

            async def send(*args, **kwargs):
                if isinstance(input, CallbackQuery): await input.message.edit_text(*args, **kwargs)
                else: await input.answer(*args, **kwargs)

            await send(escapeMd2(text+'\n\n' + await get_schedule(await cur.fetchall(), cur, user.temp_scdView)), parse_mode='MarkdownV2',
                       reply_markup=Inline.schedule(f'today_{day}', changeBtn, user.temp_scdView, user.temp_class if user.showClass else False))


        elif input.data.startswith(('schedule_left_', 'schedule_right_', 'schedule_day_')):
            data = input.data.split('_')
            day = data[-1]

            await cur.execute(f'''SELECT lesson_name, start_time, end_time, teacher_name, classroom, non_original FROM "{user.temp_class}"
                              WHERE day_name = "{day}" AND (group_name = "{user.group_name_2}" OR group_name IS NULL) AND lesson_name IS NOT NULL ORDER BY lesson_number''')

            # Determine the index of the day in the week (0 for Monday, 6 for Sunday)
            day_index = list(day_translation.values()).index(day)
            today_index = datetime.datetime.now(tz).weekday()
            
            is_today = False
            is_tomorrow = False
            if day_index == today_index: is_today = True
            elif day_index-1 == today_index: is_tomorrow = True

            if datetime.datetime.now(tz).weekday() == 6:
                start = datetime.datetime.now(tz) + datetime.timedelta(days=1)
            else:
                start = datetime.datetime.now(tz) - datetime.timedelta(days=datetime.date.today().weekday())

            week_dates = [start + datetime.timedelta(days=i) for i in range(7)]

            target_date = week_dates[day_index]
    
            if is_today:
                text = f'🗓 *Расписание на сегодня ({day}):*'
            elif is_tomorrow:
                text = f'🗓 *Расписание на завтра ({day}):*'
            else:
                if day == 'Воскресенье': day = 'Понедельник'
                text = f'🗓 *Расписание на {day} ({target_date.strftime("%d.%m")}):*'
                changeBtn = False

            # Edit the message with the new schedule
            await input.message.edit_text(
                escapeMd2(f'{text} \n\n' + await get_schedule(await cur.fetchall(), cur, user.temp_scdView)),
                parse_mode='MarkdownV2', reply_markup=Inline.schedule(f'week_{day}'+('_day' if data[1] == 'day' else ''), changeBtn,
                                                                      user.temp_scdView, user.temp_class if user.showClass else False)
            )


########### SETTINGS ###########
@dp.message_handler(ChatTypeFilter(types.ChatType.PRIVATE), commands=['settings']) # All user settings gathered here
@dp.callback_query_handler(lambda callback: callback.data == 'settings_main', state='*')
async def settings(message: Message | CallbackQuery, state: FSMContext):
    if state: await state.reset_state(with_data=True)

    text = TEXT.settings['main'] # Loading text via Texts() class
    
    # Greetings here
    if isinstance(message, Message):
        await message.reply(text, reply_markup=await Inline.settings(message.from_user.id))

    else:
        await message.answer()
        await message.message.edit_text(text, reply_markup=await Inline.settings(message.from_user.id))

# user settings handler
@dp.callback_query_handler(lambda callback: callback.data.startswith('settings'))
async def settings_navigation(callback: CallbackQuery):
    data = callback.data.split('_')

    if data[1] == 'choose':
        await callback.answer()
        if data[2] == 'class': # Choosing grade
            await callback.message.edit_text(TEXT.settings['class'],  reply_markup=await Inline.settings(callback.from_user.id, 'choose_class'))
            
        elif data[2] == 'group': # Choosing group
            await callback.message.edit_text(TEXT.settings['group'],
                                             reply_markup=await Inline.settings(callback.from_user.id, f'choose_group_{"2" if data[3] == "2" else "3"}'), parse_mode='Markdown')
            
    else:
        user = await User.loaduser(callback.from_user.id)

        if data[1] == 'choice':
            
            if data[2] == 'class':
                user.user_class, user.temp_class, user.schedule_view, user.temp_scdView, user.firstSchedule = (
                    data[3], data[3], 'lessons', 'lessons', 0
                )

            elif data[2] == 'group':
                if data[3] == '2':
                    user.group_name_2 = data[4]
                else:
                    user.group_name_3 = data[4]

            await user.updateuser()
            await callback.answer()
            await callback.message.edit_text(TEXT.settings['main'], reply_markup=await Inline.settings(callback.from_user.id))
            
        elif data[1] == 'notice': # Switching notifications
            if '_'.join(data) == 'settings_notice':
                await callback.answer()
                await callback.message.edit_text('Ты можешь настроить здесь свои уведомления.\n\nТакже можешь посмотреть примеры уведомлений.', reply_markup=await Inline.settings(callback.from_user.id, 'notice'))
            elif data[2] == 'dayend':

                if data[3] in ['on', 'off']:
                    user.notice_dayend = data[3] # Class object gets new value and being saved then

                    if data[3] == 'on':
                        await callback.answer(text='Уведомления включены ✅')
                    elif data[3] == 'off':
                        await callback.answer(text='Уведомления выключены ❌')

                    await user.updateuser() # Here it saves
                    await callback.message.edit_reply_markup(await Inline.settings(callback.from_user.id, 'notice'))
                    
                else:
                    await callback.answer("Ожидание ответа ChatGPT...")    
                    message = await callback.message.answer("Загружаю расписание...")

                    async with aiosqlite.connect('school_schedule.db') as schedule_conn:
                        async with schedule_conn.cursor() as schedule_cur:
                            await schedule_cur.execute(f'SELECT DISTINCT lesson_name, start_time, end_time, group_name FROM "{user.user_class}" WHERE day_name = "Понедельник" AND non_original IS NULL')
                            day_schedule = await schedule_cur.fetchall()

                    async with aiosqlite.connect('homework.db') as hconn:
                        async with hconn.cursor() as hcur:
                            await hcur.execute(f'SELECT content, subject FROM "{user.user_class}" WHERE group_name IS NULL LIMIT 2')
                            homework = await hcur.fetchall()

                    if homework: # Gathering tasks and writing homework review using chatgpt

                        await message.edit_text("Пишу домашку с ChatGPT...")

                        system_message = TEXT.ChatGPT['settings_system_message']
                        user_message = '\n'.join([f'{index+1}. {homework_tuple[0]} ({homework_tuple[1]})' for index, homework_tuple in enumerate(homework)])

                        homework = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": system_message},
                                {"role": "user", "content": user_message}
                            ]
                        ).choices[0].message.content

                    relevant_lessons = [lesson for lesson in day_schedule if lesson[3] is None and lesson[0] is not None]
                    schedule = [f"{index + 1}. *{lesson[0].capitalize()}*" for index, lesson in enumerate(relevant_lessons)]

                    data = {'start_time': relevant_lessons[0][1],
                    'end_time': relevant_lessons[len(schedule)-1][2],
                    'lessons_amount': len(schedule)}

                    completion = TEXT.ChatGPT['lessons_over'].format(**data)
                    completion += '\n\n*Расписание на завтра:*\n' + '\n'.join(schedule)
                    if homework:
                        completion += f'\n\n*Кратко про домашку:*\n\n{homework}'
                    else:
                        completion += '\n\n*Кратко про домашку:*\n\nКажется, что заданий на завтра нет!\n\n'
                    completion += "\n\n*(Информация выше может отличаться от настоящей)*"

                    await message.edit_text(completion, parse_mode='Markdown', reply_markup=Inline.dayend_mailing())
                    await callback.answer()
                
            elif data[2] == 'daystart':
                if data[3] in ['on', 'off']:
                    user.notice_daystart = data[3]

                    if data[3] == 'on':
                        await callback.answer(text='Уведомления включены ✅')
                    elif data[3] == 'off':
                        await callback.answer(text='Уведомления выключены ❌')

                    await user.updateuser()
                    await callback.message.edit_reply_markup(await Inline.settings(callback.from_user.id, 'notice'))

                else:
                    await callback.message.answer('Пример уведомления перед *предстоящим* уроком:\n\n_В 10:15_ - *География* (Митина Н.Б.) в *126* кабинете, до _11:00_', parse_mode='Markdown', reply_markup=Inline.deleteMsg())
                    await callback.answer()

        elif data[1] == 'schedule':

            if len(data) == 2:
                await callback.message.edit_text('Здесь ты можешь настроить отображение школьного расписания, и его кнопки.', reply_markup=await Inline.settings(callback.from_user.id, 'schedule'))

            else:

                if data[2] == 'view':

                    if user.schedule_view == "lessons": new = "pairs"
                    else: new = "lessons"

                    user.schedule_view, user.temp_scdView = (new, new)
                    await user.updateuser()

                    await callback.message.edit_reply_markup(await Inline.settings(callback.from_user.id, 'schedule'))
                    await callback.answer(text='Изменено ✅')

                elif data[2] == 'class':

                    if user.showClass == 1: user.showClass = 0
                    else: user.showClass = 1

                    await user.updateuser()

                    await callback.message.edit_reply_markup(await Inline.settings(callback.from_user.id, 'schedule' if data[-1] != 'minor' else 'default'))
                    await callback.answer(text='Изменено ✅')


# Constructor of user's data
async def getAdmin(user_id):
    user = await User.loaduser(user_id)
    
    text = f'''*Информация о пользователе:*\n
- Имя: *{user.name}*
- Класс: *{user.user_class}*
- Группа: *{user.group_name_2}*
- Уведомления перед уроком: *{user.notice_daystart}*
- Уведомления после уроков: *{user.notice_dayend}*
- Расписание: *{user.schedule_view}*
- Interactions: *{user.interactions}*
- Статус: *{'Бан' if user.status else 'Доступ'}*\n
  Выбор действия:'''

    return text
        

# Admin command handler
@dp.message_handler(ChatTypeFilter(types.ChatType.PRIVATE), commands=['admin'])
@dp.callback_query_handler(lambda callback: callback.data.startswith('admin'))
@registration_check
async def admin(data: Message | CallbackQuery, state: FSMContext, **kwargs):
    if data.from_user.id == ADMIN:
        
        if type(data) == Message:
            await data.answer('Выбери инструмент из меню кнопок ниже:', reply_markup=Inline.admin())
            try: await data.delete()
            except: pass

        else:
            callback = data
            data = callback.data.split('_')[1:]
            
            if data[0] == 'users':
                await callback.message.edit_text('Выбор пользователя:', reply_markup=Inline.admin('users'))

            elif data[0] == 'user':
                user_id = data[1]

                user = await User.loaduser(user_id)

                if len(data)==2:
                    
                    await callback.message.edit_text(await getAdmin(user_id), reply_markup=Inline.admin(f'sUser', user_id), parse_mode='Markdown')

                elif data[2] == 'status':
                    await callback.answer('Изменено!')

                    user.status = 0 if user.status else 1
                    await user.updateuser()
                    await callback.message.edit_text(await getAdmin(user_id), reply_markup=Inline.admin('sUser', user_id), parse_mode='Markdown')

                elif data[2] == 'hw': # Standart homework parser code below
                    await callback.answer()
                    
                    try:await callback.message.delete()
                    except: pass
                    with sqlite3.connect('homework.db') as conn:
                        cur = conn.cursor()

                        cur.execute(f'SELECT content, subject, mediafile_id FROM "{user.user_class}" WHERE author = "{user.name}"')

                        homework_tasks = cur.fetchall()
                    media_group = []
                    tasks_text=[]
                    embed_counter = 0
                    media = types.MediaGroup()
                                
                    for task in homework_tasks:
                        content, subject, mediafile_id = task

                        if mediafile_id:
                            mediafile_id = mediafile_id.split(' ')
                            embed_counter+=1
                            photo = [types.InputMediaPhoto(media = file, caption = f'Вложение №{embed_counter}') for file in mediafile_id]
                            media_group.extend(photo)
                            text = f"{str(subject).capitalize()}:\n{str(content if content else 'Задание на фото!').strip().capitalize()}\n\n📎 Фото №{embed_counter}"
                        else:
                            text = str(subject).capitalize()+':\n'+str(content).strip().capitalize()
                            tasks_text.append(text)

                    if media_group:
                        storage = await state.get_data()
                        try:
                            if len(media_group) > 1:
                                for photo in media_group:
                                    media.attach_photo(photo=photo)
                                
                                storage['media'] = await callback.message.answer_media_group(media=media)
                                    
                            elif len(media_group) == 1:
                                storage['media'] = [await callback.message.answer_photo(media_group[0].media)]

                            else:
                                storage['media'] = None
                        except:
                            storage['media'] = [await callback.message.answer('media expired')]
                        
                        await state.update_data(storage)


                    await callback.message.answer(text=f'\n\n'.join(tasks_text), reply_markup=Inline.admin('hw', user_id))


            elif data[0]=='back':
                await callback.answer('return...')

                storage = await state.get_data()
                storage['task_id'] = []
                if 'media' in storage:
                    messages = storage['media']
                else: messages = None
                storage['media'] = None
                await state.update_data(storage)

                await callback.message.edit_text(text=await getAdmin(data[1]), reply_markup=Inline.admin('sUser', data[1]), parse_mode='Markdown')
                
                if messages:
                    for obj in messages:
                        try: await obj.delete()
                        except: pass
                        await asyncio.sleep(0.5)


# Cabinets function provides free classrooms
@dp.message_handler(ChatTypeFilter(types.ChatType.PRIVATE), commands=['cabinets'])
@dp.callback_query_handler(lambda callback: callback.data.startswith('cabinets'))
@registration_check
async def cabinets(data: Message | CallbackQuery, **kwargs):

    message = data if isinstance(data, Message) else data.message

    if isinstance(data, Message) or data.data == 'cabinets':
        if isinstance(data, Message):
            await message.answer('Выбери период на который нужно посмотреть свободные кабинеты:', reply_markup=Inline.freerooms())
            await message.delete()
        else:
            await message.edit_text('Выбери период на который нужно посмотреть свободные кабинеты:', reply_markup=Inline.freerooms())
            await data.answer()

        return

    data = data.data.split('_')[1:]
    now = datetime.datetime.now(tz)

    if data[0] in ['day', 'current']:
        
        with sqlite3.connect('school_schedule.db') as conn:
            cur = conn.cursor()
            cur.execute('SELECT class_name FROM classes')
            classes = [_ for (_,) in cur.fetchall()]
            cur.execute('SELECT room FROM classrooms')
            total_rooms = set([_ for (_,) in cur.fetchall()])
            used_rooms = []

            if data[0] == 'day':
                
                for class_name in classes:
                    cur.execute(f"SELECT DISTINCT classroom FROM '{class_name}' WHERE day_name = ?", (day_translation[now.strftime('%A')],))
                    used_rooms.extend([_ for (_,) in cur.fetchall()])
            
                used_rooms = set(used_rooms)
                free = [room for room in list(total_rooms - used_rooms) if room[:2].isnumeric()]

                await message.edit_text(f'Свободные кабинеты: '+', '.join(free) if free else 'Свободных кабинетов нет!', reply_markup=Inline.freerooms('back'))
                print(*free)

            elif data[0] == 'current':
                
                def checker(tuple):
                    now = datetime.datetime.strptime('10:00', '%H:%M')
                    _, start, end = tuple
                    start = datetime.datetime.strptime(start, '%H:%M')
                    end = datetime.datetime.strptime(end, '%H:%M')

                    if end <= now:
                        print(tuple)
                        return False

                    return True

                for class_name in classes:
                    cur.execute(f"SELECT DISTINCT classroom, start_time, end_time FROM '{class_name}' WHERE day_name = ?", (day_translation[now.strftime('%A')],))
                    data = cur.fetchall()

                    used_rooms +=  [item[0] for item in filter(checker, data) if item[0]]

                free = total_rooms - set(used_rooms)
                print(free)

                await message.edit_text(text=', '.join(free) if free else 'Свободных кабинетов нет!', reply_markup=Inline.freerooms('back'))


######### MAIN MENU NAVIGATION
@dp.callback_query_handler(lambda callback: callback.data.endswith(('nav', 'clear')), state='*')
async def navigation_clear(callback: CallbackQuery, state: FSMContext, **kwargs):
    user_id = callback.from_user.id

    commands_text = TEXT.main_menu
    
    if callback.data.startswith('main_schedule'):
        user = await User.loaduser(user_id)
        
        if not user or not user.user_class:
            await callback.message.edit_text(commands_text, reply_markup=Inline.commands_inline(), parse_mode='Markdown')
            return
        user.temp_class, user.lastMessageType = (user.user_class, None)
            
        if not user.schedule_view:
            user.schedule_view = 'lessons'
        else:
            user.temp_scdView = user.schedule_view
        if not user.firstSchedule:
            user.firstSchedule = 1
            if user.user_class.startswith(('9', '10', '11')):
                await callback.answer('Теперь отображение расписания можно изменить в настройках', show_alert=True)
        
        await user.updateuser()

    if callback.data.startswith('setreturn'):
        user = await User.loaduser(user_id)
        if not user:
            await User.createuser(user_id, callback.from_user.full_name)
                
    try: await callback.answer()
    except: pass

    if callback.data == 'commands_clear':
        await callback.message.edit_text(commands_text, reply_markup=Inline.commands_inline(), parse_mode='Markdown')
        return

    if callback.data == 'main_nav':
        await callback.message.answer(commands_text, reply_markup=Inline.commands_inline(), parse_mode='Markdown')
        return
    
    data = await state.get_data()
    if 'media' in data and data['media']:
        await callback.message.edit_text(commands_text, reply_markup=Inline.commands_inline(), parse_mode='Markdown')
        media = data['media']
        for message in media:
            try:
                await message.delete()
                await asyncio.sleep(0.5)
            except: continue
        # return
    
    elif callback.message.photo:
        await callback.message.answer(commands_text, reply_markup=Inline.commands_inline(), parse_mode='Markdown')
        try:await callback.message.delete()
        except: pass
        
    else:
        try: await callback.message.edit_text(commands_text, reply_markup=Inline.commands_inline(), parse_mode='Markdown')
        except Exception as e: print(e)
    await state.reset_state()


######### HOMEWORK #########
@dp.message_handler(commands=['hw'])
@dp.callback_query_handler(lambda callback: callback.data.startswith('homework'))
@registration_check
async def homework(message: Message | CallbackQuery, state: FSMContext, user: User, **kwargs):

    user_class, user_group_2, view = (user.user_class, user.group_name_2, user.hw_view)
    
    storage = await state.get_data()
    storage['media'] = []
    storage['task_id'] = []
    await state.update_data(storage)

    if view in ['lessons', None]: view = 'default'

    if isinstance(message, CallbackQuery):
        callback = message
        message = callback.message
        await callback.answer()
        await message.edit_text(text=TEXT.get_text['hw_hub'],
                                        reply_markup=Inline.hw_inline(user_class=user_class, user_group_2=user_group_2, mode=view, changer=True))
        
    else:
        await message.answer(text=TEXT.get_text['hw_hub'],
                            reply_markup=Inline.hw_inline(user_class=user_class, user_group_2=user_group_2, mode=view, changer=True))


####### HOMEWORK NAVIGATION ######## 
@dp.callback_query_handler(lambda callback: callback.data.startswith('hw_')==True)
@registration_check
async def homework_navigation(callback: CallbackQuery, state: FSMContext, user: User, **kwargs):
    data = callback.data.split('_')[1:]
    print(data)

    storage = await state.get_data()
    if sorted(list(storage.keys())) != sorted(['media', 'task_id']):
        storage['media'] = []
        storage['task_id'] = []
        await state.update_data(storage)

    if callback.from_user.id == ADMIN: admin=True
    else: admin=False

    user.user_class, user.group_name_2, user.group_name_3, user.hw_view, user.name, user.fstArchive

    with sqlite3.connect('school_schedule.db') as conn:
        cur = conn.cursor()
        cur.execute(f'SELECT id FROM lessons')
        subjects = cur.fetchall()
        subjects = [_ for (_,) in subjects] if subjects else []
    

    if data[0] == 'delete':
        id = data[-1]
        await callback.answer('Deleting task...')

        with sqlite3.connect('homework.db') as conn:
            cur = conn.cursor()
            cur.execute(f'SELECT * FROM "{user.user_class}" WHERE id = {id}')
            task = cur.fetchone()
            
        # storage = await state.get_data()
        storage['task_id'] = []
        storage['task'] = task
        await callback.message.edit_text(text='Добавить задание в архив?', reply_markup=Inline.hw_inline(archive=True))
        messages = storage['media']
        storage['media'] = None
        await state.update_data(storage)

        if messages:
            for obj in messages:
                await obj.delete()
                await asyncio.sleep(0.5)
        return
    

    elif data[0]=='archivate':
        if data[1] == 'back':
            await callback.message.edit_text(text=TEXT.get_text['hw_hub'], reply_markup=Inline.hw_inline(False, user.user_class, user.group_name_2, mode=user.hw_view))
            await callback.answer('Отмена')
        
        else:
            storage = await state.get_data()
            
            async with aiosqlite.connect('homework.db') as conn:
                cur = await conn.cursor()
                await cur.execute(f'DELETE FROM "{user.user_class}" WHERE id = {storage["task"][0]}')
                await conn.commit()

            if data[1] == 'add':
                task = storage['task']
                print(task)
                async with aiosqlite.connect('archive.db') as conn:
                    cur = await conn.cursor()
                    await cur.execute(f'INSERT INTO "{user.user_class}" (content, subject, group_name, mediafile_id, expiration_day, gdzUrl, author, precisely) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (*task[1:],))
                    await conn.commit()

                await callback.message.edit_text(text=TEXT.get_text['hw_hub'], reply_markup=Inline.hw_inline(False, user.user_class, user.group_name_2, mode=user.hw_view))
                await callback.answer('Архивировано')
            elif data[1] == 'cancel':

                await callback.message.edit_text(text=TEXT.get_text['hw_hub'], reply_markup=Inline.hw_inline(False, user.user_class, user.group_name_2, mode=user.hw_view))
                await callback.answer('Удалено!')  
        return
    

    elif data[0] == 'edit':
        id = data[-1]
        await callback.answer('Если ты нажал на редактирование случайно, или просто передумал что-то менять - обязательно нажми "Сохранить", чтобы это задание осталось, иначе оно удалится', show_alert=True)

        with sqlite3.connect('homework.db') as conn:
            cur = conn.cursor()
            cur.execute(f'SELECT content, subject, group_name, mediafile_id, expiration_day, precisely FROM "{user.user_class}" WHERE id = {id}')
            # content, subject, group_name, mediafile_id, expiration_day = cur.fetchone()
            task = cur.fetchall()[0]

            cur.execute(f'DELETE FROM "{user.user_class}" WHERE id = {id}')
            conn.commit()

        content, subject, group_name, mediafile_id, expiration_day, precisely = task
        mediafile_id = mediafile_id.split(' ') if mediafile_id else []
        mediaToDel = storage['media']

        data = {}
    
        data['content'] = content
        data['subject'] = subject
        data['mediafile_id'] = mediafile_id
        data['expiration_day'] = expiration_day
        data['precisely'] = precisely
        data['media'] = []

        data['user_class'] = user.user_class
        data['user_group_2'] = user.group_name_2
        data['user_group_3'] = user.group_name_3
        data['subject_group'] = group_name
        


        if len(mediafile_id) == 1:
            data['message'] = await callback.message.answer_photo(photo=mediafile_id[0], caption=get_text(data), reply_markup=Inline.upload_navigation(), parse_mode='Markdown')

        elif len(mediafile_id) > 1:
            mediagroup = types.MediaGroup()
            [mediagroup.attach_photo(types.InputMediaPhoto(media=file)) for file in mediafile_id]
            data['media'] = await callback.message.answer_media_group(mediagroup)

            data['message'] = await callback.message.answer(text=get_text(data), reply_markup=Inline.upload_navigation(), parse_mode='Markdown')

        else:
            data['message'] = await callback.message.answer(text=get_text(data), reply_markup=Inline.upload_navigation(), parse_mode='Markdown')


        await state.update_data(data)
        await HWUpdate.waiting_for_content.set()
        
        await callback.message.delete()
        if mediaToDel:
            for obj in mediaToDel:
                await obj.delete()
                await asyncio.sleep(0.5)

        return
    
                
    elif data[0]=='back':
        await callback.answer()
        print(data, len(data))

        # storage = await state.get_data()
        storage['task_id'] = []
        messages = storage['media']
        storage['media'] = None
        # print(messages)
        await state.update_data(storage)

        if len(data) == 1:
            await callback.message.edit_text(text=TEXT.get_text['hw_hub'], reply_markup=Inline.hw_inline(False, user.user_class, user.group_name_2, mode=user.hw_view))

        else:
            await callback.message.edit_text(text=get_text(mode=f'hw_date_{data[1]}'), reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, mode='subjects', date=data[1]), parse_mode='Markdown')
        
        if messages:
            for obj in messages:
                await obj.delete()
                await asyncio.sleep(0.5)
                
    elif data[0] in subjects:
        # storage = await state.get_data()
        storage['task_id'] = []
        await callback.answer('Collecting tasks...')
        try: await callback.message.delete()
        except: pass
        with sqlite3.connect('school_schedule.db') as conn:
            cur = conn.cursor()
            cur.execute(f'SELECT lesson_name FROM lessons WHERE id = "{data[0]}"')
            data[0] = cur.fetchone()[0]
        
        async with aiosqlite.connect('homework.db') as conn:
            cur = await conn.cursor()
            if 'N' in data:
                data[data.index('N')] = None

            if data[-1] == 'dts':
                user.hw_view = 'dates'
                data = data[:-1]
            print('view: ', user.hw_view)
            if user.hw_view == 'dates':
                # Then, select tasks with both the subject and the specific group_name
                query = f'SELECT id, content, subject, mediafile_id, author FROM "{user.user_class}" WHERE subject = ? AND group_name '

                if data[1] == None:
                    query += 'IS ?'
                else:
                    query += '= ?'

                query += ' AND expiration_day = ?'

                await cur.execute(query, (*data,))

                homework_tasks = await cur.fetchall()
            
            else:
                # Then, select tasks with both the subject and the specific group_name
                query = f'SELECT id, content, subject, mediafile_id, author FROM "{user.user_class}" WHERE subject = ? AND group_name '

                if data[1] == None:
                    query += 'IS ?'
                else:
                    query += '= ?'

                await cur.execute(query, (*data,))
                homework_tasks = await cur.fetchall()

            # print(homework_tasks)

            if user.name in [task[-1] for task in homework_tasks]: owner = True
            else: owner = False

        tasks_text, storage = await getHWText(homework_tasks, callback, storage, owner=user.name, admin=admin)
        await state.update_data(storage)

        print('date', data[-1], len(data))
        await callback.message.answer(text=f'Все задания по предмету {str(data[0]).strip()}:\n\n'+'\n\n'.join(tasks_text), reply_markup=Inline.hw_inline(back=True, admin=admin, owner=owner, taskIds=storage['task_id'], date=data[-1] if user.hw_view=='dates' else None))


    elif data[0] == 'date':
        date = data[1]  
        await callback.answer()
        await callback.message.edit_text(text=get_text(mode=f'hw_date_{date}'), reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, mode='subjects', date=date), parse_mode='Markdown')

    elif data[0] == 'view':
        user.hw_view = data[1]
        await user.updateuser()
        await callback.answer('Изменено ✅')
        await callback.message.edit_text(text=TEXT.get_text['hw_hub'], reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, mode=data[1], changer=True))

    elif data[0] == 'archive':
        if user.fstArchive: await callback.answer()
        else:
            await callback.answer('У архива стало больше функций!\n\n1. Теперь можно переключать режим просмотра, нажимая на кнопку, как в домашке\n\n2. При просмотре архива по предметам теперь можно выбрать определенную дату', show_alert=True)
            user.fstArchive = 1
            await user.updateuser()

        if data[-1] == 'archive':
            await callback.message.edit_text(text=TEXT.get_text['archive'],
                        reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, mode=f'archive_{user.hw_view}', changer=True))
        
        elif data[1] == 'view':

            user.hw_view = data[2]
            await user.updateuser()

            await callback.message.edit_text(text=TEXT.get_text['archive'],
                            reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, mode=f'archive_{data[2]}', changer=True))
            
        
        elif data[1] == 'back':
            if data[-1] == 'back':

                await callback.message.edit_text(text=TEXT.get_text['archive'], reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, mode=f'archive_{user.hw_view}', changer=True))
            
            else:
                await callback.message.edit_text(text=f'Ниже ты можешь увидеть кнопки с датами истечения срока сдачи заданий по предмету, выбирай подходящий день и нажимай на кнопку!', reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, back=True, mode=f'archive_subject_{data[2]}'))
            
            storage = await state.get_data()
            media = storage['media']
            storage['media'] = None
            for obj in media:
                try: await obj.delete()
                except: pass
                await asyncio.sleep(0.5)

        elif data[1] == 'd':
            try: await callback.message.delete()
            except: pass
            async with aiosqlite.connect('archive.db') as conn:
                cur = await conn.cursor()

                await cur.execute(f'SELECT id, content, subject, mediafile_id, author FROM "{user.user_class}" WHERE (group_name IS NULL OR group_name = "{user.group_name_2}") AND expiration_day = "{data[2]}"')

                tasks = await cur.fetchall()

            tasks_text, storage = await getHWText(tasks, callback, storage, firstText=f'*Архив домашних заданий на {data[2]}:*', subjectNec=True)
            await state.update_data(storage)


            # print('date', data[-1], len(data))
            await callback.message.answer(text=f'\n\n'.join(tasks_text),
                                            reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, mode='archive', back=True),
                                            parse_mode='Markdown')
            
        elif data[1] == 'l':
            with sqlite3.connect('school_schedule.db') as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT lesson_name FROM lessons WHERE id = "{data[2]}"')
                subject = cur.fetchone()[0]
            with sqlite3.connect('archive.db') as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT id, content, subject, mediafile_id, author, expiration_day FROM "{user.user_class}" WHERE subject = "{subject}" AND group_name IS NULL OR group_name = "{user.group_name_2}"')
                tasks = cur.fetchall()

            today = datetime.datetime.today()
            expirations = [datetime.datetime.strptime(task[-1], '%d-%m-%Y') for task in tasks]
            tasks = [tasks[i][:-1] for i, dtm in enumerate(expirations) if (not (dtm == 12 and today.month == 1) and dtm >= today - datetime.timedelta(30))]
                    
            if len(tasks) > 1:
                await callback.message.edit_text(text=f'Ниже ты можешь увидеть кнопки с датами истечения срока сдачи заданий по предмету *{subject}*, выбирай подходящий день и нажимай на кнопку!', parse_mode='Markdown',
                        reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, back=True, mode=f'archive_subject_{data[2]}'))
                
            else:
                try: await callback.message.delete()
                except: pass
                
                tasks_text, storage = await getHWText(tasks, callback, storage, firstText=f'*Архив домашних заданий по предмету {subject}:*')

                await state.update_data(storage)

                await callback.message.answer(text=f'\n\n'.join(tasks_text),
                            reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, mode='archive', back=True, date=data[2]),
                            parse_mode='Markdown')

                
        elif data[1] == 's':
            try: await callback.message.delete()
            except: pass

            async with aiosqlite.connect('school_schedule.db') as conn:
                cur = await conn.cursor()
                await cur.execute(f'SELECT lesson_name FROM lessons WHERE id = "{data[2]}"')
                subject = (await cur.fetchone())[0]
                print(subject)

            async with aiosqlite.connect('archive.db') as conn:
                cur = await conn.cursor()
                await cur.execute(f'SELECT id, content, subject, mediafile_id, author FROM "{user.user_class}" WHERE subject = "{subject}" AND expiration_day = "{data[3]}" AND (group_name IS NULL OR group_name = "{user.group_name_2}")')
                tasks = await cur.fetchall()
                
            tasks_text, storage = await getHWText(tasks, callback, storage, firstText=f'*Архив {subject} на {data[3]}:*')

            await state.update_data(storage)
            
            await callback.message.answer(text=f'\n\n'.join(tasks_text),
                        reply_markup=Inline.hw_inline(user_class=user.user_class, user_group_2=user.group_name_2, mode='archive', back=True, date=data[2]),
                        parse_mode='Markdown')


# Complex texts assembler
async def getHWText(tasks: list, callback: CallbackQuery, storage: dict, firstText='', subjectNec=False, owner=None, admin=False):

    media_group = []
    storage['task_id'] = []
    tasks_text = [firstText] if firstText else []
    embed_counter = 0
    media = types.MediaGroup()
                
    for task in tasks:
        id, content, subject, mediafile_id, author = task

        if admin:
            storage['task_id'].append(id)
            
        elif author == owner:
            storage['task_id'].append(id)

        if mediafile_id:
            mediafile_id = mediafile_id.split(' ')
            embed_counter+=1
            photo = [types.InputMediaPhoto(media = file, caption = f'Вложение №{embed_counter}') for file in mediafile_id]
            media_group.extend(photo)
            if subjectNec: text = f"{subject}:\n{content if content else 'Задание на фото!'}\n\n📎 Фото №{embed_counter}"
            else: text = f"{content if content else 'Задание на фото!'}\n\n📎 Фото №{embed_counter}"
        else:
            if subjectNec: text = subject+':\n'+content
            else: text = content
                

        if author: 
            text += '\n\nДобавил: '+author
            if owner and owner == author:
                text += ' (ты можешь удалить своё задание по кнопке ниже)'

        tasks_text.append(text)

    if media_group:
        try:
            if len(media_group) > 1:
                for photo in media_group:
                    media.attach_photo(photo=photo)
                
                storage['media'] = await callback.message.answer_media_group(media=media)
                    
            elif len(media_group) == 1:
                storage['media'] = [await callback.message.answer_photo(media_group[0].media)]

            else:
                storage['media'] = None
        except:
            storage['media'] = [await callback.message.answer('media expired')]

    return tasks_text, storage
        

@dp.message_handler(ChatTypeFilter(types.ChatType.PRIVATE), commands=['update'])
@dp.callback_query_handler(lambda callback: callback.data == 'update')
@registration_check
async def update(message: Message | CallbackQuery, state: FSMContext, user: User, **kwargs):

    currentDay = day_translation[datetime.datetime.now(tz).strftime('%A')]
    
    data = {}
    data['subject'] = None
    data['expiration_day'] = None
    data['precisely'] = False
    data['subject_group'] = None

    try:
        with sqlite3.connect('school_schedule.db') as conn:
            cur = conn.cursor()
            cur.execute(f'SELECT lesson_name, group_name, start_time, end_time FROM "{user.user_class}" WHERE (group_name = "{user.group_name_2}" OR group_name IS NULL) AND day_name = "{currentDay}"')
            lessons = cur.fetchall()
            if lessons:
                now = datetime.datetime.now(tz).time()
                for index, (lesson_name, group, start, end) in enumerate(lessons):
                    start = tz.localize(datetime.datetime.strptime(start, '%H:%M')).time()
                    end = tz.localize(datetime.datetime.strptime(end, '%H:%M'))#.time()
                    fSeq = lessons[index+1] if index+1 < len(lessons) else (None, None, None, None)
                    if any(fSeq):
                        _, _, startNext, endNext = fSeq
                        endNext = tz.localize(datetime.datetime.strptime(endNext, '%H:%M')).time()
                        if endNext < now:
                            continue
                        startNext = tz.localize(datetime.datetime.strptime(startNext, '%H:%M')).time()
                    else:
                        startNext = (end + datetime.timedelta(minutes=20)).time()

                    if start <= now <= end.time() or end.time() <= now < startNext:
                        print(start, now, end.time(), startNext, sep='\n')
                        data['subject'] = lesson_name
                        data['subject_group'] = group

                        order = list(day_translation.values())
                        
                        cur.execute(f'SELECT DISTINCT day_name FROM "{user.user_class}" WHERE lesson_name = "{lesson_name}" AND non_original IS NULL AND (group_name IS NULL OR group_name = ?)', (user.group_name_2,))
                        days = sorted([_ for (_,) in cur.fetchall()], key=lambda x: order.index(x))

                        current_day_index = order.index(currentDay)
                        dates = [day for day in days if not order.index(day) <= current_day_index] + [f'{day}_future' for day in days]

                        data['expiration_day'] = dates[0]
                        break

                    # print(start, now, end, startNext, sep='\n')
                    
    except Exception as e: print(e)

    if isinstance(message, CallbackQuery):
        callback = message
        if not user.fstUPD:
            text = 'Добавлять домашку стало проще!\n\n1. Пиши текст задания сразу под этим сообщением, или отправь фотку с заданием в подписи\n\n2. Я теперь умею автоматически подставлять предмет и дату в новую домашку!'
            await callback.answer(text, show_alert=True)
            user.fstUPD = 1
            await user.updateuser()

        try: await callback.message.delete()
        except: pass
        message = callback.message
        
        
    data['content'] = None
    data['mediafile_id'] = []
    
    data['media'] = []

    data['user_class'] = user.user_class
    data['user_group_2'] = user.group_name_2
    
    data['message'] = await message.answer(text=get_text(data), reply_markup=Inline.upload_navigation(), parse_mode='Markdown')
    
    await state.set_data(data)
    await HWUpdate.waiting_for_content.set()
    # print('\n'.join([f'{key} {value}'for key, value in data.items()]))


# Text getting function for update()
def get_text(data: dict = None, mode: str = 'upd'):
    if mode == 'upd':
        if data.get('expiration_day', None):
            expiration = f'{data["expiration_day"].split("_")[0]}: {weekday_to_date(data["expiration_day"], year=False)}' if '-' not in data['expiration_day'] else data['expiration_day']
        else:
            expiration = None

        form = {
        'content': f"`{data['content']}`" if data.get('content', None) else 'Пока пусто, можешь написать задание сообщением',
        'subject': data['subject'] if data.get('subject', None) else 'Пока пусто, выбери из предложенных в меню',
        'photo': 'файл(ы) сверху' if data.get('mediafile_id', []) else 'Пока пусто, здесь можно добавлять фото, если есть.',
        'due_date': expiration if expiration else 'Пока не выбрано, день до которого надо сделать.'}

        text = TEXT.get_text['upd'].format(**form)

    elif mode.startswith('hw_date'):
        text = TEXT.get_text['hw_date'].format(weekday=get_weekday(mode.split('_')[-1], 'hw_date'))

    return text

async def normal_send(message: Message, mediafiles, answer=False, **kwargs):
    caption = len(mediafiles)==1

    if caption:
        kwargs['caption'] = kwargs.pop('text')
        send_message = message.edit_caption
    else:
        send_message = message.edit_text
    
    try:
        remess = await send_message(**kwargs)
    except:
        kwargs['text'] = kwargs.pop('caption')
        remess = await message.edit_text(**kwargs)

    return remess


# BACK
@dp.callback_query_handler(lambda callback: callback.data=='back' or callback.data=='back_more', state='*')
@registration_check
async def back_button(callback: CallbackQuery, state: FSMContext, **kwargs):
    data = await state.get_data()
    mediafiles = data.get('mediafile_id', [])
    await normal_send(callback.message, mediafiles, text=get_text(data), reply_markup=Inline.upload_navigation(add_more=True if len(mediafiles)>0 else False), parse_mode='Markdown')
    
    await state.update_data(data)
    # await state.reset_state(with_data=False)
    await HWUpdate.waiting_for_content.set()
    

# CONTENT
@dp.message_handler(ChatTypeFilter(types.ChatType.PRIVATE), state=HWUpdate.waiting_for_content, content_types=types.ContentTypes.TEXT)
async def proccess_text(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    data['content'] = message.text
    print(message.text)
    mediafiles = data['mediafile_id']

    callbackMessage = data['message']

    await normal_send(callbackMessage, mediafiles, text='Loading...', reply_markup=None)
    await normal_send(callbackMessage, mediafiles, text=get_text(data), reply_markup=Inline.upload_navigation(add_more=True if len(mediafiles)>0 else False), parse_mode='Markdown')
    
    await state.update_data(data)   
    

# SUBJECT
@dp.callback_query_handler(lambda callback: callback.data=='send_subject', state='*')
@registration_check
async def subject(callback: CallbackQuery, state: FSMContext, **kwargs):
    data = await state.get_data()
    if not data:
        await update(callback, state)
        return
    mediafiles = data['mediafile_id']
    user_class = data['user_class']
    user_group_2 = data['user_group_2']
    subject = data['subject']

    await normal_send(callback.message, mediafiles, text=f'*Выбери предмет*, нажав на одну из кнопок ниже:', reply_markup=Inline.choose_subject(user_class, user_group_2, subject), parse_mode='Markdown')

    await HWUpdate.waiting_for_subject.set()


@dp.callback_query_handler(lambda callback: callback.data.startswith('send_subject')==True, state=HWUpdate.waiting_for_subject)
async def proccess_subject(callback: CallbackQuery, state: FSMContext):

    with sqlite3.connect('school_schedule.db') as conn:
        cur = conn.cursor()
    
        data = await state.get_data()
        if 'группа' in callback.data.split('_')[2].lower().split(' '):
            subject_id = callback.data.split('_')[3]
            cur.execute(f"SELECT lesson_name FROM lessons WHERE id='{subject_id}'")
            data['subject'] = cur.fetchone()[0]
            data['subject_group'] = callback.data.split('_')[2]
        else:
            subject_id = callback.data.split('_')[2]
            cur.execute(f"SELECT lesson_name FROM lessons WHERE id='{subject_id}'")
            data['subject'] = cur.fetchone()[0]
            data['subject_group'] = None
        
        try:
            order = list(day_translation.values())
                                
            cur.execute(f'SELECT DISTINCT day_name FROM "{data["user_class"]}" WHERE lesson_name = "{data["subject"]}" AND non_original IS NULL AND (group_name IS NULL OR group_name = ?)', (data["user_group_2"],))
            days = sorted([_ for (_,) in cur.fetchall()], key=lambda x: order.index(x))

            current_day_index = order.index(day_translation[datetime.datetime.now(tz).strftime('%A')])
            dates = [day for day in days if not order.index(day) <= current_day_index] + [f'{day}_future' for day in days]
            # print(dates)
            data['expiration_day'] = dates[0]
        except: 
            data['expiration_day'] = None
        
        mediafiles = data['mediafile_id']

    await normal_send(callback.message, mediafiles, text=get_text(data), reply_markup=Inline.upload_navigation(add_more=True if len(mediafiles)>0 else False), parse_mode='Markdown')
    
    await state.update_data(data)
    await HWUpdate.waiting_for_content.set()


# Album of mediafiles handler
@dp.message_handler(ChatTypeFilter(types.ChatType.PRIVATE), state=[HWUpdate.waiting_for_content, HWUpdate.wait_for_more_media], content_types=types.ContentTypes.ANY, is_media_group=True)
async def proccess_album(message: Message, album: List[Message], state: FSMContext):
    """This handler will receive a complete album of any type."""
    data = await state.get_data()
    try: await data['message'].delete()
    except: pass

    files = data.get('media', [])
    media_group = types.MediaGroup()

    if await state.get_state() == HWUpdate.wait_for_more_media.state:
        for photo_id in data['mediafile_id']:
            media_group.attach_photo(types.InputMediaPhoto(media = photo_id))
    else:
        data['mediafile_id'].clear()        

    for index, obj in enumerate(album):
        if index == 0 and obj.caption:
            data['content'] = obj.caption
        if obj.photo:
            file_id = obj.photo[-1].file_id
        else:
            file_id = obj[obj.content_type].file_id
        
        try:
            # We can also add a caption to each file by specifying `"caption": "text"`
            data['mediafile_id'].append(file_id)
            media_group.attach({"media": file_id, "type": obj.content_type})
        except ValueError:
            return await message.answer("This type of album is not supported by aiogram.")
        
    data['media'] = await message.answer_media_group(media_group)
    data['message'] = await message.answer(get_text(data), reply_markup=Inline.upload_navigation(add_more=True), parse_mode='Markdown')
    await state.update_data(data)
    # await state.reset_state(with_data=False)
    await HWUpdate.waiting_for_content.set()
    
    for obj in album:
        await obj.delete()
        await asyncio.sleep(0.5)

    if files:
        for message in files:
            await message.delete()
            await asyncio.sleep(0.5)

# Single photo handler
@dp.message_handler(ChatTypeFilter(types.ChatType.PRIVATE), state=[HWUpdate.waiting_for_content, HWUpdate.wait_for_more_media], content_types=types.ContentTypes.PHOTO)# | types.ContentTypes.VIDEO)
async def proccess_single_mediafile(message: Message, state: FSMContext):
    data = await state.get_data()
    mediafile_id = message.photo[-1].file_id

    if message.caption: data['content'] = message.caption
    try:
        await message.delete()
        await data['message'].delete()
    except: pass
    files = data.get('media', [])

    if await state.get_state() == HWUpdate.wait_for_more_media.state:
        data['mediafile_id'].append(mediafile_id)
        media = types.MediaGroup()
        for file in data['mediafile_id']:
            media.attach_photo(types.InputMediaPhoto(media = file))
        data['media'] =  await message.answer_media_group(media)
        data['message'] = await message.answer(get_text(data), reply_markup=Inline.upload_navigation(add_more=True), parse_mode='Markdown')
    else:
        # print('no')
        data['media'] = []
        data['mediafile_id'] = [mediafile_id]
        data['message'] = await message.answer_photo(photo=mediafile_id, caption=get_text(data), reply_markup=Inline.upload_navigation(add_more=True), parse_mode='Markdown')
    
    
    await state.update_data(data)
    # await state.reset_state(with_data=False)
    await HWUpdate.waiting_for_content.set()

    if files:
        for photo in files:
            await photo.delete()
            await asyncio.sleep(0.5)


# ADD MORE MEDIA
@dp.callback_query_handler(lambda callback: callback.data=='send_more_media', state='*')
async def more_media(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        await update(callback, state)
        return
    mediafiles = data.get('mediafile_id', [])

    await normal_send(callback.message, mediafiles, text='*Файлы выше* - это существующие вложения.\nВидимо ты хочешь добавить еще, отправляй мне:', reply_markup=Inline.back_btn(), parse_mode='Markdown')

    await HWUpdate.wait_for_more_media.set()


# EXPIRATION TIME
@dp.callback_query_handler(lambda callback: callback.data=='send_expiration_time', state='*')
async def expires(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        await update(callback, state)
        return

    await normal_send(callback.message, data['mediafile_id'], text=TEXT.get_text['expiration'], 
                      reply_markup=Inline.choose_day(data), parse_mode='Markdown')


@dp.callback_query_handler(lambda callback: callback.data.startswith('send_date'), state='*')
async def proccess_expiration_day(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        await update(callback, state)
        return
    mediafiles = data['mediafile_id']

    splitted = callback.data.split('_')

    data['expiration_day'] = splitted[3] if splitted[2] == 'current' else f'{splitted[3]}_future'
    data['precisely'] = True

    await normal_send(callback.message, mediafiles, text=get_text(data), reply_markup=Inline.upload_navigation(add_more=True if len(mediafiles)>0 else False), parse_mode='Markdown')

    await state.update_data(data)
    

def weekday_to_date(weekday_name, year=True):
    # A dictionary mapping weekday names to their corresponding indices (0 for Monday, 6 for Sunday)
    if '-' not in weekday_name:
        weekdays = {
            'Понедельник': 0,
            'Вторник': 1,
            'Среда': 2,
            'Четверг': 3,
            'Пятница': 4,
            'Суббота': 5,
            'Воскресенье': 6
        }

        # Current date and its weekday index
        today = datetime.date.today()
        # today = datetime.date(24, 2, 19)
        today_index = today.weekday()

        # Target weekday index
        target_index = weekdays[weekday_name.split('_')[0]]

        # Calculate the difference in days
        difference = target_index - today_index

        # Adjust today's date by the difference
        if len(weekday_name.split('_')) > 1 and weekday_name.split('_')[1] == 'future':
            target_date = today + datetime.timedelta(days=7+difference)
        else:
            target_date = today + datetime.timedelta(days=difference)

        format = '%d-%m' if not year else '%d-%m-%Y'
        return target_date.strftime(format)
    
    else: return weekday_name


def get_weekday(date_str, mode='default'):
    date = datetime.datetime.strptime(date_str, '%d-%m-%Y')
    if mode == 'default':
        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    elif mode == 'hw_date':
        weekdays = ["Понедельник", "Вторник", "Среду", "Четверг", "Пятницу", "Субботу", "Воскресенье"]
    return weekdays[date.weekday()]


# APPLY CHANGES (CONFIRM)
@dp.callback_query_handler(lambda callback: callback.data.startswith('confirm'), state='*')
async def confirmation(callback: CallbackQuery, state: FSMContext):

    # Retrieve all data from the state and get User
    data = await state.get_data()
    user_name = (await User.loaduser(callback.from_user.id)).name

    if callback.data == 'confirm':
        content = data.get("content", None)
        subject = data.get("subject", None)

        if data.get("mediafile_id", []):
            mediafile_id = ' '.join(data.get("mediafile_id", []))
        else:
            mediafile_id = None

        expiration_day = data.get('expiration_day', None)    
        user_class = data.get('user_class', None)
        subject_group = data.get('subject_group', None)
        precisely = data.get('precisely')
        
        
        if subject:
            if expiration_day:
                expiration_day = weekday_to_date(expiration_day)
                if content or mediafile_id:
                    # Store the homework task in the database

                    async with aiosqlite.connect('homework.db') as conn:
                        cur = await conn.cursor()
                        condition = f' AND group_name = "{subject_group}" ' if subject_group else ''
                        await cur.execute(f'SELECT content, mediafile_id, author FROM "{user_class}" WHERE subject = "{subject}" AND expiration_day = "{expiration_day}"'+condition)
                        task = await cur.fetchone()
                        if task: # If this date is already taken, ask user if he sure wants to add a task 
                            content, mediafiles, author = task

                            text = f'На {expiration_day} уже есть добавленное задание по предмету {subject}:\n\n{content if content else "Задание на фото!"}\nДобавил: {author}\n\n*Добавить* - все равно добавить дз на эту же дату'

                            if mediafiles: 
                                mediafiles = mediafiles.split(' ')
                                if len(mediafiles) == 1:
                                    await callback.message.answer_photo(photo=mediafiles[0], caption=text, reply_markup=Inline.addAnyway(), parse_mode='Markdown')
                                else:
                                    media = types.MediaGroup()
                                    [media.attach_photo(types.InputMediaPhoto(media=file)) for file in mediafiles]
                                    data['media'] += await callback.message.answer_media_group(media)
                                    await callback.message.answer(text, reply_markup=Inline.addAnyway())

                            else:
                                await callback.message.answer(text, reply_markup=Inline.addAnyway())
                            
                            data['message'] = callback.message
                            await state.update_data(data)

                        else:

                            await cur.execute(f'INSERT INTO "{user_class}" (content, subject, group_name, mediafile_id, expiration_day, author, precisely) VALUES (?, ?, ?, ?, ?, ?, ?)',
                                        (content, subject, subject_group, mediafile_id, expiration_day, user_name, precisely))
                            await conn.commit()

                            await callback.answer('Задание добавлено!')
                            await callback.message.answer('Домашнее задание добавлено!', reply_markup=Inline.main_more_from_update_successfull(clear=True))

                            media = data['media'] if data['media'] else None
                            # Reset the state
                            try: await callback.message.delete()
                            except: pass
                            await state.reset_state(with_data=True)
                            
                            
                            if media:
                                for message in media:
                                    await message.delete()
                                    await asyncio.sleep(0.5)
                            
                else:
                    await callback.answer('Сначала отправь фото или текст задания!', show_alert=True)
            else:
                await callback.answer('Сначала укажи дату!', show_alert=True)
        else:
            await callback.answer('Сначала укажи предмет!', show_alert=True)
    
    else: # Process user's decision of adding task at taken date
        cData = callback.data.split('_')[1]
        if cData == 'add':
            content = data.get("content") if data['content'] else None
            subject = data.get("subject") if data['subject'] else None
            precisely = data.get('precisely')
            if data['mediafile_id'] != []:
                mediafile_id = ' '.join(data.get("mediafile_id"))
            else: mediafile_id = None
            expiration_day = data['expiration_day']
            expiration_day = weekday_to_date(expiration_day)
            user_class = data['user_class']
            subject_group = data['subject_group']
            async with aiosqlite.connect('homework.db') as conn:
                cur = await conn.cursor()
                await cur.execute(f'INSERT INTO "{user_class}" (content, subject, group_name, mediafile_id, expiration_day, author, precisely) VALUES (?, ?, ?, ?, ?, ?, ?)',
                            (content, subject, subject_group, mediafile_id, expiration_day, user_name, precisely))
                await conn.commit()
                
            await callback.answer('Задание добавлено!')
            await callback.message.answer('Домашнее задание добавлено!', reply_markup=Inline.main_more_from_update_successfull(clear=True))
            media = data['media'] if data['media'] else None
            try:
                await data['message'].delete()
                await callback.message.delete()
            except: pass
            await state.reset_state(with_data=True)
            if media:
                for message in media:
                    await message.delete()
                    await asyncio.sleep(0.5)


        elif cData == 'back':
            await callback.message.delete()
            await HWUpdate.waiting_for_content.set()


        elif cData == 'menu':
            commands_text = TEXT.main_menu
            await callback.message.answer(commands_text, reply_markup=Inline.commands_inline(), parse_mode='Markdown')
            await callback.message.delete()
            await data['message'].delete()
            
            media = data['media'] if data['media'] else None
            await state.reset_state()
            if media:
                for message in media:
                    await message.delete()
                    await asyncio.sleep(0.5)


def valid_day(tuples: list[tuple], mode='hw'):
    today = datetime.datetime.today().date()
    matched = []
    for tuple in tuples:
        expiration = tuple[5]
        if expiration:
            expiration = datetime.datetime.strptime(expiration, '%d-%m-%Y').date()
            if expiration.month == 12 and today.month == 1:
                matched.append(tuple)
            else:
                if mode == 'archive':
                    if expiration < today - datetime.timedelta(30): matched.append(tuple)
                elif mode == 'hw':
                    if expiration < today: matched.append(tuple)

    return matched


def compute_hash(data: dict):
    """Compute MD5 hash of the data."""
    m = hashlib.md5()
    m.update(str(data).encode('utf-8'))
    return m.hexdigest()


#### LOOP FUNCTIONS ####

# Check for expired tasks
async def check_expired_tasks():
    '''Checking homework.db for expired tasks and if there are some, moving them to archive'''
    while True:

        async with aiosqlite.connect("school_schedule.db") as conn2:
            cur2 = await conn2.cursor()
            await cur2.execute(f'SELECT class_name FROM classes')
            classes = [_[0] for _ in (await cur2.fetchall())]

            today = datetime.datetime.now(tz).weekday()
            # today = 0
            tomorrow = (datetime.datetime.now(tz) + datetime.timedelta(1)).strftime("%d-%m-%Y")
            # tomorrow = '20-02'
            tomorrow_dtm = datetime.datetime.now(tz) + datetime.timedelta(1)

        # Connect to the database and retrieve expired task ids
            for class_name in classes:
                async with aiosqlite.connect('homework.db') as conn:
                    cur = await conn.cursor()
                    await cur.execute(f'CREATE TABLE IF NOT EXISTS "{class_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, subject TEXT, group_name TEXT, mediafile_id TEXT, expiration_day TEXT, gdzUrl TEXT, author TEXT, precisely BOOLEAN DEFAULT FALSE)')

                    await cur.execute(f'SELECT id, subject, group_name, expiration_day, precisely FROM "{class_name}"')
                    tasks = await cur.fetchall()

                    for task in tasks: # If there are some schedule changes, tasks also stay synced with it

                        if task[3] == tomorrow:
                            
                            condition = ' AND group_name IS NULL ' if not task[2] else f' AND group_name = "{task[2]}" '

                            await cur2.execute(f'SELECT day_name FROM "{class_name}" WHERE lesson_name = "{task[1]}"'+condition)
                            days = await cur2.fetchall()

                            if day_translation[tomorrow_dtm.strftime('%A')] in [day for (day,) in days]:
                                pass

                            else:
                                print('changed')
                                days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
                                sorted_days = sorted([day for (day,) in days], key=lambda x: days_of_week.index(x))
                                # print(sorted_days)
                                for day in sorted_days:
                                    if days_of_week.index(day) > tomorrow_dtm.weekday():
                                        weekDayDate = weekday_to_date(day if 'Воскресенье' != day_translation[datetime.datetime.now(tz).strftime('%A')] else day+'_future')
                                        await cur.execute(f'UPDATE "{class_name}" SET expiration_day = "{weekDayDate}" WHERE id = "{task[0]}"')
                                        
                                        print(f'applied change {weekDayDate}: {task}')
                                        break
                                else:
                                    expdate = (datetime.datetime.strptime(tomorrow, '%d-%m-%Y') + datetime.timedelta(7)).strftime('%d-%m-%Y')
                                    await cur.execute(f'UPDATE "{class_name}" SET expiration_day = "{expdate}" WHERE id = "{task[0]}"')

                                    print(f'applied change + week {expdate}: {task}')
                            
                        
                        # Checking if the nearest day where subject appears is earlier than current expiration date
                        else:
                            if task[4]: continue # Skip tasks with manualy set expiration time

                            condition = ' AND group_name IS NULL ' if not task[2] else f' AND group_name = "{task[2]}" '

                            await cur2.execute(f'SELECT DISTINCT day_name FROM "{class_name}" WHERE lesson_name = "{task[1]}"'+condition)
                            days = await cur2.fetchall()
                            
                            days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
                            sorted_days = sorted(list(filter(lambda x: days_of_week.index(x[0]) > today, days)), key=lambda x: days_of_week.index(x[0]))

                            for (day,) in sorted_days:
                                if days_of_week.index(day) < datetime.datetime.strptime(task[3], '%d-%m-%Y').weekday():
                                    weekDayDate = weekday_to_date(day) # if 'Воскресенье' != day_translation[datetime.datetime.now(tz).strftime('%A')] else day+'_future'
                                    await cur.execute(f'UPDATE "{class_name}" SET expiration_day = "{weekDayDate}" WHERE id = "{task[0]}"')

                                    print(f'applied back change {weekDayDate}: {task}')
                                    break

                        
                    try:
                        await cur.execute(f'SELECT * FROM "{class_name}"')

                        expired_tasks = valid_day((await cur.fetchall()))

                        async with aiosqlite.connect('archive.db') as aconn:
                            acur = await aconn.cursor()
                            await acur.execute(f'CREATE TABLE IF NOT EXISTS "{class_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, subject TEXT, group_name TEXT, mediafile_id TEXT, expiration_day TEXT, gdzUrl TEXT, author TEXT, precisely BOOLEAN DEFAULT FALSE)')

                            # Move expired tasks to archive
                            for task in expired_tasks:
                                
                                task_id = task[0]
                                # Delete the task from the homework database
                                await cur.execute(f'DELETE FROM "{class_name}" WHERE id = ?', (task_id,))

                                # ARCHIVE
                                await acur.execute(f'INSERT INTO "{class_name}" (content, subject, group_name, mediafile_id, expiration_day, author) VALUES (?, ?, ?, ?, ?, ?)', (task[1], task[2], task[3], task[4], task[5], task[7],))
                            await aconn.commit()
                    except Exception as e:
                        await bot.send_message(ADMIN, 'Ошибка в базе данных: ' + str(e))
                        print(e)
                    
                    await conn.commit()
            # await conn2.commit()
        
        await asyncio.sleep(60*60)

# CHECK CHANGES
async def check_changes(forceUpd=False, path=''):
    """
    Checks for changes in the school schedule and applies them to the local database.

    Args:
        force_upd (bool): If True, the update is forced even if no changes are detected in hash.
        path (str): The file path to the school schedule. If you have .json schedule file, e.g. nika-data123.json, you can provide path to it.
        Otherwise schedule will be parsed by default, getting json from school website 
    """
    while True: 
        async def refresh_lessons(cur: sqlite3.Cursor):            

            for id in list(content["CLASS_EXCHANGE"].keys()):

                class_name = content['CLASSES'][id]
                # print(class_name)
                class_changes = content["CLASS_EXCHANGE"][id]

                changes_dict = {}

                for date, changes in class_changes.items():
                    day = day_translation[datetime.datetime.strptime(date, "%d.%m.%Y").strftime('%A')]

                    def dictcreator(mode: str, group=False):
                        
                        if mode == 'replace' and list(schedule_previous) == schedule_changes:
                            return
                            
                        if mode == 'delete':
                            delete_dict = {lessonWGroup if group else lesson_name: 'delete'}
                        else:
                            normal_dict = {None if mode=='add' else schedule_previous: schedule_changes}

                        if class_name not in changes_dict:
                            changes_dict[class_name] = {day : [delete_dict if mode=='delete' else normal_dict]}
                        else:
                            if day in changes_dict[class_name]:
                                changes_dict[class_name][day].append(delete_dict if mode=='delete' else normal_dict)
                            else:
                                changes_dict[class_name][day] = [delete_dict if mode=='delete' else normal_dict]


                    for subject_num, subject_details in changes.items():

                        if 'g' not in list(subject_details.keys()):

                            if subject_details['s'] == 'F':

                                cur.execute(f'SELECT lesson_name FROM "{class_name}" WHERE day_name = ? AND lesson_number = ? AND non_original IS NULL', (day, int(subject_num),))
                                lesson_name = cur.fetchone()
                                
                                if lesson_name:

                                    lesson_name = (lesson_name[0])

                                    dictcreator('delete')

                                    # cur.execute(f"DELETE FROM '{class_name}' WHERE day_name = ? AND lesson_number = ?", (day, int(subject_num),))
                                    cur.execute(f"UPDATE '{class_name}' SET non_original = 1 WHERE day_name = ? AND lesson_number = ?", (day, int(subject_num),))
                                        
                            else:

                                cur.execute(f'SELECT lesson_name, teacher_name, classroom FROM "{class_name}" WHERE day_name = ? AND lesson_number = ? AND non_original IS NULL', (day, int(subject_num),))
                                schedule_previous = cur.fetchone()
                                schedule_changes = [content['SUBJECTS'][subject_details['s'][0]],
                                                    content['TEACHERS'][subject_details['t'][0]],
                                                    content['ROOMS'][subject_details['r'][0]]]
                                if schedule_previous:
                                    dictcreator('replace')

                                    # Перезаписываем предмет
                                    cur.execute(f"UPDATE '{class_name}' SET lesson_name = ?, teacher_name = ?, classroom = ? WHERE lesson_number = ? AND day_name = ? AND non_original IS NULL",
                                                (content['SUBJECTS'][subject_details['s'][0]], content['TEACHERS'][subject_details['t'][0]], content['ROOMS'][subject_details['r'][0]], int(subject_num), day,))


                                else:

                                    dictcreator('add')

                                    # Добавляем предмет на тот индекс, который указан в subject_num
                                    if class_name.startswith(('9', '10', '11')):
                                        cur.execute(f'SELECT pair_time FROM pair_times WHERE lessons_inclued LIKE ?', (f'%{int(subject_num)}%',))
                                        pair_time = cur.fetchone()[0].split('-')
                                        print(pair_time)
                                        start_time = pair_time[0]
                                        end_time = pair_time[1]
                                    else:
                                        start_time = content['LESSON_TIMES'][subject_num][0]
                                        end_time = content['LESSON_TIMES'][subject_num][1]

                                    # cur.execute(f"UPDATE '{class_name}' SET lesson_number = lesson_number + 1 WHERE day_name = ? AND lesson_number >= ? AND non_original IS NULL", (day, int(subject_num),))
                                    cur.execute(f'''INSERT INTO '{class_name}' (day_name, lesson_number, lesson_name, teacher_name, start_time, end_time, classroom)
                                                    VALUES (?, ?, ?, ?, ?, ?, ?)''', (day, int(subject_num), content['SUBJECTS'][subject_details['s'][0]], content['TEACHERS'][subject_details['t'][0]], start_time, end_time, content['ROOMS'][subject_details['r'][0]]))

                        else:
                            # print('THERE ARE ALSO GROUPS')
                            for index, lesson_id in enumerate(subject_details['s']):
                                # print(class_name, index, day, subject_num)

                                group_name = content['CLASSGROUPS'][subject_details['g'][index]]
                                if group_name == '1 группа':
                                    group_name = 'Группа 1'
                                elif group_name == '2 группа':
                                    group_name = 'Группа 2'

                                if lesson_id in ['F', ""]:
                                    # print('yes')

                                    cur.execute(f'SELECT lesson_name FROM "{class_name}" WHERE day_name = ? AND lesson_number = ? AND group_name LIKE ? AND non_original IS NULL', (day, int(subject_num), f'%{group_name[-1]}%'))
                                    lesson_name = cur.fetchone()
                                    if lesson_name:
                                        lessonWGroup = (lesson_name[0], group_name)

                                        dictcreator('delete', True)
                                        # print(class_name, lesson_name, 'groupdelete')

                                        cur.execute(f"UPDATE '{class_name}' SET non_original = 1 WHERE day_name = ? AND lesson_number = ? AND group_name LIKE ? AND non_original IS NULL", (day, int(subject_num), f'%{group_name[-1]}%'))
                                        # cur.execute(f"DELETE FROM '{class_name}' WHERE day_name = ? AND lesson_number = ? AND group_name LIKE ?", (day, int(subject_num), f'%{group_name[-1]}%'))
                                    else:
                                        cur.execute(f'SELECT lesson_name FROM "{class_name}" WHERE day_name = ? AND lesson_number = ? AND group_name IS NULL AND non_original IS NULL', (day, int(subject_num)))
                                        lesson_name = cur.fetchone()
                                        if lesson_name:
                                            lessonWGroup = (lesson_name[0], group_name)

                                            dictcreator('delete', True)
                                            # print(class_name, lesson_name, 'groupdelete')

                                            cur.execute(f"UPDATE '{class_name}' SET non_original = 1, group_name = ? WHERE day_name = ? AND lesson_number = ? AND group_name IS NULL AND non_original IS NULL", (group_name, day, int(subject_num)))
                                            
                                else:
                                    
                                    cur.execute(f'SELECT lesson_name, teacher_name, classroom, group_name FROM "{class_name}" WHERE day_name = ? AND lesson_number = ? AND group_name LIKE ? AND non_original IS NULL', (day, int(subject_num), f'%{group_name[-1]}%'))
                                    schedule_previous = cur.fetchone()
                                    
                                    schedule_changes = [content['SUBJECTS'][lesson_id],
                                                        content['TEACHERS'][subject_details['t'][index]],
                                                        content['ROOMS'][subject_details['r'][index]],
                                                        group_name]
                                    
                                    if schedule_previous:

                                        dictcreator('replace', True)

                                        # Перезаписываем предмет
                                        cur.execute(f"UPDATE '{class_name}' SET lesson_name = ?, teacher_name = ?, classroom = ?, group_name = ? WHERE lesson_number = ? AND day_name = ? AND group_name = ? AND non_original IS NULL",
                                                    (content['SUBJECTS'][subject_details['s'][index]], content['TEACHERS'][subject_details['t'][index]], content['ROOMS'][subject_details['r'][index]], group_name, int(subject_num), day, schedule_previous[3]))

                                    else:
                                        
                                        dictcreator('add', True)

                                        lesson_name = content['SUBJECTS'][subject_details['s'][index]]
                                        teacher_name = content['TEACHERS'][subject_details['t'][index]]
                                        room = content['ROOMS'][subject_details['r'][index]]

                                        
                                        if class_name.startswith(('9', '10', '11')):
                                            cur.execute(f'SELECT pair_time FROM pair_times WHERE lessons_inclued LIKE ?', (f'%{int(subject_num)}%',))
                                            pair_time = cur.fetchone()[0].split('-')
                                            # print(pair_time)
                                            start_time = pair_time[0]
                                            end_time = pair_time[1]
                                        else:
                                            start_time = content['LESSON_TIMES'][subject_num][0]
                                            end_time = content['LESSON_TIMES'][subject_num][1]

                                        # cur.execute(f"UPDATE '{class_name}' SET lesson_number = lesson_number + 1 WHERE day_name = ? AND lesson_number >= ? AND non_original IS NULL", (day, int(subject_num),))
                                        cur.execute(f'''INSERT INTO '{class_name}' (day_name, lesson_number, lesson_name, teacher_name, start_time, end_time, classroom, group_name)
                                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (day, int(subject_num), lesson_name, teacher_name, start_time, end_time, room, group_name))
                            
                        
                print(changes_dict)
                # PLACEHOLDER FOR SCHEDULE CHANGE NOTIFICATIONS
                conn.commit()

    
        print('Parsing data...')
        
        if path: # If path provided, get schedule from local file
            with open(path, 'r', encoding='utf-8') as file:
                try:
                    content = json.load(file)
                except Exception as e:
                    print(e)
                    content = json.loads(str(file.read().split("=", 1)[1].strip().rstrip(";")))

        else: # Otherwise, parse it from the website
            # Получаем название JSON строки для парсинга (его зачем-то постоянно меняют)
            url = 'https://lyceum.nstu.ru/rasp/m.schedule.html'

            try:
                html_text = requests.get(url, verify=False).text
            except Exception as e:
                print(f"School server didn't respond with error {e}")

            soup = BeautifulSoup(html_text, 'lxml')

            # Формируем ссылку на JSON файл
            ad = soup.find_all('script', type='text/javascript')
            srcs = [_.get('src') for _ in ad]
            httpsAddress = f'https://lyceum.nstu.ru/rasp/{[src for src in srcs if str(src).startswith("nika_data")][0]}'

            try:
                response = requests.get(url=httpsAddress, verify=False)
            except Exception as error:
                print(f'https didnt work: {error}\nTrying to connect with http')
                response = requests.get(url=f'http://lyceum.nstu.ru/rasp/{[src for src in srcs if str(src).startswith("nika_data")][0]}', verify=False)
            else:
                print(f'https worked:\n{httpsAddress}')
            finally:
                print('finished parsing!')

            if response.status_code == 200:
                content = json.loads(response.text.split("=", 1)[1].strip().rstrip(";"))
            else:
                try:
                    await bot.send_message(chat_id=ADMIN, text=f'*Произошла ошибка* на школьном сервере.\n\n*Расписание может быть некорректным!*\n{response.status_code}\n{response.text}', parse_mode='Markdown')
                except: pass
                return
        
        # If there are any changed and the last message that user have in chat with bot is schedule, update this message
        async def updatePastSchedule():
            with sqlite3.connect('settings.db') as sconn:
                scur = sconn.cursor()
                scur.execute('UPDATE preferences SET temp_scdView = schedule_view, temp_class = class')
                sconn.commit()
                scur.execute('SELECT user_id, class, schedule_view, group_name_2, showClass, lastMessageId FROM preferences WHERE lastMessageType = "schedule"')
                data = scur.fetchall()
                day = day_translation[datetime.datetime.now(tz).strftime("%A")]

            classesDict = {}

            for user_id, class_name, view, group, showClass, lastMessageId in data:
                if class_name not in classesDict:

                    classesDict[class_name] = {group: [(user_id, view, showClass, lastMessageId)]}
                elif group not in classesDict[class_name]:
                    classesDict[class_name][group] = [(user_id, view, showClass, lastMessageId)]

                else:
                    classesDict[class_name][group].append((user_id, view, showClass, lastMessageId))
                     

            async with aiosqlite.connect('school_schedule.db') as conn:
                cur = await conn.cursor()

                for class_name in classesDict:
                    
                    is_tomorrow = False
                    await cur.execute(f'SELECT end_time FROM "{class_name}" WHERE day_name = ?', (day,))
                    times = sorted([time for (time,) in await cur.fetchall()], key=lambda x: tz.localize(datetime.datetime.strptime(x, '%H:%M')))
                    if times:
                        end_time = times[-1]
                        print(times, end_time, sep='\n')
                        if datetime.datetime.strptime(end_time, '%H:%M').time() < datetime.datetime.now(tz).time():
                            day = day_translation[(datetime.datetime.now(tz) + datetime.timedelta(days=1)).strftime("%A")]
                            is_tomorrow = True

                    if day == 'Воскресенье': 
                        day = 'Понедельник'
                        text = await monday_period(cur)
                    else:
                        if not is_tomorrow:
                            text = f'🗓 *Расписание на сегодня ({day}):*'
                        else:
                            text = f'🗓 *Расписание на завтра ({day}):*'

                    for group in classesDict[class_name]:
                        
                        await cur.execute(f'SELECT lesson_name, start_time, end_time, teacher_name, classroom, non_original FROM "{class_name}" WHERE day_name = "{day}" AND (group_name = "{group}" OR group_name IS NULL) AND lesson_name IS NOT NULL ORDER BY lesson_number')
                        schedule = await cur.fetchall()
                        
                        for user_id, view, showClass, lastMessageId in classesDict[class_name][group]:

                            try:
                                await bot.edit_message_text(escapeMd2(text+'\n\n' + await get_schedule(schedule, cur, view)), parse_mode='MarkdownV2', reply_markup=Inline.schedule(f'today_{day}', False, view, class_name if showClass else False), chat_id=user_id, message_id=lastMessageId)
                                print(f'edited schedule to {user_id}')
                            except Exception as e: print(e) #await bot.send_message(ADMIN, e)


        # Comparing current schedule hash with hash in database, if they're not the same, update schedule  
        from creating_database import refresh_databases
        
        schedule_hash = compute_hash(content['CLASS_SCHEDULE'])
        schedule_exchange_hash = compute_hash(content['CLASS_EXCHANGE'])

        with sqlite3.connect('school_schedule.db') as conn:
            cur = conn.cursor()
            cur.execute("SELECT hash_value FROM data_hash WHERE id = 1")
            period_stored_hash = cur.fetchone()
            cur.execute("SELECT hash_value FROM data_hash WHERE id = 2")
            schedule_exchange_stored_hash = cur.fetchone()

            if forceUpd: # If forceUpd is True, schedule will be updated no matter if their hashes match
                await refresh_databases(content)
                await refresh_lessons(cur)

            elif period_stored_hash[0] == schedule_hash:
                if schedule_exchange_stored_hash and schedule_exchange_stored_hash[0] == schedule_exchange_hash:
                    print('no changes applied')
                else:
                    await refresh_databases(content)
                    await refresh_lessons(cur)
                    if schedule_exchange_stored_hash:
                        cur.execute("UPDATE data_hash SET hash_value = ? WHERE id = 2", (schedule_exchange_hash,))
                    else:
                        cur.execute("INSERT INTO data_hash (id, hash_value) VALUES (?, ?)", (2, schedule_exchange_hash,))
                    print('lessons updated')
                    await updatePastSchedule()
            else:
                await refresh_databases(content)
                await refresh_lessons(cur)
                cur.execute("UPDATE data_hash SET hash_value = ? WHERE id = 1", (schedule_hash,))
                if schedule_exchange_stored_hash:
                    cur.execute("UPDATE data_hash SET hash_value = ? WHERE id = 2", (schedule_exchange_hash,))
                else:
                    cur.execute("INSERT INTO data_hash (id, hash_value) VALUES (?, ?)", (2, schedule_exchange_hash))
                print('whole schedule rewritten')
                await updatePastSchedule()

            conn.commit()
        await asyncio.sleep(60*60)  # Check every hour

        

async def dayend_notification(end_time, current_time, class_name, day, tomorrow_day, now=False):
    '''
    Send notification to a user when their lessons are finished.
    There are homework summary and number of lessons for tomorrow in this message 
    
    Args:
        - now (bool): If True, notification will be sent whether it's time or not.
    '''
    if end_time == current_time or now:
        # print('dayend_notification')
        with sqlite3.connect('settings.db') as conn:
            cur = conn.cursor()
            cur.execute('SELECT user_id, group_name_2 FROM "preferences" WHERE "class" = ? AND notice_dayend = "on"', (class_name,))

            users = cur.fetchall()

            if not users:
                return
        
        print(f'Sending dayend schedule to {class_name}...')

        with sqlite3.connect('school_schedule.db') as conn:
            cur = conn.cursor()
            cur.execute(f'SELECT lesson_name, start_time, end_time, group_name FROM "{class_name}" WHERE day_name = "{day if day != "Воскресенье" else "Понедельник"}" AND non_original IS NULL')
            day_schedule = cur.fetchall()
            if not day_schedule: 
                return
        

        with sqlite3.connect('homework.db') as conn:
            cur = conn.cursor()
            cur.execute(f'SELECT content, subject FROM "{class_name}" WHERE expiration_day = ? AND group_name IS NULL', (tomorrow_day,))
            ungrouped = cur.fetchall()
            
            grouped_users = {}
            for user, group in users:
                if group not in grouped_users:
                    grouped_users[group] = []
                grouped_users[group].append(user)
            
            for group, users in grouped_users.items():

                cur.execute(f'SELECT content, subject FROM "{class_name}" WHERE expiration_day = ? AND group_name = ? AND content IS NOT NULL', (tomorrow_day, group,))
                grouped_homework = cur.fetchall()

                homework = ungrouped + grouped_homework

                if homework:
                    system_message = "Ты помощник, который создает краткое ревью по предоставленным домашним заданиям ученикам в дружеской форме. Cделай это кратко и ясно. Например: 'Есть задания по русскому и математике. Также по литературе. Заданий много. поэтому приступай скорее!' ИЛИ 'Задали немного: прочитать пару страниц по лит-ре и одно задание по физике'. В конце всегда добавляй эту фразу: 'Нажимай на кнопку Подробнее'"

                    user_message = '\n'.join([f'{index+1}. {homework_tuple[0]} ({homework_tuple[1]})' for index, homework_tuple in enumerate(homework)])
                    
                    homework = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_message}
                        ]
                    )
                    homework = homework.choices[0].message.content
                    print(homework)
                    # return

                if day_schedule:
                    # Filter lessons based on the group and lessons that are for all groups (None)
                    relevant_lessons = [lesson for lesson in day_schedule if (lesson[3] == group or lesson[3] is None) and lesson[0] is not None]

                    # Format the lessons
                    schedule = [f"{index + 1}. *{lesson[0].capitalize()}*" for index, lesson in enumerate(relevant_lessons)]
                    
                    # Extract start_time and end_time
                    start_time = relevant_lessons[0][1]
                    end_time = relevant_lessons[len(schedule)-1][2]
                    lessons_amount = len(schedule)

                    # Generate message using API
    #                 completion = client.chat.completions.create(
    #                     model="gpt-3.5-turbo",
    #                     messages=[
    #                         {"role": "system", "content": "You are an intellectual assistant who helps to paraphrase the text in a moderately friendly manner for schoolchildren in Russian. You have to tell about the number of lessons, the time of the beginning and the end of school, and lead to the next message with the schedule for tomorrow. Don't be too detailed."},
    #                         {"role": "user", "content": f'''Привет! 😊 На сегодня все уроки закончились, с чем тебя и поздравляю!
# - {"Завтрa" if day != "Воскресенье" else "В понедельник"} у тебя {lessons_amount} уроков,
# - Учеба начинается с {start_time} и до {end_time}. 
# Давай посмотрим, что нас ожидает:'''}
    #                     ]
    #                 ).choices[0].message.content

                    completion = f'''Привет! 😊 На сегодня все уроки закончились, с чем тебя и поздравляю!
- {"Завтрa" if day != "Воскресенье" else "В понедельник"}'''
                    if class_name.startswith(('9', '10', '11')):
                        completion += f''' у тебя {lessons_amount} уроков{(" / "+str(lessons_amount//2)+" пары") if lessons_amount % 2 == 0 else ""},
- Учеба начинается с {start_time} и до {end_time}. 
Давай посмотрим, что нас ожидает:'''
                        
                    else:
                        completion += f''' у тебя {lessons_amount} уроков,
- Учеба начинается с {start_time} и до {end_time}. 
Давай посмотрим, что нас ожидает:'''

                    completion += f'\n\n*Расписание на {"завтра" if day != "Воскресенье" else "Понедельник"}:*\n' + '\n'.join(schedule)
                    if homework:
                        completion += f'\n\n*Кратко про домашку:*\n\n{homework}'
                    else:
                        completion += f'\n\n*Кратко про домашку:*\n\nКажется, что заданий на {"завтра" if day != "Воскресенье" else "Понедельник"} нет!\n\n'
                else:
                    completion = 'no schedule'
                
                #await bot.send_message(ADMIN, completion, parse_mode='Markdown', reply_markup=Inline.dayend_mailing())
                for user in users:
                    try:
                        await bot.send_message(user, completion, parse_mode='Markdown', reply_markup=Inline.dayend_mailing())
                    except: continue


async def prelesson_notification(current_time, subtracted_times, class_name, current_date, now2=False):
    '''
    Send notification to users 10 minutes before a lesson.
    Student will see where to go and when the lesson starts. And you can also look at the homework, if there is any in the subject.
    
    Args:
        - now (bool): If True, notification will be sent whether it's time or not.
    '''
    if current_time in subtracted_times or now2:
        with sqlite3.connect('settings.db') as conn:
            cur = conn.cursor()
            cur.execute(f'SELECT user_id, group_name_2 FROM "preferences" WHERE class = "{class_name}" AND notice_daystart = "on"')
            users = cur.fetchall()

        if not users:
            return

        print(f'Sending pre-lesson notification to {class_name}...')

        time_obj = datetime.datetime.strptime(current_time, '%H:%M')
        new_time_obj = time_obj + datetime.timedelta(minutes=10)
        start_time = new_time_obj.strftime('%H:%M')
        if start_time[0] == '0': start_time = start_time[1:]

        async with aiosqlite.connect('school_schedule.db') as conn:
            cur = await conn.cursor()
            print(current_date, start_time)
            # current_date = 'Пятница'
            await cur.execute(f'SELECT lesson_name, teacher_name, start_time, end_time, classroom, group_name FROM "{class_name}" WHERE day_name = "{current_date}" AND start_time = "{start_time}" AND non_original IS NULL')
            # cur.execute(f'SELECT lesson_name, teacher_name, start_time, end_time, classroom, group_name FROM "{class_name}" WHERE day_name = "Четверг" AND start_time = "8:15"')
            lessons = await cur.fetchall()
            if not lessons:
                return

            def getlessons(group: str=None):
                if group == None:
                    lesson = lessons[0]
                    
                else:
                    for lesson in lessons:
                        if lesson[-1] == group:
                            break

                lesson_name, teacher_name, start_time, end_time, classroom, group = lesson
                if not lesson_name:
                    return None, None
                completion = f'''_В {start_time}_ - *{lesson_name}* ({teacher_name}) *в {classroom}*{' кабинете' if classroom.isnumeric() else ''}, до _{end_time}_'''
                return [completion, lesson_name]


            if len(lessons) > 1:
                grouped = any([lesson[-1] for lesson in lessons])
                # print(f'Grouped: {grouped}')
                grouped_users = {}
                for user, group in users:
                    if group not in grouped_users:
                        grouped_users[group] = []
                    grouped_users[group].append(user)

                for group, users in grouped_users.items():
                    completion, subject = getlessons(group)
                    if not completion: continue
                    with sqlite3.connect('homework.db') as conn2: # Check if there are any homework tasks
                        cur2 = conn2.cursor()
                        cur2.execute(f'SELECT id FROM "{class_name}" WHERE subject = "{subject}" AND expiration_day = "{datetime.datetime.now(tz).strftime("%d-%m-%Y")}"')
                        if not cur2.fetchone(): ishw = False
                        else: ishw=True

                    params = {}
                    if ishw:
                        await cur.execute(f'SELECT id FROM lessons WHERE lesson_name = "{subject}"')
                        id = (await cur.fetchone())[0]
                        params = {'subject' : id}
                        if grouped: params['group'] = group

                    with sqlite3.connect('settings.db') as sconn:
                        scur = sconn.cursor()
                        for user in users:
                            try: # Send message and set 20 minute timer for it's deletion
                                msg = await bot.send_message(user, completion, parse_mode='Markdown', reply_markup=Inline.deleteMsg(**params))
                                time = (datetime.datetime.now(tz) + datetime.timedelta(minutes=20)).strftime("%H:%M")
                                scur.execute(f'UPDATE preferences SET delprelesson = "{f"{time}, {msg.message_id}"}" WHERE user_id = "{user}"')
                            except BotBlocked: # If the user banned this bot, remove the user from the database 
                                if TOKEN != os.environ.get("xhelpus"):
                                    scur.execute(f'DELETE FROM preferences WHERE user_id = "{user}"')
                                    print(f'User {user} deleted due to bot ban')
                            except Exception as e:
                                print(e)
                                
                        sconn.commit()

async def prelesson_delete(current_time):
    '''
    Delete messages 20 minutes after sending them 10 mins before a lesson
    '''
    with sqlite3.connect('settings.db') as conn:
        cur = conn.cursor()
        cur.execute(f'SELECT delprelesson FROM "preferences"')
        if not cur.fetchall(): return

        cur.execute(f'SELECT user_id, delprelesson FROM "preferences"')
        uplusdelprelesson = cur.fetchall()
        
        data = {}
        for i in uplusdelprelesson:
            if i[1]:
                data[i[0]] = i[1].split(', ')

        for user, time in data.items():
            if time[0] == current_time:
                try:
                    await bot.delete_message(int(user), time[1])
                    cur.execute(f'UPDATE preferences SET delprelesson = NULL WHERE user_id="{user}"')
                except Exception as e: print(e) 

        conn.commit()

# DAY END MAILING
async def mailing(now=False, now2=False):
    '''
    Prepare all data and start notification loop
    '''
    while True:
        conn = sqlite3.connect('school_schedule.db')
        cur = conn.cursor()
        cur.execute('SELECT class_name FROM classes')
        classes = [i for (i,) in cur.fetchall()]

        current_date = day_translation[datetime.datetime.now(tz).strftime('%A')]        
        current_time = datetime.datetime.now(tz).strftime('%H:%M')
        # current_time = '10:05'
        print(current_time)
        day = day_translation[(datetime.datetime.today() + datetime.timedelta(days=1)).strftime('%A')]

        today = datetime.datetime.now(tz)
        tomorrow_day = ((today + datetime.timedelta(days=1)) if today.weekday() != 5 else (today + datetime.timedelta(days=2))).strftime('%d-%m-%Y')

        for class_name in classes:

            with sqlite3.connect('settings.db') as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT user_id FROM preferences WHERE class = "{class_name}"')
                if not cur.fetchone():
                    continue
            
            conn = sqlite3.connect('school_schedule.db')
            cur = conn.cursor()
            cur.execute(f'SELECT start_time, end_time FROM "{class_name}" WHERE day_name = "{current_date}"')
            # cur.execute(f'SELECT start_time, end_time FROM "{class_name}" WHERE day_name = "Четверг"')

            times = cur.fetchall()
            start_times = [start[0] for start in times] if times else []
            end_time = max([datetime.datetime.strptime(i[1], '%H:%M') for i in times]).strftime('%H:%M') if times else None

            subtracted_times = []
            for start in start_times:
                # Convert the string to a datetime object
                time_obj = datetime.datetime.strptime(start, '%H:%M')
                
                # Subtract 5 minutes
                new_time_obj = time_obj - datetime.timedelta(minutes=10)
                
                # Convert back to a string
                new_time_str = new_time_obj.strftime('%H:%M')
                subtracted_times.append(new_time_str)
                # print(new_time_str)


            await prelesson_notification(current_time, subtracted_times, class_name, current_date, now2)
            await dayend_notification(end_time, current_time, class_name, day, tomorrow_day, now)
            await prelesson_delete(current_time)
            
        await asyncio.sleep(60)


@dp.message_handler(commands=['notify'])
async def admin_notify(message: Message):
    if message.from_user.id == ADMIN:
        arguments = message.get_args()
        if arguments:
            with sqlite3.connect('settings.db') as conn: 
                cur = conn.cursor()
                cur.execute('SELECT user_id FROM preferences')
                users = cur.fetchall()
            for (user,) in users:
                try:
                    await bot.send_message(user, arguments, reply_markup=Inline.deleteMsg())
                except: continue
            await message.answer(f'Done mailing:\n\n{arguments}')


@dp.callback_query_handler(lambda callback: callback.data.startswith('whisper'))
@dp.message_handler(commands=['say'])
async def whisper(message: Message | CallbackQuery, state: FSMContext):
    if isinstance(message, Message):
        if message.from_user.id == ADMIN:
            await message.answer('Choose a user:', reply_markup=Inline.whisper())
        
    else:
        data = message.data.split('_')

        if data[1].isnumeric() and len(data)==2:
            await message.message.edit_text('type a message to be sent to user', reply_markup=None)
            await state.set_state('whisper')
            await state.set_data({'user' : data[1]})


@dp.message_handler(state='whisper')
async def process_whisper(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.reset_state()
    recepient = data['user']

    try:
        await bot.send_message(recepient, 'От Админа:\n'+message.text, reply_markup=Inline.deleteMsg())
    except Exception as e: print(e)
    await message.answer(f'Message sent:\n{message.text}', reply_markup=Inline.deleteMsg())
    await message.delete()


# Hide button handler
@dp.callback_query_handler(lambda callback: callback.data == 'msg_delete')
async def hide(callback: CallbackQuery):

    user = await User.loaduser(callback.from_user.id)
    if not user.hideAlert and user.delprelesson:
        await callback.answer('Эти уведомления теперь удаляются сами с началом следующего урока, чтобы их не копилась куча!', show_alert=True)
        user.hideAlert = 1
        await user.updateuser()
    else:
        await callback.answer()

    if user.delprelesson:
        if user.delprelesson.split(', ')[1] == str(callback.message.message_id):
            user.delprelesson = None
            await user.updateuser()
                
    try:                
        await callback.message.delete()
    except MessageCantBeDeleted: await callback.answer('Это сообщение слишком старое, поэтому удалите его сами')



if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    # Start the expired task check loop as a background task
    loop.create_task(check_changes())
    loop.create_task(check_expired_tasks())
    loop.create_task(mailing())

    dp.middleware.setup(AlbumMiddleware())

    # Start the bot
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, loop=loop)