from flask import Flask, render_template, request, redirect, url_for, session, make_response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os 
import certifi
import json
from bson.objectid import ObjectId
from bson.json_util import dumps
import pymongo
import copy
import jwt
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv

load_dotenv()
import os 

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
ca = certifi.where()

MONGODB_URL = os.environ.get("MONGODB_URL")
client = pymongo.MongoClient(MONGODB_URL,tlsCAFile=ca)
db = client["accounts_info"]
app.permanent_session_lifetime = timedelta(minutes=5)

# to stop caching static file
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


@app.route('/', methods=["GET"]) 
def home():
    if not session.get("logged_in"):
        return render_template('home.html')
    else:
        
        token = request.cookies.get('token')
        try:
                payload = jwt.decode(token, app.config["SECRET_KEY"],algorithms="HS256")
        except:
                return jsonify({'Alert!' : "Invalid Token!"})
        
        print("payload: ", payload)
        user_id = payload.get("user_id")
        expiration = payload.get("expiration") # 2026-05-21 00:13:08.627460+00:00 for example
        expiration = datetime.strptime(expiration, "%Y-%m-%d %H:%M:%S.%f%z")

        print("Expiration: ", expiration)
        print(type(datetime.now(UTC)))

        if datetime.now(UTC) < expiration:
             print("Time hasn't passed yet, ", datetime.now(UTC))
             return redirect(url_for("to_do", user_id = user_id))

        else:
             return render_template("home.html")
        
@app.route('/track-click') # for signout hyperlink
def track_click():
    session["logged_in"] = False
    return redirect(url_for('home')) 

@app.route('/login', methods=["GET","POST"])
def log_in():
    if request.method == "GET":
        return render_template('login.html')
    elif request.method == "POST":
        attempted_email = request.form.get("email")
        attempted_password = request.form.get("password")
        
        if db.accounts.find_one({"email" : attempted_email}):
            dict_for_account = db.accounts.find_one({"email" : attempted_email})
            hashed_password = dict_for_account.get("password")
        else:
            return render_template('login.html')

        if check_password_hash(hashed_password,attempted_password): # sucessful login
            session["logged_in"] = True
            session.permanent = True
            user_id = dict_for_account.get("_id")
        
            resp = make_response(redirect(url_for("to_do", user_id = user_id)))
            token = jwt.encode({"email" : attempted_email, "user_id" : str(user_id), "expiration" : str(datetime.now(UTC) + timedelta(seconds=60))},app.config["SECRET_KEY"],algorithm="HS256")
            resp.set_cookie('token',token, httponly=True)
            return resp

        return render_template('login.html')

@app.route('/sign_up', methods=["GET","POST"])
def sign_up():
    if request.method == "GET":
        return render_template('sign_up.html')
    elif request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        print(f"name: {name} email: {email} password: {password}")

        hashed_password = generate_password_hash(password)

        if db.accounts.find_one({"email" : email}):
            print("cant make that")
            return render_template('sign_up.html')

        data = { 
                "name" : name,
                "email" : email,
                "password" : hashed_password,
                "to-do" : []}
        print(f"data: {data}")

        db.accounts.insert_one(data)
        dict_for_account = db.accounts.find_one({"email" : email})
        user_id = dict_for_account.get("_id")
        resp = make_response(redirect(url_for("to_do", user_id = user_id)))
        token = jwt.encode({"email" : email, "user_id" : str(user_id), "expiration" : str(datetime.now(UTC) + timedelta(seconds=60))},app.config["SECRET_KEY"],algorithm="HS256")
        resp.set_cookie('token',token, httponly=True)
        session["logged_in"] = True
        session.permanent = True
        return resp
            
      
