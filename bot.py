from ai_generator import generate_content, get_fallback_content
import telebot
from telebot import types, apihelper
from db import Database
import time
import random
import os
from dotenv import load_dotenv

# ================= ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ =================
load_dotenv()  # Загружает переменные из .env файла

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]

# Проверка на случай если токены не загрузились
if not TOKEN:
    raise ValueError("⚠️ TELEGRAM_BOT_TOKEN не найден в .env файле!")
if not ADMIN_IDS:
    print("⚠️ ADMIN_IDS не найден в .env файле!")

bot = telebot.TeleBot(TOKEN)
db = Database()

DIFFICULTIES = {
    'easy': '🟢 Легко (AI)',
    'medium': '🟡 Средне (AI)',
    'hardcore': '🟣 Хардкор 18+ (Карточки)'
}

user_states = {} 
apihelper.API_TIMEOUT = 60

class UserState:
    def __init__(self):
        self.step = 'IDLE'
        self.game_data = {}

def get_user_state(user_id):
    if user_id not in user_states:
        user_states[user_id] = UserState()
    return user_states[user_id]

# ================= КЛАВИАТУРЫ =================
def get_difficulty_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [types.InlineKeyboardButton(label, callback_data=f"diff_{key}") 
               for key, label in DIFFICULTIES.items()]
    markup.add(*buttons)
    return markup

def get_game_control_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Выполнил", callback_data="act_done"),
        types.InlineKeyboardButton("❌ Правда", callback_data="act_truth")
    )
    markup.add(types.InlineKeyboardButton("🏁 Закончить игру", callback_data="game_end"))
    return markup

def get_truth_control_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Ответил", callback_data="truth_done"),
        types.InlineKeyboardButton("⏭ Пропустить", callback_data="truth_skip")
    )
    return markup

def get_admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 Непроверенные карточки", callback_data="admin_unverified"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("🔙 Выход", callback_data="admin_exit")
    )
    return markup

# ================= ОБРАБОТЧИКИ (ИГРОК) =================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    db.add_user(user_id, message.from_user.username, message.from_user.first_name)
    state = get_user_state(user_id)
    state.step = 'IDLE'
    state.game_data = {}
    
    text = f"👋 Привет, {message.from_user.first_name}!\n\n"
    text += "Я бот для игры «Правда или Действие».\n"
    text += "Генерирую задания через AI или использую проверенные карточки.\n\n"
    text += "/newgame — начать новую игру\n"
    
    if user_id in ADMIN_IDS:
        text += "/admin — панель администратора\n"
        text += "/myid — узнать свой ID"
    
    bot.reply_to(message, text)

@bot.message_handler(commands=['myid'])
def show_my_id(message):
    user_id = message.from_user.id
    text = (
        f"🆔 **Ваш Telegram ID:** `{user_id}`\n\n"
        f"👑 **Админы в коде:** `{ADMIN_IDS}`\n\n"
        f"✅ Если ваш ID есть в списке — /admin будет работать."
    )
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['test'])
def test_command(message):
    user_id = message.from_user.id
    bot.reply_to(message, f"✅ Бот работает!\nВаш ID: `{user_id}`", parse_mode='Markdown')

@bot.message_handler(commands=['newgame'])
def start_new_game(message):
    user_id = message.from_user.id
    db.add_user(user_id, message.from_user.username, message.from_user.first_name)
    
    state = get_user_state(user_id)
    active_game = db.get_active_game(message.chat.id)
    
    if active_game:
        if state.step != 'GAME_ACTIVE':
            state.step = 'GAME_ACTIVE'
            state.game_data['game_id'] = active_game['id']
            state.game_data['chat_id'] = active_game['chat_id']
            state.game_data['creator_id'] = active_game['creator_id']
            state.game_data['difficulty'] = active_game['difficulty']
            state.game_data['context'] = active_game['context_tags']
            state.game_data['current_turn'] = active_game['current_player_index']
            
            players_db = db.get_game_players(active_game['id'])
            state.game_data['players'] = [p['player_name'] for p in players_db]
            state.game_data['used_titles'] = []
            
            bot.reply_to(message, "🔄 Найдена активная игра. Восстанавливаю...")
            send_task_with_buttons(message.chat.id, state, use_saved=True)
            return
        else:
            bot.reply_to(message, "⚠️ Игра уже активна!")
            return

    state.step = 'WAIT_DIFFICULTY'
    state.game_data = {'creator_id': user_id, 'chat_id': message.chat.id}
    
    text = "🎲 **Выберите сложность:**\n\n" \
           "🟢 **Легко:** AI (без посторонних)\n" \
           "🟡 **Средне:** AI (креатив)\n" \
           "🟣 **Хардкор:** Карточки (18+)"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=get_difficulty_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith('diff_'))
