from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import os
import base64
import logging
from datetime import datetime
import contextlib
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'saolsaol')

TEMP_UPLOAD_FOLDER = '/tmp'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def file_to_base64(file):
    try:
        file_content = file.read()
        encoded_content = base64.b64encode(file_content)
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        mime_type = f"image/{file_extension}"
        if file_extension == 'jpg':
            mime_type = "image/jpeg"
        base64_string = f"data:{mime_type};base64,{encoded_content.decode('utf-8')}"
        return base64_string
    except Exception as e:
        logger.error(f"Error converting file to base64: {str(e)}")
        return None

@app.route('/test')
def test():
    return f"App is running! Time: {datetime.now()}"

@app.route('/test-connection')
def test_connection():
    try:
        with get_db_connection() as db:
            if db is None:
                return "Database connection failed."
            collections = db.list_collection_names()
            return f"The connection is successful: {collections}"
    except Exception as e:
        logger.error(f"Test connection error: {str(e)}")
        return f"Connection problem: {str(e)}"

@contextlib.contextmanager
def get_db_connection():
    client = None
    try:
        mongo_uri = os.getenv("MONGO_URI")
        logger.info(f"Attempting to connect to MongoDB...")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        logger.info("MongoDB connection established successfully.")
        yield client.gamedb
    except Exception as e:
        logger.error(f"MongoDB connection error: {str(e)}")
        yield None
    finally:
        if client:
            client.close()
            logger.info("MongoDB connection closed.")

@app.route('/')
def index():
    return redirect(url_for('home'))

@app.route('/home')
def home():
    try:
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return render_template("home.html", games=[], users=[])
            
            games = list(db.games.find())
            users = list(db.users.find())
            
            return render_template("home.html", games=games, users=users)
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return render_template("home.html", games=[], users=[])

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(STATIC_FOLDER, path)

