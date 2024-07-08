from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import sqlite3
import aiosqlite
import datetime


day_translation = {
    'Monday': 'Понедельник',
    'Tuesday': 'Вторник',
    'Wednesday': 'Среда',
    'Thursday': 'Четверг',
    'Friday': 'Пятница',
    'Saturday': 'Суббота',
    'Sunday': 'Воскресенье'
}

reversed_translation = {value: key for key, value in day_translation.items()}

def groupTranslate(group: str):
    try: 
        return f'Group {group.split()[-1]}' 
    except: return group


def get_subjects(user_class: str, user_group_2: str, day=None, mode='lessons'):
    '''
    Getting list of homework subjects with their emojis. 
    
    Args:
        - day (str): lessons/dates of a particular day are selected when specified
        - mode (lessons/dates): function returns lessons or dates
    '''
    with sqlite3.connect('homework.db') as conn:
        cur = conn.cursor()

        if mode == 'dates':
            cur.execute(f'SELECT DISTINCT expiration_day FROM "{user_class}" WHERE group_name IS NULL OR group_name = "{user_group_2}"')
            dates = cur.fetchall()
            if dates:
                return [date for (date,) in dates] 
            return None

        condition = f' AND expiration_day = "{day}"' if day else ''
        cur.execute(f'SELECT DISTINCT subject FROM "{user_class}" WHERE group_name IS NULL{condition}')
        subjects = cur.fetchall()

        cur.execute(f'SELECT DISTINCT subject FROM "{user_class}" WHERE group_name = "{user_group_2}"{condition}')
        grouped_subjects = cur.fetchall()

    subjectsTuplesList = []
    groupedsubjectsTuplesList = []
    with sqlite3.connect('school_schedule.db') as conn:
        cur = conn.cursor()
        for (subject,) in subjects:
            cur.execute('SELECT id, emojiName FROM lessons WHERE lesson_name = ?', (subject,))
            id, emj = cur.fetchone()
            subjectsTuplesList.append((id, emj))
        for (subject,) in grouped_subjects:
            cur.execute('SELECT id, emojiName FROM lessons WHERE lesson_name = ?', (subject,))
            id, emj = cur.fetchone()

            groupedsubjectsTuplesList.append((id, emj))

    return subjectsTuplesList, groupedsubjectsTuplesList


