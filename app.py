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
            return f"The connection is successful: {collections}"
    except Exception as e:
     return f"connection problem: {str(e)}"


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
                
    return redirect(url_for("users_list"))
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
        user_games = []
        
        for game in games:
            user_comments = [comment for comment in user.get("comments", []) if comment["game"] == game["name"]]
            
            user_play_time = sum(comment.get("play_time", 0) for comment in user_comments) if user_comments else 0
            
            if user_play_time > 0:
                game_copy = game.copy()
                game_copy["user_play_time"] = user_play_time
                
              
                user_rating = next((comment.get("rating", None) for comment in user_comments if "rating" in comment), None)
                game_copy["user_rating"] = user_rating
                
                user_games.append(game_copy)
            
            game["user_play_time"] = user_play_time
    
    return render_template("user_page.html", user=user, games=games, user_games=user_games)
@app.route("/play_game", methods=["POST"])
def play_game():
    if "user_id" not in session:
        return redirect(url_for("home"))
    
    game_id = request.form.get("game_id")
    play_time = int(request.form.get("play_time", 0))
    
    try:
        with get_db_connection() as db:
            user = db.users.find_one({"_id": ObjectId(session["user_id"])})
            game = db.games.find_one({"_id": ObjectId(game_id)})
            
            if not user or not game:
                flash("User or Game not found", "error")
                return redirect(url_for("user_page"))
            
      
            db.games.update_one(
                {"_id": ObjectId(game_id)},
                {"$inc": {"play_time": play_time}}
            )
            
         
            db.users.update_one(
                {"_id": ObjectId(session["user_id"])},
                {"$inc": {"total_play_time": play_time}}
            )
            
        
            user_comment = None
            for comment in user.get("comments", []):
                if comment.get("game") == game["name"]:
                    user_comment = comment
                    break
                    
            if user_comment:
                db.users.update_one(
                    {"_id": ObjectId(session["user_id"]), "comments.game": game["name"]},
                    {"$inc": {"comments.$.play_time": play_time}}
                )
            else:
                new_comment = {"game": game["name"], "text": "", "play_time": play_time}
                db.users.update_one(
                    {"_id": ObjectId(session["user_id"])},
                    {"$push": {"comments": new_comment}}
                )
            
            updated_user = db.users.find_one({"_id": ObjectId(session["user_id"])})
            
         
            print(f"Game played: {game['name']}, Play time: {play_time}")
            print(f"User comments after update: {updated_user.get('comments', [])}")
            
            update_most_played_game(session["user_id"])
            flash(f"You played {game['name']} for {play_time} hours", "success")
            return redirect(url_for("user_page"))
    except Exception as e:
        print(f"Hata oluştu: {str(e)}")
        flash(f"Bir hata oluştu: {str(e)}", "error")
        return redirect(url_for("user_page"))
@app.route("/rate_game", methods=["POST"])
def rating_game():
    if "user_id" not in session:
        return redirect(url_for("home"))
    game_id=request.form.get("game_id")
    rating=int(request.form.get("rating",0)) 
    with get_db_connection() as db:
        user=db.users.find_one({"_id":ObjectId(session["user_id"])})
        game=db.games.find_one({"_id":ObjectId(game_id)})
        if not user or not game:
            flash("User or Game not found", "error")
            return redirect(url_for("user_page"))
        user_comment=None
        for comment in user.get("comments",[]):
            if comment.get("game")==game["name"]:
                user_comment=comment
                break
        if not user_comment or user_comment.get("play_time",0)<1:
            flash("You need to play the game for at least 1 hour before rating it.", "error")
            return redirect(url_for("user_page"))
        db.users.update_one({"_id":ObjectId(session["user_id"]),"comments.game":game["name"]},{"$set":{"comments.$.rating":rating}})
        update_user_average_rating(session["user_id"])
        update_game_rating(game["_id"])
        flash(f"{game['name']} oyununa {rating}/5 puan verdiniz.", "success")
        return redirect(url_for("user_page"))
