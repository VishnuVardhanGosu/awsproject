from flask import Flask, render_template, request, redirect, url_for, flash, session
import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Initialize DynamoDB
region_name = "ap-south-1"
dynamodb = boto3.resource('dynamodb', region_name=region_name)
users_table = dynamodb.Table('Users')
accounts_table = dynamodb.Table('Accounts')
statements_table = dynamodb.Table('AccountStatements')

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=['POST', 'GET'])
def register():
    if request.method == 'POST':
        user_id = str(uuid.uuid4())
        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        address = request.form['address']
        aadhar_number = request.form['aadhar_number']
        pan_card = request.form['pan_card']

        # Check if user already exists
        existing = users_table.scan(FilterExpression=Attr('email').eq(email))
        if existing['Items']:
            flash("Email already exists! Please log in.")
            return redirect(url_for('login', email=email))

        if len(phone) != 10 or len(aadhar_number) != 12:
            flash("Invalid phone or Aadhar number")
            return render_template("register.html")

        users_table.put_item(Item={
            'user_id': user_id,
            'email': email,
            'password': password,
            'full_name': full_name,
            'phone': phone,
            'address': address,
            'aadhar_number': aadhar_number,
            'pan_card': pan_card
        })

        session['user'] = {'user_id': user_id, 'email': email, 'full_name': full_name}
        flash("Registration successful! Please log in.")
        return redirect(url_for('confirm'))

    return render_template("register.html")

@app.route("/confirm")
def confirm():
    user = session.get('user')
    if user:
        return render_template("confirm.html", user=user)
    return redirect(url_for('login'))

@app.route("/login", methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        users = users_table.scan(FilterExpression=Attr('email').eq(email) & Attr('password').eq(password))
        user = users['Items'][0] if users['Items'] else None

        if user:
            session['user'] = {'user_id': user['user_id'], 'email': user['email'], 'full_name': user['full_name']}
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid login credentials!")
            return redirect(url_for('login'))

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    user = session.get('user')
    return render_template("dashboard.html", user=user) if user else redirect(url_for('login'))

@app.route("/deposit", methods=['POST', 'GET'])
def deposit():
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        amount = float(request.form['deposit_amount'])
        account_type = request.form['account_type']

        account = accounts_table.get_item(Key={'user_id': user['user_id']}).get('Item')
        if not account:
            accounts_table.put_item(Item={'user_id': user['user_id'], 'account_type': account_type, 'balance': amount})
        else:
            new_balance = account['balance'] + amount
            accounts_table.update_item(
                Key={'user_id': user['user_id']},
                UpdateExpression='SET balance = :val',
                ExpressionAttributeValues={':val': new_balance}
            )

        statements_table.put_item(Item={
            'user_id': user['user_id'],
            'timestamp': datetime.utcnow().isoformat(),
            'transaction_type': 'Credit',
            'transaction_amount': amount,
            'description': 'Deposit'
        })

        flash("Funds deposited successfully!")
        return redirect(url_for('dashboard'))

    return render_template("deposit.html")

@app.route("/balance")
def check_balance():
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    account = accounts_table.get_item(Key={'user_id': user['user_id']}).get('Item')
    balance = account['balance'] if account else 0
    return render_template("balance.html", balance=balance)

@app.route("/transfer", methods=['POST', 'GET'])
def transfer():
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        recipient_id = request.form.get('user_id')
        try:
            amount = float(request.form.get('amount'))
        except ValueError:
            flash("Invalid transfer amount!")
            return redirect(url_for('transfer'))

        recipient = users_table.get_item(Key={'user_id': recipient_id}).get('Item')
        if not recipient:
            flash("Recipient not found!")
            return redirect(url_for('transfer'))

        sender_account = accounts_table.get_item(Key={'user_id': user['user_id']}).get('Item')
        recipient_account = accounts_table.get_item(Key={'user_id': recipient_id}).get('Item')

        if not sender_account or sender_account['balance'] < amount:
            flash("Insufficient balance!")
            return redirect(url_for('transfer'))

        accounts_table.update_item(
            Key={'user_id': user['user_id']},
            UpdateExpression='SET balance = balance - :val',
            ExpressionAttributeValues={':val': amount}
        )

        if recipient_account:
            accounts_table.update_item(
                Key={'user_id': recipient_id},
                UpdateExpression='SET balance = balance + :val',
                ExpressionAttributeValues={':val': amount}
            )
        else:
            accounts_table.put_item(Item={'user_id': recipient_id, 'account_type': 'savings', 'balance': amount})

        now = datetime.utcnow().isoformat()
        statements_table.put_item(Item={
            'user_id': user['user_id'],
            'timestamp': now,
            'transaction_type': 'Debit',
            'transaction_amount': amount,
            'description': f'Transfer to {recipient_id}'
        })
        statements_table.put_item(Item={
            'user_id': recipient_id,
            'timestamp': now,
            'transaction_type': 'Credit',
            'transaction_amount': amount,
            'description': f'Transfer from {user["user_id"]}'
        })

        flash("Funds transferred successfully!")
        return redirect(url_for('dashboard'))

    return render_template("transfer.html")

@app.route("/statement")
def statements():
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    response = statements_table.query(
        KeyConditionExpression=Key('user_id').eq(user['user_id']),
        ScanIndexForward=False
    )
    return render_template("statement.html", transactions=response['Items'])

@app.route("/customer-support")
def customer_support():
    return render_template("customer_support.html")

@app.route("/services")
def services():
    return render_template("services.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False)
