# Here are stored and waiting for their day pieces of code that were cut out of the main bot for uselessness, or because they are not finished.

# Imports and variables just for beauty
import os
import sqlite3
from openai import OpenAI
from keyboards import Inline
from aiogram import Dispatcher as dp
from aiogram.types import CallbackQuery


client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
class_name, sysmessage, changes_dict = ...


####### Schedule changes button handler
@dp.callback_query_handler(lambda callback: callback.data.startswith('mailing')==True)
async def show_more(callback: CallbackQuery):
    data = callback.data.split('_')
    await callback.answer("that's it")
    conn = sqlite3.connect('storage.db')
    cur = conn.cursor()
    cur.execute(f'SELECT message FROM updates_message_storage WHERE class = "{data[1]}"')
    message = str(cur.fetchone()[0])
    await callback.message.answer(text=message, parse_mode='MarkdownV2', reply_markup=Inline.main_menu(clear=True))



######## SCHEDULE CHANGE NOTFICATONS
conn_settings = sqlite3.connect('settings.db')
cur_settings = conn_settings.cursor()

# class_name = list(changes_dict.keys())[0]
cur_settings.execute(f'SELECT user_id FROM preferences WHERE class = "{class_name}"')
users = cur_settings.fetchall()
print(f'users: {users}, class: {class_name}')
if users:

    # changes_dict = {'past': {'10-1': {'Понедельник': [[7, 'Алгебра', 'Рожнева М.С.', '212', None]], 'Четверг': [[8, 'консультация', 'Заковряшина О.В.', '212', None]], 'Вторник': [[None], [None]]}}, 'new': {'10-1': {'Понедельник': [['delete', None]], 'Четверг' : ['replace', 'Литература', 'Дунаевская', '101'], 'Вторник': [['add', 'Русский язык', 'Олифирович', '113', None], ['add', 'Технология', 'Кузнецова Н.С.', '307', None]]}}}
    # {'10-1': {'Понедельник': [{'консультация': 'delete'}, {'консультация': 'delete'}], 'Вторник': [{None: ['консультация', 'Заковряшина О.В.', '113']}, {None: ['консультация', 'Заковряшина О.В.', '113']}]}}

    completion = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": sysmessage},
        {"role": "user", "content": str(changes_dict)}
    ]
    ).choices[0].message.content

    print(completion)
    users = [_ for (_,) in users]

    for user_id in users:
        # print(class_name)
        print(user_id)
        try:
            # await bot.send_message(chat_id=int(user_id), text=completion, reply_markup=Inline.changes_mailer(changes_dict))
            print("complete")
        except Exception as e: 
            print(e)
            continue
        # await bot.send_message(chat_id='1459843746', text=completion, reply_markup=Inline.changes_mailer(changes_dict))



# check changes functiom chatgpt prompt
sysmessage = '''
Your goal is to analyze changes in the school schedule and to communicate these changes to the students in a clear and friendly way on russian language. You are writing to one specific student, he knows his class himself, so you don't need to specify it.
As input, you get a dictionary in which:
Key is a class.
Value is another dictionary where:
Key is the day of the week.
Value is a list of changes for that day.
Change specifications:
If the key is a subject name and the value is "delete", it means that this lesson has been canceled.
If the key is a tuple (lesson, teacher, room, possibly group) and the value is similar tuple, it means that the lesson, teacher and/or room has been changed.
If the key is None and the value is a tuple (lesson, teacher, room, possibly group), it means that a new lesson has been added to the end of the schedule.
Example input data:
{'10-1': {'Понедельник': [{'консультация': 'delete'}, {'консультация': 'delete'}], 'Вторник': [{None: ['консультация', 'Заковряшина О.В.', '113']}, {None: ['консультация', 'Заковряшина О.В.', '113']}]}}
Your job is to convert this vocabulary into a clear and student friendly message in russian.

Пример ответа:
Привет! Есть небольшие изменения в расписании на этой неделе:
- В понедельник отменили две консультации.
- Во вторник добавили две консультации у Заковряшиной О.В. в кабинете 113.
- В среду заменили Русский язык на Литературу у Калюжного в 309 кабинете


Если в изменениях указана группа, не забудь уточнить это в сообщении, например: "...для 1 группы"
'''   