class Inline():
    def __init__(self) -> None:
        pass
    
    # @staticmethod
    def inline_start_command(mode: str):
        inline_startup=InlineKeyboardMarkup()
        settings = InlineKeyboardButton(text='Settings', callback_data='settings_main')
        return inline_startup.add(settings)
    
    def main_more_from_update_successfull(clear: bool=False):
        back_to_main_menu = InlineKeyboardMarkup(row_width=1)
        main = InlineKeyboardButton(text='Main Menu', callback_data=f'main_{"clear" if clear else "nav"}')
        more = InlineKeyboardButton(text='Add more >>', callback_data='update')
        return back_to_main_menu.add(more, main)

    def hw_inline(back: bool | None = False,
                  user_class: str | None = None,
                  user_group_2: str | None = None,
                  admin=False,
                  owner=False,
                  taskIds: list | None = [],
                  mode=None,
                  date: str=None,
                  changer: bool=True,
                  archive: bool=False,
                  add: bool=False,
                  solution: bool=False):
        
        hw_inline = InlineKeyboardMarkup()
        main = InlineKeyboardButton('🏠 Main Menu', callback_data='main_clear')

        if archive:
            hw_inline.row_width=2
            hw_inline.add(InlineKeyboardButton('Add', callback_data='hw_archivate_add'))
            hw_inline.insert(InlineKeyboardButton('Dont add', callback_data='hw_archivate_cancel'))
            hw_inline.add(InlineKeyboardButton('Cancel', callback_data='hw_archivate_back'))
            return hw_inline


        if mode:
            if mode == 'default':
                hw_inline.row_width=2

                if changer:
                    hw_inline.add(InlineKeyboardButton(f'⚙️ View: {"subjects" if mode == "default" else "dates"}', callback_data='hw_view_default' if mode == 'dates' else 'hw_view_dates'))

                ungrouped_subjects, grouped_subjects = get_subjects(user_class, user_group_2)

                buttons = [InlineKeyboardButton(subject, callback_data=f'hw_{id}_N') for id, subject in ungrouped_subjects]
                buttons += [InlineKeyboardButton(subject, callback_data=f'hw_{id}_{user_group_2}') for id, subject in grouped_subjects]

                hw_inline.add(*buttons)
                
                if date:
                    hw_inline.add(InlineKeyboardButton('<< Back', callback_data=f'homework'))
                else:
                    hw_inline.add(main)

                print(admin)


        
            elif mode == 'dates':
                hw_inline.row_width = 2
                if user_class and user_group_2:

                    if changer:
                        hw_inline.add(InlineKeyboardButton(f'⚙️ View: {"subjects" if mode == "default" else "dates"}', callback_data='hw_view_default' if mode == 'dates' else 'hw_view_dates'))
                    
                    dates = get_subjects(user_class, user_group_2, mode='dates')
                    reserved = 0
                    if dates:
                        today = datetime.datetime.today().date()

                        for date in sorted(dates, key=lambda x: datetime.datetime.strptime(x, '%d-%m-%Y')):
                            date_obj = datetime.datetime.strptime(date, '%d-%m-%Y').date()
                            dm = date_obj.strftime('%d-%m')

                            if date_obj == today:
                                hw_inline.add(InlineKeyboardButton(f'Due today ({dm})', callback_data=f'hw_date_{date}'))
                                reserved += 1

                            elif date_obj == today + datetime.timedelta(1):
                                hw_inline.add(InlineKeyboardButton(f'Due tomorrow ({dm})', callback_data=f'hw_date_{date}'))
                                reserved += 1

                            elif date_obj > today:

                                if sum(len(row) for row in hw_inline.inline_keyboard)-1 <= reserved:
                                    hw_inline.add(InlineKeyboardButton(f'{date_obj.strftime("%A")} ({dm})', callback_data=f'hw_date_{date}'))
                                else:
                                    hw_inline.insert(InlineKeyboardButton(f'{date_obj.strftime("%A")} ({dm})', callback_data=f'hw_date_{date}'))

                hw_inline.add(main)

            elif mode == 'subjects':
                # hw_inline.add(InlineKeyboardButton('See all', callback_data='hw_all'))

                ungrouped_subjects, grouped_subjects = get_subjects(user_class, user_group_2, day=date)
                print(ungrouped_subjects, grouped_subjects)
                
                buttons = [InlineKeyboardButton(subject, callback_data=f'hw_{id}_N_{date}') for id, subject in ungrouped_subjects]
                buttons += [InlineKeyboardButton(subject, callback_data=f'hw_{id}_{user_group_2}_{date}') for id, subject in grouped_subjects]

                hw_inline.row_width=2
                
                hw_inline.add(*buttons)
                
                if date:
                    hw_inline.add(InlineKeyboardButton('<< Back', callback_data=f'homework'))
                else:
                    hw_inline.add(main)

                print(admin)

            elif mode.startswith('archive'):
                data = mode.split('_')
                if len(data) > 1:
                    today = datetime.datetime.today()
                    if data[1] in ['default', 'dates']:
                        if changer:
                            hw_inline.add(InlineKeyboardButton(f'⚙️ View: {"subjects" if data[1] == "default" else "dates"}', callback_data='hw_archive_view_default' if data[1] == 'dates' else 'hw_archive_view_dates'))

                        if data[1] == 'dates':
                            with sqlite3.connect('archive.db') as conn:
                                cur = conn.cursor()
                                # cur.execute(f'SELECT * FROM "{user_class}" WHERE group_name IS NULL OR group_name = "{user_group_2}"')
                                cur.execute(f'SELECT DISTINCT expiration_day FROM "{user_class}" WHERE group_name IS NULL OR group_name = "{user_group_2}"')
                                expirations = [d for (d,) in cur.fetchall()]

                            dates = []
                            for expiration in expirations:
                                if expiration:
                                    dtm = datetime.datetime.strptime(expiration, '%d-%m-%Y')
                                    # if dtm.month == 12 and today.month == 1: continue
                                    if dtm >= today - datetime.timedelta(90): dates.append(expiration)

                            if dates:
                                dates = sorted(dates, key=lambda x: datetime.datetime.strptime(x, '%d-%m-%Y'))
                                hw_inline.add(*[InlineKeyboardButton(date[:-5], callback_data=f'hw_archive_d_{date}') for date in dates])
                            

                        elif data[1] == 'default':
                            with sqlite3.connect('archive.db') as conn:
                                cur = conn.cursor()
                                cur.execute(f'SELECT DISTINCT subject, expiration_day FROM "{user_class}" WHERE (group_name IS NULL OR group_name = "{user_group_2}")')
                                subjects = cur.fetchall()
                                lessons = []

                            for subject, _ in subjects:

                                if subject not in lessons:
                                    expirations = [datetime.datetime.strptime(exp, '%d-%m-%Y') for s, exp in subjects if s == subject]
                                    if not all([dtm < today - datetime.timedelta(90) for dtm in expirations]):
                                        lessons.append(subject)

                            subjects.clear()
                            with sqlite3.connect('school_schedule.db') as conn:
                                cur = conn.cursor()
                                lessonids = []
                                for lesson in lessons:
                                    cur.execute(f'SELECT id, emojiName FROM lessons WHERE lesson_name = "{lesson}"')
                                    id, emojiName = cur.fetchone()
                                    lessonids.append(id)
                                    subjects.append(emojiName)
                                
                            hw_inline.add(*[InlineKeyboardButton(subject, callback_data=f'hw_archive_l_{lessonids[i]}') for i, subject in enumerate(subjects)])
                            
                        hw_inline.add(main)


                    elif data[1] == 'subject':

                        with sqlite3.connect('school_schedule.db') as conn:
                            cur = conn.cursor()
                            cur.execute(f'SELECT lesson_name FROM lessons WHERE id = "{data[2]}"')
                            subject = cur.fetchone()[0]

                        with sqlite3.connect('archive.db') as conn:
                            cur = conn.cursor()
                            cur.execute(f'SELECT DISTINCT expiration_day FROM "{user_class}" WHERE subject = "{subject}" AND (group_name IS NULL OR group_name = "{user_group_2}")')
                            expirations = [exp for (exp,) in cur.fetchall()]

                        dates = []
                        for expiration in expirations:
                            dtm = datetime.datetime.strptime(expiration, '%d-%m-%Y')
                            if dtm >= today - datetime.timedelta(90): dates.append(expiration)

                        if dates:
                            dates = sorted(dates, key=lambda x: datetime.datetime.strptime(x, '%d-%m-%Y'))
                            for d in dates:
                                hw_inline.insert(InlineKeyboardButton(d[:-5], callback_data=f'hw_archive_s_{data[2]}_{d}'))
                             

        if admin or owner:
            hw_inline.row_width = 2
            # print(taskIds)
            buttons = []
            for index, id in enumerate(taskIds):
                buttons += [InlineKeyboardButton(f'Delete {index+1}', callback_data=f'hw_delete_{id}'), InlineKeyboardButton(f'Edit {index+1}', callback_data=f'hw_edit_{id}')]
            hw_inline.add(*buttons)

        if add: hw_inline.add(InlineKeyboardButton('Add solution', callback_data='hw_add'))
        elif solution: hw_inline.add(InlineKeyboardButton('Solution', callback_data='hw_solution'))

        if back:
            # print('backdate', date)
            if mode and mode.startswith('archive'):
                if date: callback = f'hw_archive_back_{date}'
                else: callback = 'hw_archive_back'
            else:
                if date: callback = f'hw_back_{date}'
                else: callback = 'hw_back'
            print(callback)
            hw_inline.add(InlineKeyboardButton('<< Back', callback_data=callback))


        
        return hw_inline
    

    def admin(mode: str='default', user_id: int=None):
        markup = InlineKeyboardMarkup(row_width=2)

        if mode == 'default':
            users = InlineKeyboardButton('Users', callback_data='admin_users')
            markup.add(users)

        elif mode == 'users':
            
            with sqlite3.connect('settings.db') as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT name, user_id FROM preferences')
                users = cur.fetchall()
            
            user_list = [InlineKeyboardButton(name, callback_data=f'admin_user_{str(id)}') for name, id in users]
            markup.add(*user_list)

        elif mode.startswith('sUser'):
            with sqlite3.connect('settings.db') as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT class, name, status FROM preferences WHERE user_id = "{user_id}"')
                user_class, name, status = cur.fetchone()

            if user_class:
                with sqlite3.connect('homework.db') as conn:
                    cur = conn.cursor()
                    cur.execute(f'SELECT id FROM "{user_class}" WHERE author = "{name}"')
                    id = cur.fetchone()
                    print(id)
                    print(name)
            

            ban = InlineKeyboardButton(f"Status: {'Ban' if status=='ban' else 'Access'}", callback_data=f'admin_user_{user_id}_status')
            hw = InlineKeyboardButton(f"Assignments", callback_data=f'admin_user_{user_id}_hw')
            back = InlineKeyboardButton(f"Back", callback_data=f'admin_users')

            markup.row_width = 1
            markup.add(ban)
            if user_class and id:
                markup.insert(hw)
            markup.add(back)
        
        elif mode=='hw':
            back = InlineKeyboardButton(f"Back", callback_data=f'admin_back_{user_id}')
            markup.add(back)

        markup.add(InlineKeyboardButton('Hide', callback_data='msg_delete'))
        return markup
        

    def commands_inline():
        cmdinl = InlineKeyboardMarkup(row_width=1)
        
        schedule = InlineKeyboardButton('🗓 Schedule', callback_data='schedule_today')
        update = InlineKeyboardButton('+ New task', callback_data='update')
        hw = InlineKeyboardButton('📚 Homework', callback_data='homework')
        # button4 = InlineKeyboardButton('anything more..', callback_data='more')
        cmdinl.add(hw, update, schedule)
        cmdinl.row_width = 2
        settings = InlineKeyboardButton('⚙️ Settings', callback_data='settings_main')
        archive = InlineKeyboardButton('🗃 Archive', callback_data='hw_archive')
        return cmdinl.add(settings, archive)
    

    def schedule(mode: str, change=False, view='lessons', tclass:str=None):
        schedule = InlineKeyboardMarkup()
        main_menu = InlineKeyboardButton('Main menu', callback_data='main_schedule_clear')
        back_to_week = InlineKeyboardButton('<< Back', callback_data='schedule_week')
        grade = InlineKeyboardButton(f'Grade: {tclass}', callback_data='schedule_class_scd')
        mode = mode.split('_')
        
       
        if change:
            # day = day_translation[datetime.datetime.today().strftime('%A')]
            # if mode.startswith('today') or mode.split('_')[1] == (day if day!='Воскресенье' else 'Понедельник'):
                changeView = InlineKeyboardButton(f'⚙️ Schedule: {"lessons" if view=="lessons" or not view else "pairs"}', callback_data=f'schedule_view_{mode[1]}')
                schedule.add(changeView)

        if mode[0] == 'today':
            
            schedule.row_width = 2
            
            day = mode[1]
            
            days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
            yesterday = days[days.index(day) - 1 % 6]
            tomorrow = days[(days.index(day) + 1) % 6]

            left_arrow = InlineKeyboardButton('←', callback_data=f'schedule_day_{yesterday}')
            right_arrow = InlineKeyboardButton('→', callback_data=f'schedule_day_{tomorrow}')
            
            schedule.add(left_arrow, right_arrow)#.add(main_menu)
            if tclass: schedule.add(grade)
            schedule.add(main_menu)

        
        # This is the carousel
        if mode[0] == 'week':
            schedule.row_width = 2

            day = mode[1]

            days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']

            yesterday = days[days.index(day) - 1 % 6]

            tomorrow = days[(days.index(day) + 1) % 6]

            # Create keyboard buttons
            left_arrow = InlineKeyboardButton('←', callback_data=f'schedule_{"left" if mode[-1] != "day" else "day"}_{yesterday}')
            right_arrow = InlineKeyboardButton('→', callback_data=f'schedule_{"right" if mode[-1] != "day" else "day"}_{tomorrow}')
            if mode[-1] != 'day':
                back_to_week = InlineKeyboardButton('Choose a day', callback_data='schedule_week')  # Assuming this button's callback data is 'schedule_week'

                schedule.add(left_arrow, right_arrow, back_to_week)
            else:
                schedule.add(left_arrow, right_arrow)
                if tclass: schedule.add(grade)
                schedule.insert(main_menu)

        return schedule
    

    def choose_subject(user_class, user_group_2, chosen_subject):
        
        with sqlite3.connect('school_schedule.db') as conn:
            cur = conn.cursor()
            cur.execute(f'SELECT DISTINCT lesson_name, group_name FROM "{user_class}" WHERE non_original IS NULL')

            lessons = cur.fetchall()

            subjects = InlineKeyboardMarkup(row_width = 2)

            lessons_both = [lesson[0] for lesson in lessons if lesson[1] == None and lesson[0] != None]
            lessons_grouped = [lesson[0] for lesson in lessons if lesson[1] != None and lesson[0] != None]
            # lessons_grouped_3 = [lesson[0] for lesson in lessons if lesson[1] != None and lesson[0] != None]


            unique_both = sorted([_ for _ in set(lessons_both)])
            unique_grouped = sorted([_ for _ in set(lessons_grouped)])

            tuples_both = []
            for lesson in unique_both:
                cur.execute(f'SELECT id, emojiName FROM lessons WHERE lesson_name = "{lesson}"')
                tuples_both.append(cur.fetchall()[0])

            tuples_grouped = []
            for lesson in unique_grouped:
                cur.execute(f'SELECT id, emojiName FROM lessons WHERE lesson_name = "{lesson}"')
                tuples_grouped.append(cur.fetchall()[0])

        buttons = [InlineKeyboardButton(lesson, callback_data=f'send_subject_{id}') for id, lesson in tuples_both if lesson != chosen_subject]

        if user_group_2 and unique_grouped:

            buttons.extend([InlineKeyboardButton(lesson, callback_data=f'send_subject_{user_group_2}_{id}') for id, lesson in tuples_grouped if lesson != chosen_subject])# if lesson != None]# if unique_grouped else [])# if user_group_2 == 'Группа 1' or 'Группа 2' else None

        # if user_group_3:
        #     buttons.extend([InlineKeyboardButton(lesson.capitalize(), callback_data=f'send_subject_{user_group_3}_{lesson}') for lesson in grouped if lesson != None] if lessons1 else []) if user_group_3 == 'Группа 1' else None
        #     buttons.extend([InlineKeyboardButton(lesson.capitalize(), callback_data=f'send_subject_{user_group_3}_{lesson}') for lesson in grouped if lesson != None] if lessons2 else []) if user_group_3 == 'Группа 2' else None
        #     buttons.extend([InlineKeyboardButton(lesson.capitalize(), callback_data=f'send_subject_{user_group_3}_{lesson}') for lesson in grouped if lesson != None] if lessons3 else []) if user_group_3 == 'Группа 3' else None

        else:

            return subjects.add(InlineKeyboardButton('Choose group >>', callback_data='settings_main')).add(InlineKeyboardButton('<< Back', callback_data='back'))

        subjects.add(*buttons)
        subjects.add(InlineKeyboardButton('<< Back', callback_data='back'))
        return subjects

          
    def upload_navigation(clear: bool=True, add_more: bool=False):

        uploads = InlineKeyboardMarkup()

        main = InlineKeyboardButton(text='<< Main menu', callback_data=f'main_{"clear" if clear else "nav"}')

        accept = InlineKeyboardButton('Save', callback_data='confirm')

        buttons = [
        # InlineKeyboardButton('Task >>', callback_data='send_text'),
        InlineKeyboardButton('Subject >>', callback_data='send_subject'),
        # InlineKeyboardButton('Media >>', callback_data='send_media'),
        InlineKeyboardButton('Due date >>', callback_data='send_expiration_time')]

        uploads.add(*buttons)

        if add_more:
            more = InlineKeyboardButton('Add more photo >>', callback_data='send_more_media')
            uploads.add(more)

        return uploads.add(accept).add(main)
    

    def choose_day(data: dict, returnmarkup: bool=True):

        def is_past_day(target_day: str) -> bool:
            # List of days in order for comparison

            target_day = reversed_translation[target_day]

            days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            current_day = datetime.datetime.today().strftime('%A')

            # Check if target day is before the current day in the week sequence
            return days_order.index(target_day) <= days_order.index(current_day)


        def get_next_week_day(target_day: str) -> str:
            days = {
                "Monday": 0,
                "Tuesday": 1,
                "Wednesday": 2,
                "Thursday": 3,
                "Friday": 4,
                "Saturday": 5,
                "Sunday": 6,
            }

            today = datetime.date.today()
            # Assuming reversed_translation translates day names from some language to English.
            target_day = reversed_translation[target_day]

            # Calculate days until target day
            days_until_target = (days[target_day] - today.weekday() + 7) % 7
            # print()
            if not is_past_day(day_translation[target_day]) or day_translation[datetime.datetime.today().strftime('%A')] == day_translation[target_day]:
                days_until_target += 7  # always get the day in the next week

            # Get target date
            target_date = today + datetime.timedelta(days=days_until_target)

            return target_date.strftime('%d-%m')

        

        date_markup = InlineKeyboardMarkup(row_width=2)
        back = InlineKeyboardButton('<< Back', callback_data='back')

        subject = str(data['subject']) if data['subject'] != None else data['subject']
        # print(subject)
        user_class = data['user_class']
        group_name = data['user_group_2']
        # day = data['expiration_day']


        if subject and user_class:
            with sqlite3.connect('school_schedule.db') as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT DISTINCT day_name FROM "{user_class}" WHERE lesson_name = "{subject}" AND non_original IS NULL AND (group_name IS NULL OR group_name = ?)', (group_name,))
                days = cur.fetchall()
     
            if days:
                uniques = [_ for (_,) in days]
                
                dates = [InlineKeyboardButton(text=reversed_translation[day], callback_data=f'send_date_current_{day}') for day in uniques if not is_past_day(day)]
                futures = [InlineKeyboardButton(text=f'{reversed_translation[day]}: {get_next_week_day(day)}', callback_data=f'send_date_future_{day}') for day in uniques]

                if returnmarkup:
                    return date_markup.add(*dates).add(*futures).add(back)
                else:
                    return date_markup.add(*[dates + futures])
                

        return date_markup.add(back)


    # confirm markup in past
    def back_btn():
        backbtn = InlineKeyboardMarkup()
        back = InlineKeyboardButton('<< Back', callback_data='back')
        return backbtn.add(back)
        
    
    def main_menu(clear: bool=False):
        menu = InlineKeyboardMarkup()
        schedule = InlineKeyboardButton(text='🗓 Schedule', callback_data='schedule_today')
        main = InlineKeyboardButton(text='<< Main Menu', callback_data=f'main_nav')
        return menu.add(schedule, main)
    
    def changes_mailer(updates: dict | None=None):
        def strikethrough(string: str):
            return f'*~{string}~*'
        
        def bold(string: str):
            return f'*{string}*'
        
        def replace(past: str, new: str):
            return f'*~{past}~* \\- {bold(new)}'

        string = ""

        for class_name, day_updates in updates.items():
            for day, lessons in day_updates.items():
                string += f'\n{day}\\:\n\n' if string else f'{day}\\:\n\n'
                with sqlite3.connect('school_schedule.db') as conn:
                    cur = conn.cursor()
                    cur.execute(f'SELECT lesson_name FROM "{class_name}" WHERE day_name = "{day}" AND non_original IS NULL')
                    schedule = [lesson_name for (lesson_name,) in cur.fetchall()]

                for lesson_update in lessons:
                    print(lessons)
                    # Check for delete
                    if 'delete' in lesson_update.values():
                        deleted_lesson = list(lesson_update.keys())[0]
                        schedule[schedule.index(deleted_lesson[0])] = strikethrough(deleted_lesson)
                    
                    # Check for add
                    elif None in lesson_update:
                        new_lesson = lesson_update[None][0]
                        schedule.append(bold(new_lesson))
                    
                    # Check for replace
                    else:
                        old_lesson = list(lesson_update.keys())[0]
                        new_lesson = lesson_update[old_lesson][0]
                        schedule[schedule.index(old_lesson[0])] = replace(old_lesson[0], new_lesson)

                string += '\n'.join(schedule)
                string += '\n'

            string = string.replace(".", "\\.")
            with sqlite3.connect('storage.db') as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT class FROM updates_message_storage')
                classes = cur.fetchall()
                if classes:
                    classes = [_[0] for _ in classes]
                    if class_name in classes:
                        cur.execute(f'UPDATE updates_message_storage SET message = ? WHERE class = ?', (string, class_name))
                    else:
                        cur.execute(f'INSERT INTO updates_message_storage (class, message) VALUES (?, ?)', (class_name, string))
                else:
                    cur.execute(f'INSERT INTO updates_message_storage (class, message) VALUES (?, ?)', (class_name, string))

            conn.commit()

        buttons = InlineKeyboardMarkup()
        show_more = InlineKeyboardButton(text='Details >>', callback_data=f'mailing_{class_name}')
        buttons.add(show_more)
        return buttons

    
    async def settings(user_id, mode: str | None = 'default'):
        settings = InlineKeyboardMarkup(row_width=1)
        # back = InlineKeyboardButton(text='<< Back', callback_data='settings_main')
        main_menu = InlineKeyboardButton(text='<< Save', callback_data='setreturn_main_clear')


        if mode == 'default':

            async with aiosqlite.connect('settings.db') as conn:
                cur = await conn.cursor()

                await cur.execute(f'SELECT class, group_name_2, schedule_view, showClass, temp_class FROM preferences WHERE user_id = "{user_id}"')
                user_class, group2, scheduleView, showClassdb, temp_class = await cur.fetchone()

            my_class = InlineKeyboardButton(text=f'🎓 My Grade: {user_class if user_class else "Выбрать"}', callback_data='settings_choose_class')
            notifications = InlineKeyboardButton(text=f'🔔 Notifications: choose', callback_data='settings_notice')
            settings.add(my_class)
            
            if temp_class:
                with sqlite3.connect('school_schedule.db') as conn:
                    cur = conn.cursor()

                    cur.execute(f"SELECT COUNT(*) FROM '{user_class}' WHERE group_name IS NOT NULL")
                    group = cur.fetchone()[0]

                    if group:
                        cur.execute(f'SELECT teacher_name FROM "{user_class}" WHERE lesson_name = "Ин.яз" AND group_name = "{group2}"')
                        teacher = cur.fetchone()[0].split()[0]
                        my_group_2 = InlineKeyboardButton(text=f'My Group: {groupTranslate(group2)}', callback_data='settings_choose_group_2')
                        settings.add(my_group_2)
                settings.add(notifications)

                if user_class.startswith(('9', '10', '11')):
                    if scheduleView:
                        schedule_sett = InlineKeyboardButton(text='Schedule: set up', callback_data='settings_schedule')
                        settings.add(schedule_sett)
                else:
                    showClass = InlineKeyboardButton(text=f'Show grade: {"on" if showClassdb else "off"}', callback_data='settings_schedule_class_minor')
                    settings.add(showClass)

                settings.add(main_menu)
        
        
        elif mode.startswith('choose_class'):
            settings.row_width = 4

            async with aiosqlite.connect('school_schedule.db') as conn:
                cur = await conn.cursor()

                await cur.execute(f'SELECT class_name FROM classes')
                grades = [grade for (grade,) in await cur.fetchall()]

            if mode.split('_')[-1] == 'scd':
                buttons = [InlineKeyboardButton(grade, callback_data=f'schedule_class_{grade}') for grade in grades]
            else:
                buttons = [InlineKeyboardButton(grade, callback_data=f'settings_choice_class_{grade}') for grade in grades]

            settings.add(*buttons)


        elif mode == 'choose_group_2':
            settings.row_width = 1

            with sqlite3.connect('settings.db') as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT class FROM preferences WHERE user_id={user_id}')
                class_name = cur.fetchone()[0]

            with sqlite3.connect('school_schedule.db') as conn:
                cur = conn.cursor()
                cur.execute(f'SELECT DISTINCT group_name, teacher_name FROM "{class_name}" WHERE lesson_name = "Ин.яз"')
                groupTeacher = cur.fetchall()

                if groupTeacher:

                    groupAndTeacherDict = {group_name: teacher_name for group_name, teacher_name in groupTeacher}

                    buttons = [InlineKeyboardButton(f'{groupTranslate(group)}', callback_data=f'settings_choice_group_2_{group}') for group, teacher in sorted([(group_name, teacher) for group_name, teacher in groupAndTeacherDict.items()], key=lambda x: x[0])]

                    settings.add(*buttons)

                else:
                    settings.add(InlineKeyboardButton(text='<< Back', callback_data='settings_main'))
            

        elif mode == 'notice':

            async with aiosqlite.connect('settings.db') as conn:
                cur = await conn.cursor()
                await cur.execute(f'SELECT notice_dayend, notice_daystart FROM preferences WHERE user_id = "{user_id}"')
                dayend, daystart = await cur.fetchone()

            settings.row_width = 1

            dayend = InlineKeyboardButton(text=f'Summary: {"on" if dayend == "on" else "off"}', callback_data=f'settings_notice_dayend_{"on" if dayend == "off" else "off"}')
            daystart = InlineKeyboardButton(text=f'Before class: {"on" if daystart == "on" else "off"}', callback_data=f'settings_notice_daystart_{"on" if daystart == "off" else "off"}')
            settings.add(dayend, daystart)

            settings.row_width = 2
            # dayendeg = InlineKeyboardButton(text='Summary example', callback_data='settings_notice_dayend_eg')
            daystarteg = InlineKeyboardButton(text='Notice example', callback_data='settings_notice_daystart_eg')
            settings.add(daystarteg)

            settings.row_width = 1
            back = InlineKeyboardButton(text='<< Back', callback_data='settings_main')
            settings.add(back)

        elif mode == 'schedule':

            async with aiosqlite.connect('settings.db') as conn:
                cur = await conn.cursor()
                await cur.execute(f'SELECT schedule_view, showClass FROM preferences WHERE user_id = "{user_id}"')
                view, showClass = await cur.fetchone()

                settings.row_width = 1
                chng_view = InlineKeyboardButton(text=f'View: {"lessons" if view == "lessons" else "pairs"}', callback_data=f'settings_schedule_view')
                showclass = InlineKeyboardButton(text=f'Show grade: {"on" if showClass else "off"}', callback_data=f'settings_schedule_class')
                back = InlineKeyboardButton(text='<< Back', callback_data='settings_main')

                settings.add(chng_view, showclass, back)

        return settings


    def dayend_mailing():
        buttons = InlineKeyboardMarkup(row_width=1)

        buttons.add(InlineKeyboardButton(text='Details >>', callback_data='homework_save'), InlineKeyboardButton(text='Hide', callback_data='msg_delete'))
        return buttons
    
    def chatgpt(mode: str='default'):
        if mode == 'default':
            pass

    def whisper(mode: str='default'):
        markup = InlineKeyboardMarkup(row_width=2)
        if mode == 'default':
            with sqlite3.connect('settings.db') as conn:
                cur = conn.cursor()
                cur.execute('SELECT name, user_id FROM preferences')
                users = cur.fetchall()

            buttons = [InlineKeyboardButton(name, callback_data=f'whisper_{user_id}') for name, user_id in users]

            markup.add(*buttons)

        return markup
    

    def addAnyway():
        markup = InlineKeyboardMarkup(row_width=2)

        add = InlineKeyboardButton('Add', callback_data='confirm_add')
        cancel = InlineKeyboardButton('Cancel', callback_data='confirm_menu')
        back = InlineKeyboardButton('<< Back to editor', callback_data='confirm_back')

        markup.add(add, cancel, back)
        return markup
    
    @staticmethod
    def deleteMsg(subject=None, group='N', *args, **kwargs):
        markup = InlineKeyboardMarkup()
        if subject:
            hw = InlineKeyboardButton('Task for it', callback_data=f'hw_{subject}_{group}_{datetime.datetime.today().strftime("%d-%m")}_dts')
            markup.add(hw)

        delete = InlineKeyboardButton('Hide', callback_data='msg_delete')
        markup.insert(delete)
        return markup

    def freerooms(mode='menu'):
        markup = InlineKeyboardMarkup(row_width=1)
        hide = InlineKeyboardButton('Hide', callback_data='msg_delete')

        if mode == 'menu':
            current = InlineKeyboardButton('Next class', callback_data='cabinets_current')
            day = InlineKeyboardButton('All day', callback_data='cabinets_day')
            markup.add(day, current, hide)

        if mode == 'back':
            back = InlineKeyboardButton('<< Back', callback_data='cabinets')
            markup.row_width = 2
            markup.add(back, hide)

        return markup