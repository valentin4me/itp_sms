from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import vonage
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clients.db'
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class ClientModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    itp_date = db.Column(db.Date, nullable=False)

vonage_client = vonage.Client(key='bbff094a', secret='oIgi7QLMfk8NNlhO')
sms = vonage.Sms(vonage_client)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        flash('Login unsuccessful. Please check your username and password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    return render_template('home.html')

@app.route('/clienti')
@login_required
def clienti():
    clients = ClientModel.query.all()
    return render_template('clients.html', clients=clients)

@app.route('/statistici')
@login_required
def statistici():
    total_clients = ClientModel.query.count()
    expired_clients = ClientModel.query.filter(ClientModel.itp_date < datetime.today()).count()
    expiring_soon_clients = ClientModel.query.filter(ClientModel.itp_date.between(datetime.today(), datetime.today() + timedelta(days=7))).count()

    clients_per_month = db.session.query(db.func.strftime('%Y-%m', ClientModel.itp_date), db.func.count(ClientModel.id)).group_by(db.func.strftime('%Y-%m', ClientModel.itp_date)).all()
    months = [month for month, count in clients_per_month]
    clients_per_month_counts = [count for month, count in clients_per_month]

    return render_template('statistics.html', total_clients=total_clients, expired_clients=expired_clients, expiring_soon_clients=expiring_soon_clients, months=months, clients_per_month=clients_per_month_counts)

@app.route('/adauga_client', methods=['POST'])
@login_required
def adauga_client():
    data = request.form
    new_client = ClientModel(
        name=data['name'],
        phone=data['phone'],
        itp_date=datetime.strptime(data['itp_date'], '%Y-%m-%d')
    )
    db.session.add(new_client)
    db.session.commit()
    return redirect('/clienti')

@app.route('/editeaza_client', methods=['POST'])
@login_required
def editeaza_client():
    data = request.form
    client = ClientModel.query.get(data['id'])
    if client:
        client.name = data['name']
        client.phone = data['phone']
        client.itp_date = datetime.strptime(data['itp_date'], '%Y-%m-%d')
        db.session.commit()
    return redirect('/clienti')

@app.route('/obtine_clienti', methods=['GET'])
@login_required
def obtine_clienti():
    clients = ClientModel.query.all()
    clients_list = [{"id": client.id, "name": client.name, "phone": client.phone, "itp_date": client.itp_date.strftime('%Y-%m-%d')} for client in clients]
    return jsonify(clients_list), 200

@app.route('/sterge_client/<int:id>', methods=['POST'])
@login_required
def sterge_client(id):
    client = ClientModel.query.get(id)
    if client:
        db.session.delete(client)
        db.session.commit()
        return redirect('/clienti')
    return jsonify({"status": "Clientul nu a fost găsit"}), 404

@app.route('/test_sms', methods=['POST'])
@login_required
def test_sms():
    data = request.form
    responseData = sms.send_message({
        "from": "VonageAPI",
        "to": data['phone'],
        "text": data['message'],
    })
    if responseData["messages"][0]["status"] == "0":
        return jsonify({"status": "SMS de test trimis cu succes"}), 200
    else:
        return jsonify({"status": f"Mesajul a eșuat cu eroarea: {responseData['messages'][0]['error-text']}"}), 400

def trimite_sms_reamintire():
    with app.app_context():
        clients = ClientModel.query.all()
        for client in clients:
            if client.itp_date - timedelta(days=7) == datetime.today().date():
                responseData = sms.send_message({
                    "from": "VonageAPI",
                    "to": client.phone,
                    "text": "ITP-ul tău expiră într-o săptămână!",
                })
                if responseData["messages"][0]["status"] == "0":
                    print("Mesaj trimis cu succes.")
                else:
                    print(f"Mesajul a eșuat cu eroarea: {responseData['messages'][0]['error-text']}")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='negrustefan').first():
            hashed_password = generate_password_hash('itpsabareni', method='pbkdf2:sha256')
            new_user = User(username='negrustefan', password=hashed_password)
            db.session.add(new_user)
            db.session.commit()

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=trimite_sms_reamintire, trigger="interval", hours=24)
    scheduler.start()

    try:
        app.run(debug=True)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()