from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import contextlib
import uuid

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Configure upload folder
UPLOAD_FOLDER = 'static/uploads/game_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

@app.route("/users")
def users():
    """
    New route to display all users in the system
    This page will be accessible from the navigation bar
    """
    with get_db_connection() as db:
        users = list(db.users.find())
    return render_template("users.html", users=users)

@app.route("/games")
def games():
    search = request.args.get('search', '')
    genre_filter = request.args.get('genre', '')
    sort_by = request.args.get('sort', 'rating')
    
    with get_db_connection() as db:
        # Build the query
        query = {}
        
        if search:
            query['name'] = {'$regex': search, '$options': 'i'}  # Case-insensitive search
            
        if genre_filter:
            query['genres'] = genre_filter
        
        # Get all games based on the query
        games_cursor = db.games.find(query)
        
        # Sort the results
        if sort_by == 'rating':
            games = list(games_cursor.sort('rating', -1))  # Descending order
        elif sort_by == 'play_time':
            games = list(games_cursor.sort('play_time', -1))
        elif sort_by == 'name':
            games = list(games_cursor.sort('name', 1))  # Ascending order
        elif sort_by == 'comments':
            # This is a bit more complex - we need to sort by the length of comments array
            games = list(games_cursor)
            games.sort(key=lambda x: len(x.get('all_comments', [])) if x.get('all_comments') else 0, reverse=True)
        else:
            games = list(games_cursor)
        
        # Get all available genres for the filter dropdown
        all_genres = set()
        for game in db.games.find({}, {'genres': 1}):
            for genre in game.get('genres', []):
                all_genres.add(genre)
        
        # Add user-specific data if logged in
        if 'user_id' in session:
            user = db.users.find_one({"_id": ObjectId(session["user_id"])})
            if user:
                for game in games:
                    # Find the user's comments for this game
                    user_comments = [comment for comment in user.get('comments', []) if comment.get('game') == game['name']]
                    if user_comments:
                        game['user_play_time'] = user_comments[0].get('play_time', 0)
                        game['user_rating'] = user_comments[0].get('rating')
                        game['user_comment'] = user_comments[0].get('text', '')
    
    return render_template('games.html', games=games, all_genres=sorted(all_genres))

@app.route("/add_game", methods=["POST"])
def add_game():
    if request.method == "POST":
        name = request.form.get("gameName")
        genres = [genre.strip() for genre in request.form.get("gameGenre").split(",")]
        optional1 = request.form.get("gameOptional1")
        optional2 = request.form.get("gameOptional2")
        
        # Handle image file upload
        photo_path = ""
        if 'gamePhoto' in request.files:
            file = request.files['gamePhoto']
            if file and file.filename != '' and allowed_file(file.filename):
                # Generate unique filename to avoid overwrites
                filename = secure_filename(file.filename)
                file_extension = filename.rsplit('.', 1)[1].lower()
                unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
                
                # Save the file
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                
                # Save the relative path to the database
                photo_path = f"/static/uploads/game_images/{unique_filename}"
            else:
                flash("Invalid image file. Please upload a valid image (PNG, JPG, JPEG, GIF).", "error")
                return redirect(url_for("home"))
        else:
            flash("Game image is required.", "error")
            return redirect(url_for("home"))
            
        game = {
            "name": name,
            "genres": genres,  
            "photo": photo_path,
            "play_time": 0,
            "all_comments": [], 
            "rating": 0,
            "rating_enable": True,  
            "optional_attributes": {"release_date": optional1, "developer": optional2}
        }
        
        with get_db_connection() as db:
            db.games.insert_one(game)
        
        flash(f"Game '{name}' has been added successfully.", "success")
        return redirect(url_for("home"))

