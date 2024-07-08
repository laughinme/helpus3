import sqlite3
import asyncio
import json
import requests
import datetime
from bs4 import BeautifulSoup
import hashlib
requests.packages.urllib3.disable_warnings()

def compute_hash(data: dict):
    """Compute MD5 hash of the data."""
    m = hashlib.md5()
    m.update(str(data).encode('utf-8'))
    return m.hexdigest()

async def refresh_databases(content: dict | None = None, path=None) -> None:
    """
    Refreshing school schedule without applying exchanges.
    This function uses only CLASS_SCHEDULE from json to build database
    
    Args:
        - content (dict): already transformed json string to python dictionary
        - path (bool): if you want to parse schedule from local file, you can provide path to it 
    
    Returns:
        actually nothing, but it creates database "school_schedule.db"
    """
    print('Refreshing database...')


    if content == None:
        if path:
            with open(path, 'r', encoding='utf-8') as file:
                try:
                    content = json.load(file)
                except Exception as e:
                    print(e)
                    content = json.loads(str(file.read().split("=", 1)[1].strip().rstrip(";"))) # remove odd js file elements

        else:
            # Получаем название JSON строки для парсинга (его зачем-то постоянно меняют)
            url = 'https://lyceum.nstu.ru/rasp/m.schedule.html'

            html_text = requests.get(url, verify=False).text

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

    conn = sqlite3.connect('school_schedule.db')
    cur = conn.cursor()

    cur.execute(f'DROP TABLE IF EXISTS "classes"')
    # Create table for classes
    cur.execute('''
    CREATE TABLE IF NOT EXISTS classes (
        id TEXT,
        class_name TEXT
    )
    ''')

    for number, classes in content['CLASSES'].items():
        cur.execute('INSERT OR IGNORE INTO classes (id, class_name) VALUES (?, ?)', (number, classes,))
        
    cur.execute(f'DROP TABLE IF EXISTS "classrooms"')

    # Create table for classrooms
    cur.execute('''
    CREATE TABLE IF NOT EXISTS classrooms (
        id TEXT,
        room TEXT
    )
    ''')
    

    for id, room in content["ROOMS"].items():
        cur.execute(f'INSERT OR IGNORE INTO classrooms (id, room) VALUES (?, ?)', (id, room))
        

    cur.execute(f'DROP TABLE IF EXISTS "lessons"')
    

    cur.execute('''CREATE TABLE IF NOT EXISTS lessons (
        id TEXT,
        lesson_name TEXT,
        emojiName TEXT
    )''')


    emojis = {
        'виртуальная реальность': 'Virtual Reality 🕶️',
        'Алгебра': 'Algebra ➗',
        'Алгоритмы решения экономиче...': 'Algorithms for Economic Problems 💹',
        'Биология': 'Biology 🦋',
        'География': 'Geography 🌍',
        'География НСО': 'Geography of NSO 🌏',
        'Геометрия': 'Geometry 📐',
        'Занимательное черчение': 'Interesting Drafting 🖋️',
        'Избранные вопросы математик...': 'Selected Questions of Mathematics 🔢',
        'Изо': 'Art 🎨',
        'Ин.яз': 'Foreign Language 🇺🇸',
        'Индивидуальный проект': 'Individual Project 🔍',
        'Инженер авиастроительного п...': 'Aerospace Engineering ✈️',
        'Инженерная графика': 'Engineering Graphics 📊',
        'ИнфоКУРС': 'InfoCourse 💻',
        'Информатика': 'Computer Science 💾',
        'Искусство': 'Art 🎭',
        'История': 'History 📜',
        'ИТ физика': 'IT Physics ⚛️',
        'ИТ экономика': 'IT Economics 💰',
        'Классный час': 'Class Hour 🕒',
        'Консультация': 'Consultation 💬',
        'КП по математике': 'Math Projects 🧮',
        'Культура Японии': 'Japanese Culture 🇯🇵',
        'Литература': 'Literature 📚',
        'Литературное чтениечтение': 'Literary Reading 📖',
        'Математика': 'Mathematics 🔢',
        'Методы решения физических з...': 'Methods for Solving Physics Problems 🧬',
        'Музыка': 'Music 🎵',
        'Навигационная астрономия': 'Navigational Astronomy 🌌',
        'Наглядная геометрия': 'Visual Geometry 📏',
        'Наш край Сибирь': 'Our Region Siberia 🐻',
        'ОБЖ': 'Safety Education 🚒',
        'Обществознание': 'Social Studies 👥',
        'Окружающий мир': 'The World Around Us 🌳',
        'Олимпиадная математика': 'Olympiad Mathematics 🥇',
        'ОЛиСК': 'OLiSK 🏫',
        'ОРКСЭ': 'ORCSE 📊',
        'Основы 3Д модедирования': 'Basics of 3D Modeling 🖥️',
        'Основы авиамоделирования': 'Basics of Aircraft Modeling ✈️',
        'Основы информатики': 'Basics of Computer Science 💻',
        'Основы финансовой грамотности': 'Basics of Financial Literacy 💳',
        'Практическая биология': 'Practical Biology 🔬',
        'Предпрофильная подготовка': 'Pre-Professional Training 📚',
        'Программирование': 'Programming 💻',
        'Программирование Кумир': 'Kumir Programming 🖥️',
        'Программирование практика': 'Programming Practice 💻',
        'Прогрммирование на Python': 'Python Programming 🐍',
        'Психология': 'Psychology 🧠',
        'Разговор о важном': 'Talk About Important Things 💬',
        'Решение олимпиадных задач': 'Solving Olympiad Problems 🏆',
        'Решение олимпиадных задач п...': 'Solving Olympiad Problems 🏆',
        'Риторика': 'Rhetoric 🗣️',
        'Родная литература (русская)': 'Native Literature (Russian) 📚',
        'Родной язык (русский)': 'Native Language (Russian) 📝',
        'Русский язык': 'Russian Language 🇷🇺',
        'Спец курс по экономике': 'Special Course in Economics 💹',
        'Стратегия смыслового чтения': 'Strategy of Meaningful Reading 📖',
        'Технический английский': 'Technical English 🗣️',
        'Технология': 'Technology 🔧',
        'Технопредпринимательство': 'Tech Entrepreneurship 💼',
        'Физика': 'Physics ⚛️',
        'Физика лаб': 'Physics Lab 🧪',
        'Физика практика': 'Physics Practice 🧲',
        'Физкультура': 'Physical Education 🏃‍♂️',
        'Химия': 'Chemistry 🔬',
        'Химия от теории к практике': 'Chemistry from Theory to Practice 🧪',
        'Химия практика': 'Chemistry Practice 🔬',
        'Экология': 'Ecology 🌿',
        'Экономика': 'Economics 💹',
        'Экспериментальная физика': 'Experimental Physics 🔬',
        'Элементы математической логики': 'Elements of Mathematical Logic 🧠',
        'Юные естествоиспытатели': 'Young Naturalists 🌱',
        'Японский язык': 'Japanese Language 🇯🇵',
        'УПК': 'UPK 📚',
        'Бассейн': 'Swimming Pool 🏊‍♂️',
        'Театр': 'Theater 🎭',
        'Обед': 'Lunch 🍽️',
        'Экскурсия': 'Excursion 🚌'
    }

    for id, lesson in content["SUBJECTS"].items():
        if lesson in emojis: emj = emojis[lesson]
        else: emj = lesson
        cur.execute(f'INSERT OR IGNORE INTO lessons (id, lesson_name, emojiName) VALUES (?, ?, ?)', (id, lesson, emj))
        

    cur.execute(f"DROP TABLE IF EXISTS days")
    

    # Create table for days
    cur.execute('''
    CREATE TABLE IF NOT EXISTS days (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day_name TEXT
    )
    ''')

    # Prepopulate days table with the names of the days
    days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    for day in days:
        cur.execute(f'INSERT OR IGNORE INTO days (day_name) VALUES ("{day}")')


    cur.execute('''DROP TABLE IF EXISTS "updates_message_storage"''')

    # Period for schedule
    cur.execute('DROP TABLE IF EXISTS period')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS period (
        prefix TEXT,
        value
    )''')   

    period = next(iter(content["PERIODS"]))

    for key, value in content["PERIODS"][period].items():
        cur.execute(f'''INSERT OR IGNORE INTO period (prefix, value) VALUES ("{key}", "{value}")''')

    
    cur.execute(f"DROP TABLE IF EXISTS data_hash")
    
    # Hash storage to know when it's time to update schedule
    cur.execute('''
    CREATE TABLE IF NOT EXISTS data_hash (
        id INTEGER PRIMARY KEY,
        hash_value TEXT
    )
    ''')
    cur.execute(f'INSERT INTO data_hash (id, hash_value) VALUES (1, ?)', (compute_hash(content['CLASS_SCHEDULE']),))
    

    cur.execute(f"DROP TABLE IF EXISTS groups")
    

    cur.execute(f'CREATE TABLE IF NOT EXISTS groups (id TEXT, group_name TEXT)')

    for group_number, group_name in content['CLASSGROUPS'].items():
        cur.execute(f'INSERT OR IGNORE INTO groups (id, group_name) VALUES (?, ?)', (group_number, group_name))
        

    cur.execute(f"DROP TABLE IF EXISTS pair_times")
    cur.execute(f'CREATE TABLE IF NOT EXISTS pair_times (lessons_inclued TEXT, pair_time TEXT)')
    pairs = {
        '1-2': '8:30-10:00',
        '3-4': '10:15-11:45',
        '5-6': '12:10-13:40',
        '7-8': '14:00-15:30',
        '9-10': '15:45-17:15'
    }
    for lessons, pair_time in pairs.items():
        cur.execute(f'INSERT OR IGNORE INTO pair_times (lessons_inclued, pair_time) VALUES (?, ?)', (lessons, pair_time))


    cur.execute('SELECT class_name FROM classes')
    classes = [i[0] for i in cur.fetchall()]

    to_remove  = []
    for class_name in classes:

        if list(filter(lambda x: content["CLASSES"][x] == class_name, content["CLASSES"]))[0] not in [grade for grade in content["CLASS_SCHEDULE"] [list(content['PERIODS'].keys())[0]]]:
            to_remove.append(class_name)
            print('to remove:', to_remove)  # Removing classes, that are 
            
    for i in to_remove:
        classes.remove(i)

    for class_name in classes:
        # cur.execute("SELECT id FROM 'classes' WHERE class_name=?", (class_name,))
        # class_id = int(list(cur.fetchone())[0])
        # print(class_name, class_id)

        cur.execute(f'DROP TABLE IF EXISTS "{class_name}"')
        

        cur.execute(f'''
        CREATE TABLE IF NOT EXISTS "{class_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_name TEXT,
            lesson_number INTEGER,
            lesson_name TEXT,
            teacher_name TEXT,
            start_time TEXT,
            end_time TEXT,
            classroom TEXT,
            group_name TEXT,
            non_original TEXT
        )
        ''')

        
        cur.execute("SELECT id FROM 'days'")
        day_ids = [i[0] for i in cur.fetchall()]

        for day_id in day_ids:

            cur.execute("SELECT day_name FROM 'days' WHERE id=?", (day_id,))
            day_name = cur.fetchone()[0]

            lessons_og = content["CLASS_SCHEDULE"] [list(content['PERIODS'].keys())[0]] [list(filter(lambda x: content["CLASSES"][x] == class_name, content["CLASSES"]))[0]]
            
            lessons = [lessons_og[key] for key in lessons_og if key.startswith(str(day_id))]
            lesson_num_unindex = [key for key in lessons_og if key.startswith(str(day_id))]

            def weekday_lessons_construction(day: list,
                                            content: dict | None = content,
                                            capitalize: bool | None = False) -> None:
                
                lessons_index, teacher_index, cabinet_index, groups_index = list(), list(), list(), list()

                subject_names = list()

                for elem in day:
                    if len(elem['s']) == 1:
                        lessons_index.append(elem['s'][0])
                        teacher_index.append(elem['t'][0])
                        cabinet_index.append(elem['r'][0])
                    else:
                        lessons_index.append(elem['s'])
                        teacher_index.append(elem['t'])
                        cabinet_index.append(elem['r'])
                        groups_index.append(elem['g'])

                # This is the full version of the code:
                for lesson in lessons_index:
                    if isinstance(lesson, str):
                        subject_names.append(content['SUBJECTS'][lesson])
                    elif isinstance(lesson, list):
                        subject_names.append([content['SUBJECTS'][i] if i != '' else None for i in lesson])

                # This is a shortened version of the same code 
                teachers_names = [content['TEACHERS'][teacher] if isinstance(teacher, str) else [content['TEACHERS'][i] if i != '' else None for i in teacher] for teacher in teacher_index]
                cabinets = [content['ROOMS'][cabinet] if isinstance(cabinet, str) else [content['ROOMS'][i] if i != '' else None for i in cabinet] for cabinet in cabinet_index]
                groups = [[content['CLASSGROUPS'][i] for i in group] for group in groups_index] if groups_index else None

                groupsindex = -1
                for index, subject in enumerate(subject_names):
                    if lesson_num_unindex[index][1] != '0':
                        lesson_number = lesson_num_unindex[index][1:]
                    else:
                        lesson_number = lesson_num_unindex[index][2]

                    if isinstance(subject, list):
                        
                        groupsindex+=1
                        for i, lesson in enumerate(subject):

                            lesson_name = lesson
                            teacher_name = teachers_names[index][i]

                            group_name = groups[groupsindex][i]
                            if group_name == '1 группа':
                                group_name = 'Группа 1'
                            elif group_name == '2 группа':
                                group_name = 'Группа 2'

                            classroom = cabinets[index][i]

                            if class_name.startswith(('9', '10', '11')):

                                #pairCheckNum!!!!!!!!!! = lesson_number

                                if index == 0:
                                    previous_lessons = []
                                else:
                                    previous_lessons = [subject_names[index-1][i], teachers_names[index-1][i], cabinets[index-1][i]]

                                current_lesson = [lesson_name, teacher_name, classroom]

                                if index == len(subject_names)-1:
                                    next_lessons = []
                                else:
                                    next_lessons = [subject_names[index+1][i], teachers_names[index+1][i], cabinets[index+1][i]]


                                if current_lesson in next_lessons or (next_lessons and teacher_name == next_lessons[1]):

                                    cur.execute(f'SELECT lessons_inclued, pair_time FROM pair_times WHERE lessons_inclued LIKE "%{lesson_number}%"')
                                    lessons_included, pair_time = cur.fetchone()
                                    
                                    if lesson_number == lessons_included.split('-')[-1]:
                                        start_time = content['LESSON_TIMES'][lesson_number][0]
                                        end_time = (datetime.datetime.strptime(start_time, '%H:%M') + datetime.timedelta(hours=1.5)).strftime('%H:%M')

                                    else:
                                        start_time = pair_time.split('-')[0]
                                        end_time = pair_time.split('-')[1]
                
                                elif current_lesson in previous_lessons or (previous_lessons and teacher_name == previous_lessons[1]):

                                    cur.execute(f'SELECT lessons_inclued, pair_time FROM pair_times WHERE lessons_inclued LIKE "%{lesson_number}%"')
                                    lessons_included, pair_time = cur.fetchone()

                                    if lesson_number == lessons_included.split('-')[0]:
                                        start_time = content['LESSON_TIMES'][str(int(lesson_number)-1)][0]
                                        end_time = (datetime.datetime.strptime(start_time, '%H:%M') + datetime.timedelta(hours=1.5)).strftime('%H:%M')

                                    else:
                                        start_time = pair_time.split('-')[0]
                                        end_time = pair_time.split('-')[1]
                            else:
                                start_time = content['LESSON_TIMES'][lesson_number][0]
                                end_time = content['LESSON_TIMES'][lesson_number][1]


                            cur.execute(f'''INSERT INTO "{class_name}" (day_name, lesson_number, lesson_name, teacher_name, start_time, end_time, classroom, group_name) 
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                        (day_name, lesson_number, lesson_name, teacher_name, start_time, end_time, classroom, group_name))
                            
        
                    else:
                        lesson_name = subject
                        teacher_name = teachers_names[index]
                        classroom = cabinets[index]
                        group_name = None


                        if class_name.startswith(('9', '10', '11')):

                            # print(lesson_num_unindex, pairCheckNum, 'yes')

                            if index == 0:
                                previous_lesson = []
                            else:
                                previous_lesson = [subject_names[index-1], teachers_names[index-1], cabinets[index-1]]

                            current_lesson = [lesson_name, teacher_name, classroom]

                            if index == len(subject_names)-1:   
                                next_lesson = []
                            else:
                                next_lesson = [subject_names[index+1], teachers_names[index+1], cabinets[index+1]]

                            if current_lesson == next_lesson or (next_lesson and teacher_name == next_lesson[1]):

                                cur.execute(f'SELECT lessons_inclued, pair_time FROM pair_times WHERE lessons_inclued LIKE "%{lesson_number}%"')
                                lessons_included, pair_time = cur.fetchone()

                                if lesson_number == lessons_included.split('-')[1] and not (current_lesson == previous_lesson or (previous_lesson and teacher_name == previous_lesson[1])):
                                    start_time = content['LESSON_TIMES'][lesson_number][0]
                                    end_time = (datetime.datetime.strptime(start_time, '%H:%M') + datetime.timedelta(hours=1.5)).strftime('%H:%M')

                                else:
                                    start_time = pair_time.split('-')[0]
                                    end_time = pair_time.split('-')[1]

                            elif current_lesson == previous_lesson or (previous_lesson and teacher_name == previous_lesson[1]):

                                cur.execute(f'SELECT lessons_inclued, pair_time FROM pair_times WHERE lessons_inclued LIKE "%{lesson_number}%"')
                                lessons_included, pair_time = cur.fetchone()

                                if lesson_number == lessons_included.split('-')[0] and not (current_lesson == next_lesson or (next_lesson and teacher_name == next_lesson[1])):
                                    start_time = content['LESSON_TIMES'][str(int(lesson_number)-1)][0]
                                    end_time = (datetime.datetime.strptime(start_time, '%H:%M') + datetime.timedelta(hours=1.5)).strftime('%H:%M')

                                else:
                                    start_time = pair_time.split('-')[0]
                                    end_time = pair_time.split('-')[1]
                            else:

                                start_time = content['LESSON_TIMES'][lesson_number][0]
                                end_time = content['LESSON_TIMES'][lesson_number][1]

                        else:
                            start_time = content['LESSON_TIMES'][lesson_number][0]
                            end_time = content['LESSON_TIMES'][lesson_number][1]


                        cur.execute(f'''INSERT INTO "{class_name}" (day_name, lesson_number, lesson_name, teacher_name, start_time, end_time, classroom, group_name) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                    (day_name, lesson_number, lesson_name, teacher_name, start_time, end_time, classroom, group_name))
                        
            weekday_lessons_construction(lessons)
    conn.commit()
    conn.close()


if __name__ == '__main__':
    asyncio.run(refresh_databases())