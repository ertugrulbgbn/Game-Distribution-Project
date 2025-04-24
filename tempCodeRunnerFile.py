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