@app.route('/to_do/<user_id>', methods=["GET","POST","DELETE"])
def to_do(user_id):
    token = request.cookies.get('token')
    print(f"TOKEN: {token}")
    if not token:
            return jsonify({"Alert!" : "Token is missing!"})
    try:
            payload = jwt.decode(token, app.config["SECRET_KEY"],algorithms="HS256")
    except:
            return jsonify({'Alert!' : "Invalid Token!"})
    
    dict_for_account = db.accounts.find_one({"_id" : ObjectId(user_id)})

    user_email = dict_for_account.get("email")
    name = dict_for_account.get("name")
    token_email = payload.get("email")
    print("USER EMAIL: ", user_email)
    print("TOKEN EMAIL: ", token_email)
    print("LOGGED IN: ", session["logged_in"])

    if user_email == token_email or not session["logged_in"] == True:
         to_do_list = dict_for_account.get("to-do")
         old_list = copy.deepcopy(to_do_list)
         important_filter = False

         if request.form.get("Filter By Important"):
            print("Filter on")
            important_filter = True
         elif request.form.get("Descelect Filter"):
            print("Filter off")
            important_filter = False

         if request.form.get("Title Create"): # create task
            new_task_title = request.form.get("Title Create")
            new_task_desc = request.form.get("Description Create")
            important = request.form.get("important") # on or None
            
            if important:
                to_do_list.append({"title" : new_task_title, "description" : new_task_desc, "important" : True})
            else:
                to_do_list.append({"title" : new_task_title, "description" : new_task_desc, "important" : False})
        
         elif request.form.get("Delete Task"): # delete task
            delete_task = request.form.get("Delete Task")
            print(f"Deleting this task gng {delete_task}")

            print("To Do list length: ", len(to_do_list))
            if len(to_do_list) > 0:
                for x in to_do_list: 
                    if x.get("title") == delete_task:
                        to_do_list.remove(x)

         elif request.form.get("Old Title") and request.form.get("New Title"):

            old_title = [td.get("title") for td in to_do_list if td.get("title") == request.form.get("Old Title")]

            if len(old_title) > 0:
                old_title = "".join(old_title[0])
                new_title = request.form.get("New Title")
                
                print("Old title: ", old_title)
                print("The entire list: ", to_do_list)

                correct_td_list = [x for x in to_do_list if old_title == x.get("title")]
                print("td list 1: ", correct_td_list)

                for x in correct_td_list:
                    correct_td_list = x
                
                to_do_list.remove(correct_td_list)

                correct_td_list["title"] = new_title
                to_do_list.append(correct_td_list)
               
         elif request.form.get("Old Title") and request.form.get("New Description"):

            old_title = [td.get("title") for td in to_do_list if td.get("title") == request.form.get("Old Title")]

            if len(old_title) > 0:
                old_title = "".join(old_title[0])
                new_des = request.form.get("New Description")
                
                correct_td_list = [x for x in to_do_list if old_title == x.get("title")]
                for x in correct_td_list:
                    correct_td_list = x

                correct_td_list["description"] = new_des
                
         elif request.form.get("Old Description") and request.form.get("New Description"):

            old_des = [td.get("description") for td in to_do_list if td.get("description") == request.form.get("Old Description")]

            if len(old_des) > 0:
                old_des = "".join(old_des[0])
                new_des = request.form.get("New Description")
                
                correct_td_list = [x for x in to_do_list if old_des == x.get("description")]

                for x in correct_td_list:
                    correct_td_list = x 
                correct_td_list["description"] = new_des

         elif request.form.get("Old Description") and request.form.get("New Title"):

            old_des = [td.get("description") for td in to_do_list if td.get("description") == request.form.get("Old Description")]
            if len(old_des) > 0:
                old_des = "".join(old_des[0])
                print(old_des)
                new_title = request.form.get("New Title")
                
                correct_td_list = [x for x in to_do_list if old_des == x.get("description")]
                for x in correct_td_list:
                    correct_td_list = x 
                correct_td_list["title"] = new_title

         try:
            if request.form.get("important"):
                correct_td_list["important"] = True     
            else:
                correct_td_list["important"] = False
         except:
             print("skip it")

         myquery = { "to-do": old_list }
         newvalues = { "$set": { "to-do": to_do_list } }
         db.accounts.update_one(myquery,newvalues)
        
         return render_template('to_do.html', name = name, td = to_do_list, important_filter = important_filter)
    else:
        return jsonify({'Alert!' : "Access Denied!"})

if __name__ == '__main__':
    # for deployment
    # to make it work for both production and development
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)