@app.route("/remove_game", methods=["POST"])
def remove_game():
    game_id = request.form.get("game_id")
    with get_db_connection() as db:
        game = db.games.find_one({"_id": ObjectId(game_id)})
        if game:
            # Delete the game image file if it exists
            if game.get("photo") and game["photo"].startswith("/static/uploads/"):
                try:
                    file_path = os.path.join(app.root_path, game["photo"].lstrip("/"))
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    print(f"Error deleting file: {str(e)}")
            
            db.games.delete_one({"_id": ObjectId(game_id)})
            
            # Update any users who had this as their most played game
            db.users.update_many(
                {"most_played": game["name"]},
                {"$set": {"most_played": None}} 
            )
            flash(f"Game '{game['name']}' has been successfully deleted.", "success")
        else:
            flash("Game not found.", "error")

    # Return to the page that initiated the request
    referrer = request.referrer
    if referrer and url_for('users') in referrer:
        return redirect(url_for("users"))
    else:
        return redirect(url_for("home"))

@app.route("/toggle_rating", methods=["POST"])
def toggle_rating():
    game_id = request.form.get("game_id")
    action = request.form.get("action")
    
    with get_db_connection() as db:
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

@app.route("/add_user", methods=["POST"])
def add_user():
    name = request.form.get("userName")
    gender = request.form.get("userGender")
    avatar_path = request.form.get("userAvatar")
    
    with get_db_connection() as db:
        # Check if username already exists
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
            "comments": []
        }
        db.users.insert_one(user)
        flash(f"User '{name}' has been added successfully.", "success")
    
    # Return to the page that initiated the request
    referrer = request.referrer
    if referrer and url_for('users') in referrer:
        return redirect(url_for("users"))
    else:
        return redirect(url_for("home"))

@app.route("/remove_user", methods=["POST"])
def remove_user():
    user_id = request.form.get("user_id")
    with get_db_connection() as db:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if user:
            # Remove user's comments from all games
            for comment in user.get("comments", []):
                db.games.update_one(
                    {"name": comment["game"]},
                    {"$pull": {"all_comments": {"user": user["name"]}}}
                )
            
            # Delete the user
            db.users.delete_one({"_id": ObjectId(user_id)})
            
            # Clear session if the deleted user is the currently logged in user
            if session.get("user_id") == user_id:
                session.clear()
                flash("Your account has been deleted.", "success")
            else:
                flash(f"User '{user['name']}' has been deleted.", "success")
    
    # Return to the page that initiated the request
    referrer = request.referrer
    if referrer and url_for('users') in referrer:
        return redirect(url_for("users"))
    else:
        return redirect(url_for("home"))

@app.route("/login_as_user", methods=["POST"])
def login_as_user():
    user_id = request.form.get("user_id")
    
    with get_db_connection() as db:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if user:
            session["user_id"] = str(user_id)
            session["user_name"] = user.get("name")
            session["avatar"] = user.get("avatar")
            
            flash(f"Logged in as {user.get('name')}", "success")
        else:
            flash("User not found", "error")
    
    return redirect(url_for("user_page"))

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("avatar", None)
    flash("You have been logged out", "success")
    return redirect(url_for("home"))

@app.route("/user_page")
def user_page():
    """
    Personal profile page for the logged-in user
    Only accessible when a user is logged in
    """
    if "user_id" not in session:
        flash("You need to be logged in to view this page", "error")
        return redirect(url_for("home"))
    
    user_id = session["user_id"]
    
    with get_db_connection() as db:
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
            
            if user_play_time > 0:
                game_copy = game.copy()
                game_copy["user_play_time"] = user_play_time
                
                # Get user's rating for this game
                user_rating = next((comment.get("rating", None) for comment in user_comments if "rating" in comment), None)
                game_copy["user_rating"] = user_rating
                
                # Get user's comment for this game
                user_comment_text = next((comment.get("text", "") for comment in user_comments), "")
                game_copy["user_comment"] = user_comment_text
                
                user_games.append(game_copy)
            
            game["user_play_time"] = user_play_time
    
    return render_template("user_page.html", user=user, games=games, user_games=user_games)

