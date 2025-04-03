from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

messages = {
    "buy": lambda: "Bought!",
    "sell": lambda: "Sold!",
    "register": lambda: "Registerd!",
    None: lambda: "",
}

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user = {}
    user_id = session["user_id"]
    cd = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    print(cd)
    user['cash'] = cd[0]['cash']
    pd = db.execute("SELECT symbol,name,count,price FROM portfolio JOIN shares ON share_id=shares.id WHERE user_id = ?", user_id)
    print(pd)
    user['shares'] = pd
    # calculate total 
    user["total"] = sum([i["price"]*i["count"] for i in pd]) + user["cash"]
    if "msg" not in session:
        session["msg"] = None
    flash = messages[session["msg"]]
    return render_template("index.html", user = user, usd = usd, get_flashed_messages=flash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    session["msg"] = None
    if request.method == "POST":
        symbol = request.form.get("symbol")
        count =  int(request.form.get("shares"))
        if len(symbol)==0:
            return apology("Symbol required!!", 403)
        
        user_id = session["user_id"]
        result = {}
        price: float 
        
        users = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        print(users)
        
        # 1 check if it is in shares table, the share which user is buying
        shares = db.execute("SELECT * FROM shares WHERE symbol = ?", symbol)
        print(shares)
        if len(shares)==0:
            # share with symbol not found in db, hence calling API
            result = lookup(symbol)
            print(result)
            if result is None:
                return apology("Symbol doesn't exist!", 403)
            price = result['price']
            share_id = db.execute("INSERT INTO shares(name, symbol, price) values(?, ?, ?)",
                       result["name"], symbol, price)
            
            if users[0]['cash'] < price:
                return apology("Insufficient balance!!", 403)
            # inserted the record for the share
        else:
            share_id = shares[0]["id"]
            price = shares[0]["price"]
        # got share id    
        
        # 2 insert into transactions table 
        t = db.execute("INSERT INTO transactions(user_id, share_id, count, type, transaction_date) values(?, ?, ?,?,?)",
                       user_id, share_id, count, "BUY", datetime.now())
        print("Insert into transaction: ",t)
        
        # 3 increment count in portfolio
        # so first get the current count of stock if present
        stocks = db.execute("SELECT * FROM portfolio where user_id = ? and share_id = ?", user_id, share_id)
        print(stocks)
        if len(stocks)==0:
            # user doesn't hold this share
            res = db.execute("INSERT INTO portfolio(user_id, share_id, count) values(?, ?, ?)",
                             user_id, share_id, count)
        else:
            # increment count for this share
            count += stocks[0]["count"]
            res = db.execute("UPDATE portfolio set count = ? where user_id = ? and share_id = ?",
                             count, user_id, share_id)
        print(res)
        cash = users[0]['cash'] - (int(request.form.get("shares"))*price)
        updated = db.execute("UPDATE users set cash = ? WHERE id = ?", cash, user_id)
        print(updated)
        session["msg"] = "buy"
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    session["msg"] = None
    user_id = session["user_id"]
    transactions = db.execute("SELECT symbol,price,count,transaction_date,type FROM transactions JOIN shares on share_id=shares.id where user_id = ?", 
                            user_id)
    return render_template("history.html", transactions = transactions)    


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    session["msg"] = None
    if request.method == "POST":
        result = lookup(request.form.get("symbol"))
        if result:
            result = [result]
        return render_template("quoted.html", items = result, usd = usd)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session["msg"] = None
    if request.method == "POST":
        password = request.form.get("password")
        username = request.form.get("username")
        confirmation = request.form.get("confirmation")
        if len(request.form.get("username")) == 0:
            return apology("Username required!", 403)
        
        if len(password) == 0:
            return apology("Password required!", 403)
        
        if len(password) < 6 or len(password) > 20:
            return apology("Password length should be between 6 and 20!", 403)
        
        if len(confirmation) == 0 or confirmation != password:
            return apology("Passwords didn't match!", 403)

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(rows) > 0:
            return apology("Username already exists", 403)
        hashed = generate_password_hash(password)
        user_id = db.execute("INSERT INTO users(username, hash) values(?, ?)",username, hashed)
        print(user_id)
        # Remember which user has logged in
        session["user_id"] = user_id
        session["msg"] = "register"
        return redirect("/")
    else:
        return render_template("registration.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    session["msg"] = None
    user_id = session["user_id"]
    
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        portfolio = db.execute("SELECT price,count,share_id FROM portfolio JOIN shares on share_id = shares.id where user_id = ? and symbol = ?",
                               user_id, symbol)
        print(portfolio)
        count = portfolio[0]["count"]
        price = portfolio[0]["price"]
        share_id = portfolio[0]["share_id"]
        
        if shares > count :
            # failure - No of selling of shares is greater than user own
            return apology("Not enough shares !!")
        cash = shares*price
        # success
        # 1 update portfolio to decrement share count
        # 2 insert into transactions for sell record for this user
        # 3 update users cash
        if shares == count:
            # delete the share from portfolio
            res = db.execute("DELETE from portfolio where user_id = ? and share_id = ?",
                            user_id, share_id)
        res = db.execute("UPDATE portfolio set count = ? where user_id = ? and share_id = ?",
                            (count-shares), user_id, share_id)
        t = db.execute("INSERT INTO transactions(user_id, share_id, count, type, transaction_date) values(?, ?, ?,?,?)",
                       user_id, share_id, shares, "SELL", datetime.now())
        print("Insert into transaction: ",t)
        res = db.execute("UPDATE users set cash = cash + ? where id = ?",
                            cash, user_id)
        session["msg"] = "sell"
        return redirect("/")
    else:        
        shares = db.execute("SELECT name,symbol FROM portfolio JOIN shares on share_id=shares.id where user_id = ?", user_id)
        return render_template("sell.html", shares=shares)

if __name__ == "__main__":
    app.run(debug=True)