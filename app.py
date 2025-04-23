from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv

import os
from datetime import datetime
import contextlib

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
@app.route('/test-connection')
def test_connection():
    try:
        with get_db_connection() as db:
            collections = db.list_collection_names()
            return f"Bağlantı başarılı! Koleksiyonlar: {collections}"
    except Exception as e:
     return f"Bağlantı hatası: {str(e)}"  


@contextlib.contextmanager
def get_db_connection():
    client = MongoClient(os.getenv("MONGO_URI"))
    try:
        yield client.gamedb
    finally:
        client.close()

@app.route('/')
def home():
    with get_db_connection() as db:
        games = list(db.games.find())
        users = list(db.users.find())
    return render_template("home.html", games=games, users=users)

@app.route("/add_game", methods=["POST"])
def add_game():
    if request.method == "POST":
        name = request.form.get("gameName")
        genres = [genre.strip() for genre in request.form.get("gameGenre").split(",")]

        photo = request.form.get("gamePhoto")
        optional1 = request.form.get("gameOptional1")
        optional2 = request.form.get("gameOptional2")
        game = {
            "name": name,
            "genres": genres,  
            "photo": photo,
            "play_time": 0,
            "all_comments": [], 
            "rating": 0,
            "rating_enable": True,  
            "optional_attributes": {"release_date": optional1, "developer": optional2}
        }
        
        with get_db_connection() as db:
            db.games.insert_one(game)
        
        return redirect(url_for("home"))
@app.route("/remove_game", methods=["POST"])
def remove_game():
    game_id = request.form.get("game_id")
    with get_db_connection() as db: # Veritabanı bağlantısını açar bu
        game = db.games.find_one({"_id": ObjectId(game_id)})
        if game:
            db.games.delete_one({"_id": ObjectId(game_id)})
            
            db.users.update_many(
                {"most_played": game["name"]},
                {"$set": {"most_played": None}} 
            )
            flash(f"'{game['name']}' oyunu başarıyla silindi.", "success") 
        else:
            flash("Oyun bulunamadı.", "error")

    return redirect(url_for("home")) 

@app.route("/toggle_rating", methods=["POST"])
def toggle_rating():
    game_id = request.form.get("game_id")
    action = request.form.get("action")
    
    with get_db_connection() as db:
        if action == "enable":
            db.games.update_one(
                {"_id": ObjectId(game_id)},
                {"$set": {"rating_enable": True}}
            )
            flash("Oyun puanlamasi etkinleştirildi.", "success")
        else:
            db.games.update_one(
                {"_id": ObjectId(game_id)},
                {"$set": {"rating_enable": False}}
            )
            flash("Oyun puanlamasi devre dişi birakildi.", "success")
    
    return redirect(url_for("home"))
@app.route("/add_user", methods=["POST"])
def add_user():
    name = request.form.get("userName")
    with get_db_connection() as db:
        user = {
            "name": name,
            "total_play_time": 0,  
            "most_played": None,
            "avarage_of_rating": 0,
            "comments": []
        }
        db.users.insert_one(user)
    return redirect(url_for("home"))
@app.route("/remove_user", methods=["POST"])
def remove_user():
    user_id=request.form.get("user_id")
    with get_db_connection() as db:
        user=db.users.find_one({"_id":ObjectId(user_id)})
        if user:
            for comment in user.get("comments",[]):
                db.games.update_one({"name":comment["game"]},{"$pull":{"all_comment":{"user":user["name"]}}})#bu pull ile tüm oyun yorumlarını kişinin sildik.
            db.users.delete_one({"_id":ObjectId(user_id)})
                
    return redirect(url_for("home"))
@app.route("/login_as_user", methods=["POST"])
def login_as_user():
    user_id=request.form.get("user_id")
    session["user_id"]=str(user_id)
    return redirect(url_for("user_page"))
@app.route("/user_page")
def user_page():
    if "user_id" not in session:
        return redirect(url_for("home"))
    
    user_id = session["user_id"]
    
    with get_db_connection() as db:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            session.pop("user_id", None)
            return redirect(url_for("home"))
        
        
        games = list(db.games.find())
        
       
        for game in games:
            
            user_comments = [comment for comment in user.get("comments", []) if comment["game"] == game["name"]]
            
       
            user_play_time = sum(comment.get("play_time", 0) for comment in user_comments) if user_comments else 0
            
            game["user_play_time"] = user_play_time
    

    return render_template("user_page.html", user=user, games=games)
    

    
            
   

# Flask uygulamasını başlat
if __name__ == "__main__":
    app.run(debug=True)