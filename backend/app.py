from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
import os
from dotenv import load_dotenv
import random
import json
import string

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 使用字典來存儲房間信息
rooms = {}

# 載入卡牌數據
with open('./static/images/cards/cards.json', 'r', encoding='utf-8') as f:
    all_cards = json.load(f)

def generate_room_code():
    """生成一個唯一的6位房間代碼"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in rooms:
            return code

@app.route('/create_room', methods=['POST'])
def create_room():
    room_code = generate_room_code()
    rooms[room_code] = {
        'players': [],
        'game_started': False,
        'common_cards': [],
        'player_cards': {},
        'current_turn': None,
        'guesses_left': {}
    }
    return jsonify({"message": "Room created", "room_code": room_code}), 200

@app.route('/join_room', methods=['POST'])
def join_room():
    data = request.get_json()
    room_code = data.get('room_code')
    player_name = data.get('player_name')

    if not room_code or not player_name:
        return jsonify({"error": "Room code and player name are required"}), 400

    if room_code not in rooms:
        return jsonify({"error": "Room not found"}), 404

    room = rooms[room_code]
    
    if len(room['players']) >= 2:
        return jsonify({"error": "Room is full"}), 400

    if room['game_started']:
        return jsonify({"error": "Game has already started"}), 400

    room['players'].append(player_name)
    room['guesses_left'][player_name] = 3
    
    socketio.emit('player_joined', {"player": player_name, "players": room['players']}, room=room_code)
    
    return jsonify({"message": f"Joined room: {room_code}", "players": room['players']}), 200

@app.route('/start_game', methods=['POST'])
def start_game():
    data = request.get_json()
    room_code = data.get('room_code')

    if room_code not in rooms:
        return jsonify({"error": "Room not found"}), 404

    room = rooms[room_code]

    if len(room['players']) != 2:
        return jsonify({"error": "Need exactly 2 players to start the game"}), 400

    if room['game_started']:
        return jsonify({"error": "Game has already started"}), 400

    # 選擇25張卡牌作為共同牌庫
    room['common_cards'] = random.sample(all_cards, 25)

    # 為每個玩家分配一張秘密角色卡
    for player in room['players']:
        room['player_cards'][player] = random.choice(room['common_cards'])

    room['game_started'] = True
    room['current_turn'] = room['players'][0]  # 第一個玩家先開始

    socketio.emit('game_started', {
        "common_cards": [card['id'] for card in room['common_cards']],
        "current_turn": room['current_turn']
    }, room=room_code)

    return jsonify({"message": "Game started"}), 200

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    socketio.emit('player_joined', {"player": data['player'], "players": rooms[room]['players']}, room=room)

@socketio.on('ask_question')
def handle_question(data):
    room_code = data['room_code']
    player = data['player']
    question = data['question']

    room = rooms[room_code]

    if player != room['current_turn']:
        return {"error": "Not your turn"}

    # 在這裡，我們只是將問題廣播給房間中的所有玩家
    # 實際的回答和卡牌過濾將由玩家在前端完成
    socketio.emit('new_question', {
        "player": player,
        "question": question
    }, room=room_code)

    # 切換到下一個玩家的回合
    room['current_turn'] = [p for p in room['players'] if p != player][0]
    socketio.emit('turn_change', {"current_turn": room['current_turn']}, room=room_code)

@socketio.on('make_guess')
def handle_guess(data):
    room_code = data['room_code']
    player = data['player']
    guessed_card = data['guessed_card']

    room = rooms[room_code]

    if player != room['current_turn']:
        return {"error": "Not your turn"}

    if room['guesses_left'][player] <= 0:
        return {"error": "No guesses left"}

    room['guesses_left'][player] -= 1

    opponent = [p for p in room['players'] if p != player][0]
    correct_card = room['player_cards'][opponent]

    if guessed_card == correct_card['id']:
        # 玩家猜對了
        socketio.emit('game_over', {
            "winner": player,
            "correct_card": correct_card
        }, room=room_code)
    else:
        # 玩家猜錯了
        socketio.emit('guess_result', {
            "player": player,
            "guessed_card": guessed_card,
            "correct": False,
            "guesses_left": room['guesses_left'][player]
        }, room=room_code)

        if room['guesses_left'][player] == 0:
            # 如果玩家用完了所有猜測機會
            socketio.emit('game_over', {
                "winner": opponent,
                "correct_card": correct_card
            }, room=room_code)
        else:
            # 切換到下一個玩家的回合
            room['current_turn'] = opponent
            socketio.emit('turn_change', {"current_turn": room['current_turn']}, room=room_code)

@app.route('/card_image/<int:card_id>')
def card_image(card_id):
    return send_from_directory('static/images/cards', f'{card_id:02d}.png')

@app.route('/card_back')
def card_back():
    return send_from_directory('static/images/cards', 'card_back.png')

if __name__ == '__main__':
    socketio.run(app, debug=True, port=int(os.getenv('PORT', 5000)))