@app.route("/play_game", methods=["POST"])
def play_game():
    if "user_id" not in session:
        flash("You need to be logged in to play games", "error")
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
            
            # Update game play time
            db.games.update_one(
                {"_id": ObjectId(game_id)},
                {"$inc": {"play_time": play_time}}
            )# Update user total play time
            db.users.update_one(
                {"_id": ObjectId(session["user_id"])},
                {"$inc": {"total_play_time": play_time}}
            )
            
            # Update or create user comment for this game
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
            
            # Update the user's most played game
            update_most_played_game(session["user_id"])
            
            flash(f"You played {game['name']} for {play_time} hours", "success")
            return redirect(url_for("games"))
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("games"))

@app.route("/rate_game", methods=["POST"])
def rating_game():
    if "user_id" not in session:
        flash("You need to be logged in to rate games", "error")
        return redirect(url_for("home"))
    
    game_id = request.form.get("game_id")
    rating = int(request.form.get("rating", 0))
    
    with get_db_connection() as db:
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
        return redirect(url_for("games"))

@app.route("/comment_game", methods=["POST"])
def comment_game():
    if "user_id" not in session:
        flash("You need to be logged in to comment on games", "error")
        return redirect(url_for("home"))
        
    game_id = request.form.get("game_id")
    comment_text = request.form.get("comment_text", "").strip()
    
    with get_db_connection() as db:
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
            
        # Update user's comment
        db.users.update_one(
            {"_id": ObjectId(session["user_id"]), "comments.game": game["name"]},
            {"$set": {"comments.$.text": comment_text}}
        )
        
        # Check if user already has a comment in the game's comments
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
        return redirect(url_for("games"))

def update_most_played_game(user_id):
    try:
        with get_db_connection() as db:
            user = db.users.find_one({"_id": ObjectId(user_id)})
            
            if not user or not user.get("comments"):
                return
            
            if len(user["comments"]) > 0:
                most_commented_game = max(user["comments"], key=lambda x: x.get("play_time", 0))
                most_played_game = most_commented_game.get("game")
                
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
        return "No user logged in"
    
    user_id = session["user_id"]
    
    with get_db_connection() as db:
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

def migrate_user_avatars():
    """
    Script to add or update avatar field for existing users in the database
    This can be run manually or automatically when the app starts
    """
    print("Checking for users without avatars or needing avatar updates...")
    
    with get_db_connection() as db:
        # Find all users that don't have an avatar field or have an outdated avatar
        users_without_proper_avatar = list(db.users.find({
            "$or": [
                {"avatar": {"$exists": False}},
                {"avatar": {"$in": ["/static/img/Man.png", "/static/img/Woman.png"]}}
            ]
        }))
        
        if not users_without_proper_avatar:
            print("All users have up-to-date avatars. No migration needed.")
            return
            
        print(f"Found {len(users_without_proper_avatar)} users needing avatar updates. Migrating...")
        
        for user in users_without_proper_avatar:
            # Determine proper avatar based on gender
            if "gender" not in user:
                # Default to male if gender is not specified
                user["gender"] = "male"
            
            # Default avatars based on gender
            if user["gender"] == "female":
                avatar = "/static/img/Woman/image (10).png"
            else:
                avatar = "/static/img/Man/image (11).png"
            
            # If the user had a previous avatar and it's a custom one, keep it
            if "avatar" in user and not user["avatar"].endswith(("Man.png", "Woman.png")):
                avatar = user["avatar"]
            
            # Update the user with the avatar field
            db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {
                    "avatar": avatar,
                    "gender": user["gender"]
                }}
            )
            print(f"Updated user: {user.get('name', 'Unknown')} with avatar: {avatar}")
        
        print("Avatar migration completed successfully!")

# Run the migration when the app starts
if __name__ == "__main__":
    # Run the avatar migration
    try:
        migrate_user_avatars()
    except Exception as e:
        print(f"Error during avatar migration: {str(e)}")
        
    app.run(debug=True)