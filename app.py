from flask import Flask, request, jsonify, render_template
app = Flask(__name__)

CHAT_ROOMS_DATA = {'123dasdq34radc': "First Room",
                   'das3dasdasdas': "Second Room",
                   "dasd3rfsdcfs3aczzzzz": 'Third Room'
                   }


# A welcome message to test our server
@app.route('/')
def index():
    return render_template('home.html', chat_rooms=CHAT_ROOMS_DATA)


@app.route('/chatroom/<chat_id>')
def chatroom(chat_id):
    print("Chatroom called")
    return render_template("chatroom.html", room_data={'id': chat_id, 'name': CHAT_ROOMS_DATA[chat_id]})

@app.route('/message')
def add_message():
    pass

@app.route('/update_conversation')
def add_message():
    pass

if __name__ == '__main__':
    # Threaded option to enable multiple instances for multiple user access support
    app.run(threaded=True, port=5000)