def handle_difficulty(call):
    user_id = call.from_user.id
    state = get_user_state(user_id)
    if state.step != 'WAIT_DIFFICULTY': return

    difficulty = call.data.replace('diff_', '')
    state.game_data['difficulty'] = difficulty
    
    bot.edit_message_text(f"✅ Сложность: **{DIFFICULTIES[difficulty]}**\n\nВведите игроков:", 
                          call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    state.step = 'WAIT_PLAYERS'
    bot.send_message(call.message.chat.id, "Имена через запятую или число (4).")

# ================= ОБЩИЙ ХЕНДЛЕР — С ПРОВЕРКОЙ НА КОМАНДЫ =================
@bot.message_handler(func=lambda message: True)
def handle_game_setup(message):
    # ✅ БЛОКИРУЕТ ПЕРЕХВАТ КОМАНД
    if message.text and message.text.startswith('/'):
        return
    
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if state.step not in ['WAIT_PLAYERS', 'WAIT_CONTEXT']: return
    if state.game_data.get('creator_id') != user_id: return

    if state.step == 'WAIT_PLAYERS':
        players_input = message.text.strip()
        if players_input.isdigit():
            players = [f"Игрок {i+1}" for i in range(int(players_input))]
        else:
            players = [p.strip() for p in players_input.split(',') if p.strip()]
        
        if len(players) < 2:
            bot.reply_to(message, "⚠️ Минимум 2 игрока.")
            return

        state.game_data['players'] = players
        
        if state.game_data['difficulty'] == 'hardcore':
            state.game_data['context'] = 'general'
            finalize_game_setup(message.chat.id, state)
        else:
            state.step = 'WAIT_CONTEXT'
            bot.reply_to(message, "📝 **Опишите обстоятельства:**\n(или «пропустить»)")

    elif state.step == 'WAIT_CONTEXT':
        context_text = message.text.strip()
        state.game_data['context'] = 'general' if context_text.lower() in ['пропустить', 'skip', '-'] else context_text
        finalize_game_setup(message.chat.id, state)

def finalize_game_setup(chat_id, state):
    game_id = db.create_game(
        chat_id=chat_id,
        creator_id=state.game_data['creator_id'],
        difficulty=state.game_data['difficulty'],
        context_tags=state.game_data['context']
    )
    
    for player_name in state.game_data['players']:
        db.add_player_to_game(game_id, state.game_data['creator_id'], player_name)
    
    state.step = 'GAME_ACTIVE'
    state.game_data['game_id'] = game_id
    state.game_data['current_turn'] = 0
    state.game_data['used_titles'] = []
    
    bot.send_message(chat_id, f"🎉 **Игра началась!**\nИгроки: {', '.join(state.game_data['players'])}", parse_mode='Markdown')
    send_task_with_buttons(chat_id, state, use_saved=False)

# ================= AI-ГЕНЕРАЦИЯ =================
def get_ai_content(content_type: str, state) -> dict:
    difficulty = state.game_data.get('difficulty', 'easy')
    context = state.game_data.get('context', 'general')
    used_titles = state.game_data.get('used_titles', [])
    
    if difficulty == 'hardcore':
        card = db.get_card(difficulty, content_type, None)
        if card:
            return {'is_hardcore': True, 'text': card['text'], 'title': None, 'context': None}
        return {'is_hardcore': True, 'text': 'Карточка не найдена.', 'title': None, 'context': None}
    
    ai_result = generate_content(content_type=content_type, difficulty=difficulty, context=context, used_titles=used_titles)
    
    if not ai_result:
        fallback = get_fallback_content(content_type, difficulty)
        return {'is_hardcore': False, 'text': fallback['text'], 'title': fallback.get('title', ''), 'context': fallback.get('context', '')}
    
    if ai_result.get('title') and ai_result['title'] not in ['Ошибка', 'Запасное задание']:
        if 'used_titles' not in state.game_data:
            state.game_data['used_titles'] = []
        state.game_data['used_titles'].append(ai_result['title'])
        if len(state.game_data['used_titles']) > 20:
            state.game_data['used_titles'] = state.game_data['used_titles'][-20:]
    
    return {'is_hardcore': False, 'text': ai_result['text'], 'title': ai_result.get('title', ''), 'context': ai_result.get('context', '')}

# ================= ОТПРАВКА ЗАДАНИЙ =================
def send_task_with_buttons(chat_id, state, use_saved=False):
    players = state.game_data['players']
    turn_index = state.game_data.get('current_turn', 0)
    current_player = players[turn_index % len(players)]
    game_id = state.game_data.get('game_id')
    
    if use_saved and game_id:
        saved_task = db.get_current_task(game_id)
        if saved_task and saved_task['current_task_text']:
            content = {'is_hardcore': state.game_data.get('difficulty') == 'hardcore', 'text': saved_task['current_task_text'], 'title': saved_task['current_task_title'], 'context': saved_task['current_task_context']}
            _send_task_message(chat_id, current_player, content, state)
            return
    
    loading_msg = bot.send_message(chat_id, f"🎲 {current_player}, готовлю задание...")
    content = get_ai_content('dare', state)
    
    try:
        bot.delete_message(chat_id, loading_msg.message_id)
    except:
        pass
    
    if game_id:
        db.save_current_task(game_id, content['text'], content.get('title', ''), content.get('context', ''), 'dare')
    
    _send_task_message(chat_id, current_player, content, state)

def _send_task_message(chat_id, current_player, content, state):
    if content.get('is_hardcore'):
        message_text = f"🎯 **{current_player}**, твоё задание:\n\n{content['text']}"
    else:
        message_text = f"🎯 **{current_player}**, твоё задание:\n\n📛 **{content['title']}**\n📍 _{content['context']}_\n\n{content['text']}"
    
    bot.send_message(chat_id, message_text, parse_mode='Markdown')
    control_msg = bot.send_message(chat_id, "⬇️ **Выберите действие:**", parse_mode='Markdown', reply_markup=get_game_control_keyboard())
    state.game_data['control_message_id'] = control_msg.message_id
    state.game_data['question_mode'] = False

def send_truth_question(chat_id, state, use_saved=False):
    players = state.game_data['players']
    turn_index = state.game_data.get('current_turn', 0)
    current_player = players[turn_index % len(players)]
    game_id = state.game_data.get('game_id')
    
    if use_saved and game_id:
        saved_task = db.get_current_task(game_id)
        if saved_task and saved_task['current_task_text']:
            content = {'is_hardcore': state.game_data.get('difficulty') == 'hardcore', 'text': saved_task['current_task_text'], 'title': saved_task['current_task_title'], 'context': saved_task['current_task_context']}
            _send_truth_message(chat_id, current_player, content, state)
            return
    
    loading_msg = bot.send_message(chat_id, f"❓ {current_player}, готовлю вопрос...")
    content = get_ai_content('truth', state)
    
    try:
        bot.delete_message(chat_id, loading_msg.message_id)
    except:
        pass
    
    if game_id:
        db.save_current_task(game_id, content['text'], content.get('title', ''), content.get('context', ''), 'truth')
    
    _send_truth_message(chat_id, current_player, content, state)

def _send_truth_message(chat_id, current_player, content, state):
    if content.get('is_hardcore'):
        message_text = f"❓ **{current_player}**, вопрос «Правда»:\n\n{content['text']}"
    else:
        message_text = f"❓ **{current_player}**, вопрос «Правда»:\n\n📛 **{content['title']}**\n📍 _{content['context']}_\n\n{content['text']}"
    
    bot.send_message(chat_id, message_text, parse_mode='Markdown')
    control_msg = bot.send_message(chat_id, "⬇️ **Ты ответил на вопрос?**", parse_mode='Markdown', reply_markup=get_truth_control_keyboard())
    state.game_data['control_message_id'] = control_msg.message_id
    state.game_data['question_mode'] = True

def delete_control_message(chat_id, state):
    control_msg_id = state.game_data.get('control_message_id')
    if control_msg_id:
        try:
            bot.delete_message(chat_id, control_msg_id)
        except Exception as e:
            print(f"⚠️ Не удалось удалить сообщение: {e}")
        state.game_data['control_message_id'] = None

# ================= УПРАВЛЕНИЕ ИГРОЙ =================
@bot.callback_query_handler(func=lambda call: call.data in ['act_done', 'act_truth', 'game_end', 'truth_done', 'truth_skip'])
def handle_game_actions(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    state = get_user_state(user_id)
    
    active_game = db.get_active_game(chat_id)
    if not active_game:
        bot.answer_callback_query(call.id, "⚠️ Игра не найдена в БД", show_alert=True)
        return

    if state.step != 'GAME_ACTIVE' or state.game_data.get('game_id') != active_game['id']:
        state.step = 'GAME_ACTIVE'
        state.game_data['game_id'] = active_game['id']
        state.game_data['chat_id'] = active_game['chat_id']
        state.game_data['creator_id'] = active_game['creator_id']
        state.game_data['difficulty'] = active_game['difficulty']
        state.game_data['context'] = active_game['context_tags']
        state.game_data['current_turn'] = active_game['current_player_index']
        players_db = db.get_game_players(active_game['id'])
        state.game_data['players'] = [p['player_name'] for p in players_db]
        delete_control_message(chat_id, state)
        
        saved_task = db.get_current_task(state.game_data['game_id'])
        if saved_task and saved_task['current_task_text']:
            if saved_task['current_task_type'] == 'dare':
                send_task_with_buttons(chat_id, state, use_saved=True)
            else:
                send_truth_question(chat_id, state, use_saved=True)
            return

    game_id = state.game_data.get('game_id')
    delete_control_message(chat_id, state)
    
    players = state.game_data['players']
    turn_index = state.game_data.get('current_turn', 0)
    current_player_name = players[turn_index % len(players)]
    
    if call.data == 'act_done':
        db.update_player_score_by_name(game_id, current_player_name, 1)
        bot.answer_callback_query(call.id, "✅ Зачет! +1 балл")
        time.sleep(0.5)
        next_turn(chat_id, state)
    elif call.data == 'act_truth':
        bot.answer_callback_query(call.id, "❓ Отвечай на вопрос!")
        time.sleep(0.5)
        send_truth_question(chat_id, state, use_saved=False)
    elif call.data == 'truth_done':
        bot.answer_callback_query(call.id, "✅ Ответ засчитан! (без баллов)")
        time.sleep(0.5)
        next_turn(chat_id, state)
    elif call.data == 'truth_skip':
        db.update_player_score_by_name(game_id, current_player_name, -1)
        bot.answer_callback_query(call.id, "⏭ Пропущено! -1 балл")
        time.sleep(0.5)
        next_turn(chat_id, state)
    elif call.data == 'game_end':
        check_and_finish_game(chat_id, call, state)

def check_and_finish_game(chat_id, call, state):
    game_id = state.game_data.get('game_id')
    players = state.game_data['players']
    player_count = len(players)
    total_turns = db.get_total_turns(game_id)
    
    if total_turns % player_count == 0:
        finish_game(chat_id, state)
    else:
        turns_remaining = player_count - (total_turns % player_count)
        current_player_name = players[total_turns % player_count]
        bot.answer_callback_query(call.id, f"⏳ Сначала завершите круг!", show_alert=True)
        bot.send_message(chat_id, f"⚠️ **Нельзя закончить игру сейчас!**\n\nЧтобы все участвовали поровну, нужно завершить текущий круг.\nОсталось ходов: **{turns_remaining}**\nСледующий игрок: **{current_player_name}**", parse_mode='Markdown')
        send_task_with_buttons(chat_id, state, use_saved=True)

def finish_game(chat_id, state):
    game_id = state.game_data.get('game_id')
    if not game_id:
        bot.send_message(chat_id, "⚠️ Ошибка: ID игры не найден.")
        return
    delete_control_message(chat_id, state)
    
    results = db.get_game_results(game_id)
    leaderboard = "🏆 **ТАБЛИЦА ЛИДЕРОВ** 🏆\n\n"
    sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
    
    for i, player in enumerate(sorted_results, 1):
        medal = ['🥇', '🥈', '🥉'][i-1] if i <= 3 else '🔹'
        leaderboard += f"{medal} **{i}. {player['player_name']}** — {player['score']} действий\n"
    
    if sorted_results:
        winner = sorted_results[0]
        winners = [p for p in sorted_results if p['score'] == winner['score']]
        if len(winners) > 1:
            leaderboard += f"\n🤝 **Ничья!** Победили: {', '.join([w['player_name'] for w in winners])}"
        else:
            leaderboard += f"\n🎉 **Победитель: {winner['player_name']}!**"
    
    db.finish_game(game_id)
    bot.send_message(chat_id, leaderboard, parse_mode='Markdown')
    state.step = 'IDLE'
    state.game_data = {}
    bot.send_message(chat_id, "Спасибо за игру! /newgame — чтобы начать заново.")

def next_turn(chat_id, state):
    players = state.game_data['players']
    turn_index = state.game_data.get('current_turn', 0)
    next_index = (turn_index + 1) % len(players)
    state.game_data['current_turn'] = next_index
    game_id = state.game_data.get('game_id')
    db.update_game_turn(game_id, next_index)
    db.clear_current_task(game_id)
    next_player = players[next_index]
    bot.send_message(chat_id, f"🔁 Ход игрока: **{next_player}**", parse_mode='Markdown')
    send_task_with_buttons(chat_id, state, use_saved=False)

# ================= АДМИН-КОМАНДЫ =================
@bot.message_handler(commands=['admin'])
def admin_menu(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    print(f"🔧 [{time.strftime('%H:%M:%S')}] /admin от user_id={user_id}")
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, f"🚫 Доступ запрещён\nВаш ID: `{user_id}`", parse_mode='Markdown')
        return
    
    try:
        text = "🔧 **Панель администратора**\n\nВыберите действие:"
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton("📋 Непроверенные карточки", callback_data="admin_unverified"),
            types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
            types.InlineKeyboardButton("🔙 Выход", callback_data="admin_exit")
        )
        sent_message = bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown', reply_markup=keyboard)
        print(f"✅ Сообщение отправлено! message_id={sent_message.message_id}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        bot.reply_to(message, f"❌ Ошибка:\n`{str(e)}`", parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == 'admin_unverified')
def admin_show_unverified(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён", show_alert=True)
        return
    try:
        cards = db.get_unverified_cards()
        if not cards:
            bot.answer_callback_query(call.id, "✅ Все карточки проверены!", show_alert=True)
            return
        card = cards[0]
        type_emoji = "❓" if card['type'] == 'truth' else "🎯"
        diff_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴", "hardcore": "🟣"}.get(card['difficulty'], "⚪")
        text = f"{type_emoji} **Карточка # {card['id']}**\n\n{diff_emoji} **Сложность:** {card['difficulty']}\n📝 **Тип:** {card['type']}\n🏷 **Теги:** {card['tags'] or 'нет'}\n\n📄 **Текст:**\n_{card['text']}_\n\nПроверьте и подтвердите или отклоните."
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("✅ Верифицировать", callback_data=f"verify_yes_{card['id']}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"verify_no_{card['id']}")
        )
        bot.send_message(call.message.chat.id, text, parse_mode='Markdown', reply_markup=keyboard)
        bot.answer_callback_query(call.id)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {e}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('verify_'))
def admin_verify_card(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён", show_alert=True)
        return
    try:
        parts = call.data.split('_')
        action = parts[1]
        card_id = int(parts[2])
        if action == 'yes':
            db.verify_card(card_id, 1)
            bot.answer_callback_query(call.id, "✅ Карточка подтверждена!", show_alert=True)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        elif action == 'no':
            db.verify_card(card_id, 0)
            bot.answer_callback_query(call.id, "❌ Карточка отклонена!", show_alert=True)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        admin_show_unverified(call)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {e}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == 'admin_stats')
def admin_show_stats(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён", show_alert=True)
        return
    text = f"📊 **Статистика бота**\n\n👥 Админов: {len(ADMIN_IDS)}"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, text, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == 'admin_exit')
def admin_exit(call):
    if call.from_user.id not in ADMIN_IDS:
        return
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "🔙 Выход из меню")

@bot.message_handler(commands=['unverified'])
def cmd_unverified(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 Доступ запрещён")
        return
    cards = db.get_unverified_cards()
    if not cards:
        bot.reply_to(message, "✅ Все карточки проверены!")
        return
    text = f"📋 **Непроверенные карточки:** {len(cards)} шт.\n\n"
    for card in cards[:5]:
        text += f"#{card['id']} [{card['difficulty']}] {card['type']}: {card['text'][:50]}...\n"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['verify'])
def cmd_verify(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 Доступ запрещён")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Использование: /verify <id> [1/0]")
        return
    try:
        card_id = int(args[1])
        is_verified = int(args[2]) if len(args) > 2 else 1
        db.verify_card(card_id, is_verified)
        bot.reply_to(message, f"✅ Карточка #{card_id} верифицирована: {is_verified}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 Доступ запрещён")
        return
    bot.reply_to(message, "📊 Статистика бота (в разработке)")

# ================= ЗАПУСК =================
if __name__ == '__main__':
    print("🚀 Бот 'Правда или Действие' запущен...")
    print(f"👑 Админы: {ADMIN_IDS}")
    print(f"🤖 Токен загружен: {'✅' if TOKEN else '❌'}")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)