######## Group messages scanner for hw
@dp.message_handler(content_types=types.ContentTypes.TEXT | types.ContentTypes.PHOTO)
@registration_check
async def add_string(message: Message, state: FSMContext, album: List[Message], **kwargs):
    print(message, album, sep='\n\n')
    if message.chat.type == 'private':
        if message.text and message.text.split(':')[0].lower().strip() in ['дз', 'д/з'] or message.caption and message.caption.split(':')[0].lower().strip() in ['дз', 'д/з']:
            data = await state.get_data()
            if data and message.from_user.id in data:
                if data[message.from_user.id] > (datetime.datetime.now() - datetime.timedelta(seconds=15)):
                    await message.answer('Пожалуйста, подождите 15 секунд между отправкой заданий.')
                    return
            await state.update_data({message.from_user.id : datetime.datetime.now()})

            conn = sqlite3.connect('settings.db')
            cur = conn.cursor()
            cur.execute(f'SELECT class, group_name_2, group_name_3 FROM preferences WHERE user_id = "{message.from_user.id}"')
            fetched = cur.fetchall()
            user_class = fetched[0][0]
            user_group_2 = fetched[0][1]
            user_group_3 = fetched[0][2]

            if user_class is None:
                await message.answer('Сначала выбери класс в настройках', reply_markup=await Inline.settings(user_id=message.from_user.id))
                return

            conn = sqlite3.connect('school_schedule.db')
            cur = conn.cursor()
            cur.execute(f'SELECT lesson_name FROM "{user_class}"')
            lessons = cur.fetchall()

            subjects = sorted(set([lesson[0] for lesson in lessons if lesson[0] != None]))
            # print(subjects)

            system_message = '''Your task is to process the information from the user string and return the data as a JSON string.
            Example of input data: по русскому на субботу читать учебник на странице 65. 
            Your task is to distribute the data from this string in dictionary format - key: value. From the received data we see that the user designates the subject and the text of the task.
            You should always return a construct like this:
            {"content" : "*task text obtained from the input data if exists*", "subject" : "relevant subject if exists", "expiration_day" : "*day on which the task was assigned, if specified*"}
            There are several keys in total: content, subject, expiration_day, 
            If some data was not provided, return an empty string in the value of corresponding key.
            You must return subject like it is in list of possible subjects: ''' + ', '.join(subjects)

            try:
                user_message = ''.join(message.text.split(':')[1:]).strip()
            except:
                user_message = ''.join(message.caption.split(':')[1:]).strip()

            # print(user_message)

            completion = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message}
                    ]
                )
            # print(completion)
            # await message.answer(text=f'system: total tokens spent - {completion["usage"]["total_tokens"]}')

            completion = completion.choices[0].message.content
            try:
                data = json.loads(completion)
            except Exception as e:
                print(e)
                return

            data[message.from_user.id] = datetime.datetime.now()

            data['subject_group'] = None

            # print(data['subject'])
            if data['subject'] == '':
                data['subject'] = None
            else:
                conn = sqlite3.connect('school_schedule.db')
                cur = conn.cursor()
                cur.execute(f'SELECT group_name FROM "{user_class}" WHERE lesson_name = "{data["subject"]}"')
                lessons = cur.fetchone()[0]
                # print(lessons)
                if lessons:
                    data['subject_group'] = user_group_2

            
            if data['content'] == '':
                data['content'] = None

            data['user_class'] = user_class

            data['media'] = None

            data['user_class'] = user_class
            data['user_group_2'] = user_group_2
            data['user_group_3'] = user_group_3

            if data['expiration_day'] == '':
                data['expiration_day'] = None
            else:
                days = Inline.choose_day(data=data, returnmarkup=False)
                if data['expiration_day'] not in days:
                    data['expiration_day'] = None
                else:
                    data['expiration_day'] = data['expiration_day'].capitalize()
            
            if message.media_group_id:
                # data['mediafile_id'] = message.media_group_id
                await message.answer(text='Пожалуйста, отправьте файлы по одному, а не группой.')
            elif message.photo:
                data['mediafile_id'] = [message.photo[-1].file_id]
            else:
                data['mediafile_id'] = []

            data['media'] = None
            # print(data['subject_group'])

            # await message.forward(chat_id=message.from_user.id)
            if data['mediafile_id'] != []:
                data['message'] = await message.answer_photo(photo=message.photo[-1].file_id, caption=get_text(data), reply_markup=Inline.upload_navigation())
            else:
                data['message'] = await message.answer(text=get_text(data), reply_markup=Inline.upload_navigation())

            await state.update_data(data)

            print('\n'.join([f'{key} {value}'for key, value in data.items()]))