@app.route("/users")
def users():
    try:
        session.pop("user_id", None)
        session.pop("user_name", None)
        session.pop("avatar", None)

        flash("Please select a user to login first.", "warning")
        return redirect(url_for("home"))
    except Exception as e:
        logger.error(f"Error in users route: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("home"))

@app.route("/games")
def games():
    try:
        search = request.args.get('search', '')
        genre_filter = request.args.get('genre', '')
        sort_by = request.args.get('sort', 'rating')
        
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return render_template("games.html", games=[], all_genres=[])
            
            query = {}
            
            if search:
                query['name'] = {'$regex': search, '$options': 'i'}  
                
            if genre_filter:
                query['genres'] = genre_filter
            
            games_cursor = db.games.find(query)
            
            if sort_by == 'rating':
                games = list(games_cursor.sort('rating', -1))  
            elif sort_by == 'play_time':
                games = list(games_cursor.sort('play_time', -1))
            elif sort_by == 'name':
                games = list(games_cursor.sort('name', 1)) 
            elif sort_by == 'comments':
                games = list(games_cursor)
                games.sort(key=lambda x: len(x.get('all_comments', [])) if x.get('all_comments') else 0, reverse=True)
            else:
                games = list(games_cursor)
            
            for game in games:
                if "all_comments" in game and isinstance(game["all_comments"], list):
                    game["all_comments"] = sorted(
                        game["all_comments"],
                        key=lambda comment: comment.get("play_time", 0),
                        reverse=True
                    )
            
            all_genres = set()
            for game in db.games.find({}, {'genres': 1}):
                for genre in game.get('genres', []):
                    all_genres.add(genre)
            
            if 'user_id' in session:
                user = db.users.find_one({"_id": ObjectId(session["user_id"])})
                if user:
                    for game in games:
                        user_comments = [comment for comment in user.get('comments', []) if comment.get('game') == game['name']]
                        if user_comments:
                            game['user_play_time'] = user_comments[0].get('play_time', 0)
                            game['user_rating'] = user_comments[0].get('rating')
                            game['user_comment'] = user_comments[0].get('text', '')
                        else:
                            game['user_play_time'] = 0
                            game['user_rating'] = None
                            game['user_comment'] = ''
        
        return render_template('games.html', games=games, all_genres=sorted(all_genres))
    except Exception as e:
        logger.error(f"Error in games route: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return render_template("games.html", games=[], all_genres=[])

@app.route("/add_game", methods=["POST"])
def add_game():
    if request.method == "POST":
        try:
            name = request.form.get("gameName")
            genres = [genre.strip() for genre in request.form.get("gameGenre").split(",")]
            optional1 = request.form.get("gameOptional1")
            optional2 = request.form.get("gameOptional2")
            
            photo_data = ""
            if 'gamePhoto' in request.files:
                file = request.files['gamePhoto']
                if file and file.filename != '' and allowed_file(file.filename):
                    # Dosyayı Base64 formatında kodla
                    photo_data = file_to_base64(file)
                    
                    if not photo_data:
                        flash("Error processing the image. Please try again.", "error")
                        return redirect(url_for("home"))
                else:
                    flash("Invalid image file. Please upload a valid image (PNG, JPG, JPEG, GIF).", "error")
                    return redirect(url_for("home"))
            else:
                flash("Game image is required.", "error")
                return redirect(url_for("home"))
                
            game = {
                "name": name,
                "genres": genres,  
                "photo": photo_data,
                "play_time": 0,
                "all_comments": [], 
                "rating": 0,
                "rating_enable": True,  
                "optional_attributes": {"release_date": optional1, "developer": optional2}
            }
            
            with get_db_connection() as db:
                if db is None:
                    flash("Database connection failed. Please try again later.", "error")
                    return redirect(url_for("home"))
                
                db.games.insert_one(game)
            
            flash(f"Game '{name}' has been added successfully.", "success")
            return redirect(url_for("home"))
        except Exception as e:
            logger.error(f"Error in add_game: {str(e)}")
            flash(f"An error occurred while adding the game: {str(e)}", "error")
            return redirect(url_for("home"))

@app.route("/remove_game", methods=["POST"])
def remove_game():
    try:
        game_id = request.form.get("game_id")
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return redirect(url_for("home"))
                
            game = db.games.find_one({"_id": ObjectId(game_id)})
            if game:
                affected_users = []
                
                for comment in game.get("all_comments", []):
                    username = comment.get("user")
                    if username:
                        user = db.users.find_one({"name": username})
                        if user:
                            affected_users.append(user["_id"])
                
                for user_id in affected_users:
                    user = db.users.find_one({"_id": user_id})
                    if user:
                        for comment in user.get("comments", []):
                            if comment.get("game") == game["name"]:
                                play_time = comment.get("play_time", 0)
                                
                                db.users.update_one(
                                    {"_id": user_id},
                                    {"$inc": {"total_play_time": -play_time}}
                                )
                                
                                db.users.update_one(
                                    {"_id": user_id},
                                    {"$pull": {"comments": {"game": game["name"]}}}
                                )
                                
                                if user.get("most_played") == game["name"]:
                                    update_most_played_game(str(user_id))
                                
                                if "rating" in comment:
                                    update_user_average_rating(str(user_id))
                                
                                break
                
                if game.get("photo") and not game["photo"].startswith("data:"):
                    try:
                        photo_path = os.path.join(app.root_path, game["photo"].lstrip("/"))
                        if os.path.exists(photo_path):
                            os.remove(photo_path)
                            logger.info(f"Deleted game image: {photo_path}")
                    except Exception as e:
                        logger.error(f"Error deleting game image: {str(e)}")
                
                db.games.delete_one({"_id": ObjectId(game_id)})
                
                flash(f"Game '{game['name']}' has been successfully deleted.", "success")
            else:
                flash("Game not found.", "error")

        referrer = request.referrer
        if referrer and 'users' in referrer:
            return redirect(url_for("users"))
        else:
            return redirect(url_for("home"))
    except Exception as e:
        logger.error(f"Error in remove_game: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("home"))

@app.route("/toggle_rating", methods=["POST"])
def toggle_rating():
    try:
        game_id = request.form.get("game_id")
        action = request.form.get("action")
        
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return redirect(url_for("home"))
                
            game = db.games.find_one({"_id": ObjectId(game_id)})
            if not game:
                flash("Game not found.", "error")
                return redirect(url_for("home"))
                
            if action == "enable":
                db.games.update_one(
                    {"_id": ObjectId(game_id)},
                    {"$set": {"rating_enable": True}}
                )
                flash(f"Ratings and comments have been enabled for '{game['name']}'.", "success")
            else:
                db.games.update_one(
                    {"_id": ObjectId(game_id)},
                    {"$set": {"rating_enable": False}}
                )
                flash(f"Ratings and comments have been disabled for '{game['name']}'.", "success")
        
        return redirect(url_for("home"))
    except Exception as e:
        logger.error(f"Error in toggle_rating: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("home"))

@app.route("/add_user", methods=["POST"])
def add_user():
    try:
        name = request.form.get("userName")
        gender = request.form.get("userGender")
        avatar_path = request.form.get("userAvatar")
        
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return redirect(url_for("home"))
                
            existing_user = db.users.find_one({"name": name})
            if existing_user:
                flash(f"Username '{name}' is already taken. Please choose another username.", "error")
                return redirect(url_for("home"))
                
            user = {
                "name": name,
                "gender": gender,
                "avatar": avatar_path,
                "total_play_time": 0,  
                "most_played": None,
                "avarage_of_rating": 0,
                "comments": [],
                "created_at": datetime.now()
            }
            db.users.insert_one(user)
            flash(f"User '{name}' has been added successfully.", "success")
        
        return redirect(url_for("home"))
    except Exception as e:
        logger.error(f"Error in add_user: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("home"))

@app.route("/remove_user", methods=["POST"])
def remove_user():
    try:
        user_id = request.form.get("user_id")
        
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return redirect(url_for("home"))
                
            user = db.users.find_one({"_id": ObjectId(user_id)})
            if user:
                affected_games = []
                
                user_total_play_time = user.get("total_play_time", 0)
                
                for comment in user.get("comments", []):
                    game_name = comment.get("game")
                    play_time = comment.get("play_time", 0)
                    
                    if game_name:
                        game = db.games.find_one({"name": game_name})
                        if game:
                            affected_games.append({
                                "id": game["_id"],
                                "name": game_name,
                                "play_time": play_time
                            })
                        
                        db.games.update_one(
                            {"name": game_name},
                            {"$pull": {"all_comments": {"user": user["name"]}}}
                        )
                
                db.users.delete_one({"_id": ObjectId(user_id)})
                
                for game_info in affected_games:
                    db.games.update_one(
                        {"_id": game_info["id"]},
                        {"$inc": {"play_time": -game_info["play_time"]}}
                    )
                    
                    update_game_rating(game_info["id"])
                    
                    logger.info(f"Updated game '{game_info['name']}' stats after user removal")
                
                if session.get("user_id") == user_id:
                    session.clear()
                    flash("Your account has been deleted.", "success")
                else:
                    flash(f"User '{user['name']}' has been deleted.", "success")
        
        return redirect(url_for("home"))
    except Exception as e:
        logger.error(f"Error in remove_user: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("home"))

@app.route("/login_as_user", methods=["POST"])
def login_as_user():
    try:
        user_id = request.form.get("user_id")
        
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return redirect(url_for("home"))
                
            user = db.users.find_one({"_id": ObjectId(user_id)})
            if user:
                session["user_id"] = str(user_id)
                session["user_name"] = user.get("name")
                session["avatar"] = user.get("avatar")
                
                flash(f"Logged in as {user.get('name')}", "success")
            else:
                flash("User not found", "error")
        
        return redirect(url_for("user_page"))
    except Exception as e:
        logger.error(f"Error in login_as_user: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("home"))

@app.route("/logout")
def logout():
    try:
        session.pop("user_id", None)
        session.pop("user_name", None)
        session.pop("avatar", None)
        flash("You have been logged out", "success")
        return redirect(url_for("home"))
    except Exception as e:
        logger.error(f"Error in logout: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("home"))

@app.route("/user_page")
def user_page():
    try:
        if "user_id" not in session:
            flash("You need to be logged in to view this page", "error")
            return redirect(url_for("home"))
        
        user_id = session["user_id"]
        
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return redirect(url_for("home"))
                
            user = db.users.find_one({"_id": ObjectId(user_id)})
            
            if not user:
                session.pop("user_id", None)
                session.pop("user_name", None)
                session.pop("avatar", None)
                flash("User account not found", "error")
                return redirect(url_for("home"))
            
            games = list(db.games.find())
            user_games = []
            
            for game in games:
                user_comments = [comment for comment in user.get("comments", []) if comment["game"] == game["name"]]
                user_play_time = sum(comment.get("play_time", 0) for comment in user_comments) if user_comments else 0
                
                game["user_play_time"] = user_play_time
                
                if user_play_time > 0:
                    game_copy = game.copy()
                    
                    user_rating = next((comment.get("rating", None) for comment in user_comments if "rating" in comment), None)
                    game_copy["user_rating"] = user_rating
                    
                    user_comment_text = next((comment.get("text", "") for comment in user_comments), "")
                    game_copy["user_comment"] = user_comment_text
                    
                    user_games.append(game_copy)
        
        return render_template("user_page.html", user=user, games=games, user_games=user_games)
    except Exception as e:
        logger.error(f"Error in user_page: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("home"))

@app.route("/play_game", methods=["POST"])
def play_game():
    try:
        if "user_id" not in session:
            flash("You need to be logged in to play games", "error")
            return redirect(url_for("home"))
        
        game_id = request.form.get("game_id")
        play_time = int(request.form.get("play_time", 0))
        
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return redirect(url_for("home"))
                
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
            
            update_most_played_game(session["user_id"])
            
            flash(f"You played {game['name']} for {play_time} hours", "success")
            
            referrer = request.referrer
            if referrer and 'games' in referrer:
                return redirect(url_for("games"))
            else:
                return redirect(url_for("user_page"))
    except Exception as e:
        logger.error(f"Error in play_game: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("user_page"))

@app.route("/rate_game", methods=["POST"])
def rate_game():
    try:
        if "user_id" not in session:
            flash("You need to be logged in to rate games", "error")
            return redirect(url_for("home"))
        
        game_id = request.form.get("game_id")
        rating = int(request.form.get("rating", 0))
        
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return redirect(url_for("home"))
                
            user = db.users.find_one({"_id": ObjectId(session["user_id"])})
            game = db.games.find_one({"_id": ObjectId(game_id)})
            
            if not user or not game:
                flash("User or Game not found", "error")
                return redirect(url_for("games"))
                
            if not game.get("rating_enable", True):
                flash("Ratings are disabled for this game", "error")
                return redirect(url_for("games"))
            
            user_comment = None
            for comment in user.get("comments", []):
                if comment.get("game") == game["name"]:
                    user_comment = comment
                    break
                    
            if not user_comment or user_comment.get("play_time", 0) < 1:
                flash("You need to play the game for at least 1 hour before rating it.", "error")
                return redirect(url_for("games"))
                
            db.users.update_one(
                {"_id": ObjectId(session["user_id"]), "comments.game": game["name"]},
                {"$set": {"comments.$.rating": rating}}
            )
            
            update_user_average_rating(session["user_id"])
            update_game_rating(game["_id"])
            
            flash(f"You rated {game['name']} {rating}/5 stars.", "success")
            
            referrer = request.referrer
            if referrer and 'games' in referrer:
                return redirect(url_for("games"))
            else:
                return redirect(url_for("user_page"))
    except Exception as e:
        logger.error(f"Error in rate_game: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("games"))

@app.route("/comment_game", methods=["POST"])
def comment_game():
    try:
        if "user_id" not in session:
            flash("You need to be logged in to comment on games", "error")
            return redirect(url_for("home"))
            
        game_id = request.form.get("game_id")
        comment_text = request.form.get("comment_text", "").strip()
        
        with get_db_connection() as db:
            if db is None:
                flash("Database connection failed. Please try again later.", "error")
                return redirect(url_for("home"))
                
            user = db.users.find_one({"_id": ObjectId(session["user_id"])})
            game = db.games.find_one({"_id": ObjectId(game_id)})
            
            if not user or not game:
                flash("User or Game not found", "error")
                return redirect(url_for("games"))
                
            if not game.get("rating_enable", True):
                flash("Comments are disabled for this game", "error")
                return redirect(url_for("games"))
                
            user_comment = None
            for comment in user.get("comments", []):
                if comment.get("game") == game["name"]:
                    user_comment = comment
                    break
                    
            if not user_comment or user_comment.get("play_time", 0) < 1:
                flash("You need to play the game for at least 1 hour before commenting on it.", "error")
                return redirect(url_for("games"))
                
            db.users.update_one(
                {"_id": ObjectId(session["user_id"]), "comments.game": game["name"]},
                {"$set": {"comments.$.text": comment_text}}
            )
            
            existing_comment = False
            for comment in game.get("all_comments", []):
                if comment.get("user") == user["name"]:
                    existing_comment = True
                    db.games.update_one(
                        {"_id": ObjectId(game_id), "all_comments.user": user["name"]},
                        {"$set": {
                            "all_comments.$.text": comment_text,
                            "all_comments.$.play_time": user_comment["play_time"]
                        }}
                    )
                    break
                    
            if not existing_comment:
                db.games.update_one(
                    {"_id": ObjectId(game_id)},
                    {"$push": {"all_comments": {
                        "user": user["name"],
                        "text": comment_text,
                        "play_time": user_comment["play_time"]
                    }}}
                )
                
            flash(f"Your comment on {game['name']} has been saved.", "success")
            
            referrer = request.referrer
            if referrer and 'games' in referrer:
                return redirect(url_for("games"))
            else:
                return redirect(url_for("user_page"))
    except Exception as e:
        logger.error(f"Error in comment_game: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("user_page"))

def update_most_played_game(user_id):
    try:
        with get_db_connection() as db:
            if db is None:
                logger.error("Database connection failed in update_most_played_game.")
                return
                
            user = db.users.find_one({"_id": ObjectId(user_id)})
            
            if not user:
                return
            
            if not user.get("comments") or len(user["comments"]) == 0:
                db.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": {"most_played": None}}
                )
                return
            
            most_commented_game = max(user["comments"], key=lambda x: x.get("play_time", 0))
            most_played_game = most_commented_game.get("game")
            
            if most_commented_game.get("play_time", 0) == 0:
                db.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": {"most_played": None}}
                )
            else:
                db.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": {"most_played": most_played_game}}
                )
    except Exception as e:
        logger.error(f"Most played game update error: {str(e)}")

def update_user_average_rating(user_id):
    try:
        with get_db_connection() as db:
            if db is None:
                logger.error("Database connection failed in update_user_average_rating.")
                return
                
            user = db.users.find_one({"_id": ObjectId(user_id)})
            
            if not user:
                return
            
            rated_comments = [comment for comment in user.get("comments", []) if "rating" in comment]
            
            if not rated_comments:
                db.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": {"avarage_of_rating": 0}}
                )
                return
            
            avg_rating = sum(comment["rating"] for comment in rated_comments) / len(rated_comments)
            
            db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"avarage_of_rating": round(avg_rating, 1)}}
            )
    except Exception as e:
        logger.error(f"User average rating update error: {str(e)}")

def update_game_rating(game_id):
    try:
        with get_db_connection() as db:
            if db is None:
                logger.error("Database connection failed in update_game_rating.")
                return
                
            game = db.games.find_one({"_id": ObjectId(game_id)})
            if not game:
                logger.error(f"Game with ID {game_id} not found.")
                return
                
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
            
            if total_play_time <= 0:
                db.games.update_one(
                    {"_id": ObjectId(game_id)},
                    {"$set": {"rating": 0}}
                )
                return
            
            weighted_rating = total_weighted_rating / total_play_time
            
            db.games.update_one(
                {"_id": ObjectId(game_id)},
                {"$set": {"rating": round(weighted_rating, 1)}}
            )
    except Exception as e:
        logger.error(f"Game rating update error: {str(e)}")

@app.route("/debug_user")
def debug_user():
    try:
        if "user_id" not in session:
            return "No user logged in"
        
        user_id = session["user_id"]
        
        with get_db_connection() as db:
            if db is None:
                return "Database connection failed"
            
            user = db.users.find_one({"_id": ObjectId(user_id)})
            
            if not user:
                return "User not found"
            
            comments = user.get("comments", [])
            
            result = {
                "user_name": user["name"],
                "total_play_time": user["total_play_time"],
                "comments": comments
            }
            
            return str(result)
    except Exception as e:
        logger.error(f"Error in debug_user: {str(e)}")
        return f"Error: {str(e)}"

def migrate_user_avatars():
    try:
        logger.info("Checking for users without avatars or needing avatar updates...")
        
        with get_db_connection() as db:
            if db is None:
                logger.error("Database connection failed in migrate_user_avatars.")
                return
            
            users_without_proper_avatar = list(db.users.find({
                "$or": [
                    {"avatar": {"$exists": False}},
                    {"avatar": {"$in": ["/static/img/Man.png", "/static/img/Woman.png"]}}
                ]
            }))
            
            if not users_without_proper_avatar:
                logger.info("All users have up-to-date avatars. No migration needed.")
                return
                
            logger.info(f"Found {len(users_without_proper_avatar)} users needing avatar updates. Migrating...")
            
            for user in users_without_proper_avatar:
                
                if "gender" not in user:
                    user["gender"] = "male"
                
                if user["gender"] == "female":
                    avatar = "/static/img/Woman/image (10).png"
                else:
                    avatar = "/static/img/Man/image (11).png"
                
                if "avatar" in user and not user["avatar"].endswith(("Man.png", "Woman.png")):
                    avatar = user["avatar"]
                
                db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {
                        "avatar": avatar,
                        "gender": user["gender"]
                    }}
                )
                logger.info(f"Updated user: {user.get('name', 'Unknown')} with avatar: {avatar}")
            
            logger.info("Avatar migration completed successfully!")
    except Exception as e:
        logger.error(f"Error during avatar migration: {str(e)}")

def migrate_user_created_at():
    try:
        logger.info("Checking for users without created_at field...")
        
        with get_db_connection() as db:
            if db is None:
                logger.error("Database connection failed in migrate_user_created_at.")
                return
                
            users_without_date = list(db.users.find({"created_at": {"$exists": False}}))
            
            if not users_without_date:
                logger.info("All users have created_at field. No migration needed.")
                return
                
            logger.info(f"Found {len(users_without_date)} users without created_at. Migrating...")
            
            for user in users_without_date:
                db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"created_at": datetime.now()}}
                )
                logger.info(f"Updated user: {user.get('name', 'Unknown')} with current date")
            
            logger.info("Date migration completed successfully!")
    except Exception as e:
        logger.error(f"Error during date migration: {str(e)}")

try:
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        logger.info(f"Created upload directory: {UPLOAD_FOLDER}")
except Exception as e:
    logger.error(f"Could not create upload directory: {str(e)}")

if __name__ == "__main__":
    try:
        migrate_user_avatars()
        migrate_user_created_at()
    except Exception as e:
        logger.error(f"Error during migration: {str(e)}")
    
    app.run(host="0.0.0.0", port=8080, debug=True)