@app.route("/comment_game", methods=["POST"])
def comment_game():
    if "user_id" not in session:
        return redirect(url_for("home"))
    game_id=request.form.get("game_id")
    comment_text=request.form.get("comment_text","").strip()
    with get_db_connection() as db:
        user=db.users.find_one({"_id":ObjectId(session["user_id"])})
        game=db.games.find_one({"_id":ObjectId(game_id)})
        if not user or not game:
            flash("User or Game not found", "error")
            return redirect(url_for("user_page"))
        user_comment=None
        for comment in user.get("comments",[]):
            if comment.get("game")==game["name"]:
                user_comment=comment
                break
        if not user_comment or user_comment.get("play_time",0)<1:
            flash("You need to play the game for at least 1 hour before commenting on it.", "error")
            return redirect(url_for("user_page"))
        db.users.update_one({"_id":ObjectId(session["user_id"]),"comments.game":game["name"]},{"$set":{"comments.$.text":comment_text}})
        exists_comment=False
        for comment in game.get("all_comments",[]):
            if comment.get("user")==user["name"]:
                exists_comment=True
                db.games.update_one(
                    {"_id": ObjectId(game_id), "all_comments.user": user["name"]},
                    {"$set": {
                        "all_comments.$.text": comment_text,
                        "all_comments.$.play_time": user_comment["play_time"]
                    }}
                )
                break
        if not exists_comment:
            db.games.update_one({
                "_id": ObjectId(game_id)},{"$push":{"all_comments":{"user":user["name"],"text":comment_text,"play_time":user_comment["play_time"]}}})
            flash(f"You commented on {game['name']}.", "success")
        return redirect(url_for("user_page"))
def update_most_played_game(user_id):
    try:
        with get_db_connection() as db:
            user = db.users.find_one({"_id": ObjectId(user_id)})
            
            if not user or not user.get("comments"):
                print("User or comments not found for most played game update")
                return
            
            print(f"User comments for most played update: {user.get('comments', [])}")
            
            if len(user["comments"]) > 0:
                most_commented_game = max(user["comments"], key=lambda x: x.get("play_time", 0))
                most_played_game = most_commented_game.get("game")
                
                print(f"Most played game determined as: {most_played_game}")
                
                db.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": {"most_played": most_played_game}}
                )
    except Exception as e:
        print(f"Most played game update error: {str(e)}")
def update_user_average_rating(user_id):
    with get_db_connection() as db:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            return
        
        rated_comments = [comment for comment in user.get("comments", []) if "rating" in comment]
        
        if not rated_comments:
            avg_rating = 0
        else:
            avg_rating = sum(comment["rating"] for comment in rated_comments) / len(rated_comments)
        
     
        db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"avarage_of_rating": round(avg_rating, 1)}}
        )

def update_game_rating(game_id):
    with get_db_connection() as db:
        game = db.games.find_one({"_id": ObjectId(game_id)})
        users = list(db.users.find())
        
        total_weighted_rating = 0
        total_play_time = 0
        
        for user in users:
            for comment in user.get("comments", []):
                if comment.get("game") == game["name"] and "rating" in comment:
                    play_time = comment.get("play_time", 0)
                    rating = comment["rating"]
                    
                    total_weighted_rating += play_time * rating
                    total_play_time += play_time
        
        if total_play_time > 0:
            weighted_rating = total_weighted_rating / total_play_time
        else:
            weighted_rating = 0
        
      
        db.games.update_one(
            {"_id": ObjectId(game_id)},
            {"$set": {"rating": round(weighted_rating, 1)}}
        )
@app.route("/debug_user")
def debug_user():
    if "user_id" not in session:
        return "Kullanıcı girişi yapılmamış"
    
    user_id = session["user_id"]
    
    with get_db_connection() as db:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            return "Kullanıcı bulunamadı"
        
        comments = user.get("comments", [])
        
        result = {
            "user_name": user["name"],
            "total_play_time": user["total_play_time"],
            "comments": comments
        }
        
        return str(result)
@app.route('/users')
def users_list():
    with get_db_connection() as db:
        users = list(db.users.find())
    return render_template("users.html", users=users)
        
            
        
           
            

        
    
    
    
        
        
        

               

        
                 
    
    

    
            
   

# Flask uygulamasını başlat
if __name__ == "__main__":
    app.run(debug=True)