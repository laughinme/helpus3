
# Homework Helper 

A telegram bot that shows homework, schedules, sending notifications and helps you get your schoolwork in order

## Features

- Showing homework synchronized with the school schedule
- Schedule parsed from the school website
- Customizable homework and schedule display
- Notifications system, user is notified before each lesson and after all lessons
- Storing expired tasks in archive
- Fine-tuning of the bot by the user

## Screenshots

My bot has a user-friendly interface, thanks to the fact that it's on Telegram. You can see some screenshots [right here](https://github.com/laughinme/helpus3/tree/additional/images).

## Bot construction

This bot works on the aiogram framework version 2.25.1. The code has many features that allow you to connect to databases asynchronously; manage dates, times and mailings using the datetime module. 

I think it's important to know how functions work or how bot's databases built, so here is the guide:

### Schedule

The schedule is parsed from the school website, where it is located thanks to Nika-soft. The schedule file itself is a json string that has the schedule for classes, teachers and also exchanges in the schedule. As for the [guide](https://github.com/laughinme/helpus3/blob/main/additional/JSON_Nika_description.pdf) I was given, the formatted data is written to the database. You can also see real [example](https://github.com/laughinme/helpus3/blob/main/additional/nika.json) of this json. This is what it looks like:

| Column             | Description                                                      |
| ----------------- | ------------------------------------------------------------------- |
| `id` | just for number |
| `day_name` | I think you can guess |
| `lesson_number` | lesson number on a particular day |
| `lesson_name` | lesson name |
| `teacher_name` | one who teaches |
| `start_time` | when lesson starts (for pair schedule it might be different) |
| `end_time` | when lesson ends (changes for pairs as well) |
| `classroom` | study room |
| `non_original` | shows if this lesson canceled |

and this database tables names are names of the classes they contain info of

### Homework
Archive database has the same structure as this

| Column             | Description                                                      |
| ------------------ | ---------------------------------------------------------------- |
| `id` | just for number |
| `content` | text of the task |
| `subject` | guess what? |
| `group_name` | group of user who added this task |
| `mediafile_id` | telegram mediafile id |
| `expiration_day` | %d.%m.%Y format date when task expires |
| `gdzUrl` | nevermind |
| `author` | user who added this task |
| `precisely` | if task's date was chosen by user (not automatically) |

if precisely = True, date will not be changed as schedule updates

### Settings

I'm really proud that i made my own OOP way to interact with users, while all other dbs use sql requests. This database stores information about users and bot uses this db without direct sql code, some kind of self-made ORM. Class User does this.

| Column             | Description                                                      |
| ----------------- | ------------------------------------------------------------------- |
| `id` | just for number |
| `user_id` | user's telegram id |
| `class` | user's class name |
| `group_name_2` | if class is divided into groups, it shown here|
| `group_name_3` | nevermind |
| `notice_dayend` | on/off - whether to notice user after all lessons |
| `notice_daystart` | on/off - whether to notice user before all lessons |
| `name` | user's full name |
| `schedule_view` | pairs/lessons - since 9th grade you can choose different view |
| `hw_view` | default/dates - show tasks for days/for subjects |
| `firstSchedule` | False until user opens schedule |
| `status` | True = user banned |
| `fstUPD` | whether user ever uploaded a task |
| `hwUpd` | whether user ever opened homework menu |
| `hideAlert` | whether user ever hidden a message with button |
| `temp_class` | temporary class field, needed for class changing function in schedule settings |
| `delprelesson` | needed for automatic deletion of pre-lesson notice |
| `temp_scdView` | temporary schedule view, needed for settings |
| `interactions` | number of registered user's interactions with bot |
| `fstArchive` | whether user ever opened archive |
| `lastMessageType` | name of the last used function |
| `lastMessageId` | id of the last sent message |

Most boolean fields are needed to show alert of updates

## Running the bot
First off you have to define environment variables, I use `secret.env` in the project folder to store them, here is the specification below:

| Variable             | Description                                                      |
| ----------------- | ------------------------------------------------------------------- |
| `OPENAI_API_KEY` | if you want to use chatgpt api in the bot, you should provide api key |
| `BOT_TOKEN` | Your telegram bot token |
| `admin_id` | Admin telegram user.id, allows you to access the admin panel |

Now make sure you are in the bot folder inside cmd. If not, use command:

```cmd
    cd path_to_bot_folder
```

You should also install all the requirements from file using this commands in cmd:

```cmd
    pip install -r requirements.txt
```
Now you can run the bot using this:

```cmd
    python bot.py
```

## Thanks

A huge thank you to the [Nika-soft](https://nikasoft.ru/) team who made this whole project possible. Thanks to Ivan, who provided me with a tutorial on how to use their JSON