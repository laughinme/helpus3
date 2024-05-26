import sqlite3

# I just do experiments here

def deploy():

    conn = sqlite3.connect("settings.db")
    cur = conn.cursor()

    # cur.execute(f"ALTER TABLE preferences ADD COLUMN lastMessageType TEXT")
    # cur.execute(f"ALTER TABLE preferences DROP COLUMN lastMessage")
     
    # cur.execute("UPDATE preferences SET hw_view = 'default' WHERE hw_view IS NULL")

    conn.commit()   


#     cur.execute('''CREATE TABLE IF NOT EXISTS "preferences_temp" (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     user_id INTEGER,
#     class TEXT DEFAULT "1а",
#     group_name_2 TEXT DEFAULT "Группа 1",
#     group_name_3 TEXT,
#     notice_dayend TEXT DEFAULT "on",
#     notice_daystart TEXT DEFAULT "on",
#     name TEXT,
#     schedule_view TEXT DEFAULT "lessons",
#     hw_view TEXT DEFAULT "default",
#     firstSchedule BOOLEAN DEFAULT FALSE,
#     status BOOLEAN DEFAULT FALSE,
#     fstUPD BOOLEAN DEFAULT FALSE,
#     hwUpd BOOLEAN DEFAULT FALSE,
#     hideAlert BOOLEAN DEFAULT FALSE,
#     temp_class TEXT,
#     showClass BOOLEAN DEFAULT TRUE,
#     delprelesson TEXT,
#     temp_scdView TEXT,
#     interactions INTEGER DEFAULT 0,
#     fstArchive BOOLEAN DEFAULT FALSE
# )''')
    
#     cur.execute('INSERT INTO "preferences_temp" SELECT * FROM preferences')
#     cur.execute('DROP TABLE preferences')
#     cur.execute('ALTER TABLE preferences_temp RENAME TO preferences')
#     conn.commit()
    
    import datetime
    conn = sqlite3.connect('archive.db')
    cur = conn.cursor()

    # cur.execute(f'SELECT DISTINCT subject, expiration_day FROM "9а"')
    # subjects = cur.fetchall()
    # lessons = []
    # today = datetime.datetime.today()
    # for subject, _ in subjects:
    #     if subject not in lessons:
    #         expirations = [datetime.datetime.strptime(e, '%d-%m-%Y') for s, e in subjects if s == subject]
    #         if not all([dtm < today - datetime.timedelta(30) for dtm in expirations if dtm != 12 and today.month != 1]):
    #             lessons.append(subject)
    # print(lessons)

    # cur.execute('DELETE FROM "9а" WHERE id=190')

    # cur.execute(f'SELECT name FROM sqlite_master WHERE type="table"')
    # tables = [table for (table,) in cur.fetchall()]
    # print(tables)
    # for table in tables:
    #     try:
    #         cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "precisely" BOOLEAN DEFAULT FALSE')
    #         cur.execute(f"""
    #         UPDATE '{table}'
    #         SET expiration_day = CASE
    #             WHEN SUBSTR(expiration_day, 4, 2) NOT IN ('10', '11', '12') THEN expiration_day || '-2024'
    #             ELSE expiration_day || '-2023'
    #         END""")

    #     except Exception as e: print(e)

    # Обновление строк, где месяц не равен 10, 11 или 12 (прибавляем -2024)
    

    conn.commit()

    conn = sqlite3.connect('homework.db')
    cur = conn.cursor()
    # nigger = ('ale', 'Алгебра', '24-04-2024', 'admin')
    # cur.execute(f'INSERT INTO "9а" (content, subject, expiration_day, author) VALUES (?, ?, ?, ?)', tuple(nigger))
    
    # cur.execute(f'UPDATE "9а" SET expiration_day = "22-02-2024" WHERE id=284')

    # cur.execute(f'SELECT name FROM sqlite_master WHERE type="table"')
    # tables = [table for (table,) in cur.fetchall()]
    # print(tables)
    # for table in tables:
    #     try:
    #         cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "precisely" BOOLEAN DEFAULT FALSE')
    #         cur.execute(f"""
    #         UPDATE '{table}'
    #         SET expiration_day = CASE
    #             WHEN SUBSTR(expiration_day, 4, 2) NOT IN ('10', '11', '12') THEN expiration_day || '-2024'
    #             ELSE expiration_day || '-2023'
    #         END""")

    #     except Exception as e: print(e)

    conn.commit()


if __name__ == '__main__':
    deploy()