###### GDZ solutions parser with ChatGPT
if user_class.startswith('9') and subject.lower() == 'русский язык':
    system_message = 'Your goal is to return JSON representation of data given by user. You have to return a python dictionary with only one key "exc" and value of type string. The value should be a number of an exercise that was given by user. If the user has given an invalid exercise number, you should return "invalid" as a value of "exc" key. Example: user_message: по русскому задали номер 40 на странице 9; you return {"exc" : "40"} on it'

    user_message = content

    completon = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0301",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
    )['choices'][0]['message']['content']
    data = json.loads(completon)
    print(data)
    try:
        exc = data['exc']
        number = user_class.split('-')[0][0]
        url = f'https://gdz.ru/class-{number}/russkii_yazik/trostnecova-{number}/{exc}-nom'
        print(url)
        request = requests.get(url)
        print(request.status_code)
        print(request.text)
    except Exception as e:
        print(e)


####### ChatGPT function
@dp.message_handler(commands=['chatgpt'])
@dp.callback_query_handler(lambda callback: callback.data.startswith('openai'))
@registration_check
async def chatgpt(data: types.Message | types.CallbackQuery, **kwargs):
    if type(data) == types.Message:
        # await data.answer('Привет! Я могу поговорить с тобой на любую тему. Напиши мне что-нибудь, и я отвечу тебе.')
        await data.answer('Пока не готово...')
        
    else:
        await data.answer()
        await data.message.edit_text("Привет! Я могу поговорить с тобой на любую тему. Напиши мне что-нибудь, и я отвечу тебе.")
    # await Openai.waiting_for_prompt.set()

@dp.message_handler(state=Openai.waiting_for_prompt)
async def proccess_prompt(message: types.Message, state: FSMContext):
    prompt = message.text
    message = await message.answer('Обработка...')
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0301",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )['choices'][0]['message']['content']
    await message.edit_text(completion)



##### Old homework parsing code
    if data[0] == 'all':
        # storage = await state.get_data()
        storage['task_id'] = []
        await callback.answer('Collecting tasks...')
        temp = await callback.message.edit_text('Collecting tasks...')
        conn = sqlite3.connect('homework.db')
        cur = conn.cursor()
        cur.execute(f'SELECT id, content, subject, mediafile_id, expiration_day FROM "{user_class}" WHERE group_name IS NULL')
        homework_tasks = cur.fetchall()
        cur.execute(f'SELECT id, content, subject, mediafile_id, expiration_day FROM "{user_class}" WHERE group_name = "{user_group_2}"')
        homework_tasks += cur.fetchall()
        conn.close()

        if len(homework_tasks) == 0:
            await callback.message.edit_text('Ни одного задания не найдено!', reply_markup=Inline.main_menu(clear=True))
                    
        else:
            media_group = []
            embed_counter=0
            media = types.MediaGroup()
                        
            for task in homework_tasks:
                # if str(task[1]).lower() in SUBJECTS:
                id, content, subject, mediafile_id, expiration = task

                storage['task_id'].append(id)

                if mediafile_id:
                    mediafile_id = mediafile_id.split(' ')
                    embed_counter+=1
                    try:
                        await callback.message.answer_document(mediafile_id, caption=text)
                    except:
                                        
                        photo = [types.InputMediaPhoto(media = file, caption = f'Вложение №{embed_counter}') for file in mediafile_id]
                        media_group.extend(photo)


            if media_group:
                try:
                    if len(media_group) > 1:
                        for photo in media_group:
                            media.attach_photo(photo=photo)
                        # msg = await message.answer_media_group(media=media)
                        storage['media'] = await callback.message.answer_media_group(media=media)
                            
                    elif len(media_group) == 1:
                        storage['media'] = [await callback.message.answer_photo(media_group[0].media)]

                    else:
                        storage['media'] = None
                except:
                    await callback.message.answer('media expired')
                # print(storage['media'])
                await state.update_data(storage)


            tasks_text=[]
            embed_counter=0
            for task in homework_tasks:
            # if str(task[1]).lower() in SUBJECTS:
                id, content, subject, mediafile_id, expiration = task
                if mediafile_id:
                    embed_counter+=1
                    text = f"{str(subject).strip().capitalize()}:\n{str(content if content else 'Нет текста задания, посмотри на фото!').strip().capitalize()}.\n\n📎 Детали во вложении №{embed_counter}\n📅 Срок сдачи: {expiration}"
                    tasks_text.append(text)

                else:
                    text = f"{str(subject).strip().capitalize()}:\n{str(content).strip().capitalize()}.\n\n📅 Срок сдачи: {expiration}"
                    tasks_text.append(text)
            
            await callback.message.answer(text='\n\n'.join(tasks_text), reply_markup=Inline.hw_inline(back=True, admin=admin, taskIds=storage['task_id']), parse_mode='Markdown')
            try:
                await temp.delete()
            except: Exception