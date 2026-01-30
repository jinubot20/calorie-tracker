from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Union
import database
import ai_engine
import auth
import os
import shutil
import json
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='app_debug.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

# Singapore Time Offset (UTC+8)
def get_sg_time():
    return datetime.utcnow() + timedelta(hours=8)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB
database.init_db()

# Models
class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    telegram_id: Union[str, None] = None

class Token(BaseModel):
    access_token: str
    token_type: str

# Auth Routes
@app.post("/auth/register", response_model=Token)
def register(user_data: UserCreate, db: Session = Depends(database.get_db)):
    try:
        logger.debug(f"Registering user: {user_data.email}")
        db_user = db.query(database.User).filter(database.User.email == user_data.email).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_pwd = auth.get_password_hash(user_data.password)
        logger.debug(f"DEBUG HASH GENERATED: {hashed_pwd}")
        new_user = database.User(
            email=user_data.email,
            hashed_password=hashed_pwd,
            name=user_data.name,
            telegram_id=user_data.telegram_id
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        access_token = auth.create_access_token(data={"sub": new_user.email})
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        logger.exception("Error during registration")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    try:
        user = db.query(database.User).filter(database.User.email == form_data.username).first()
        if not user or not auth.verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token = auth.create_access_token(data={"sub": user.email})
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        logger.exception("Error during login")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/me")
def read_users_me(current_user: database.User = Depends(auth.get_current_user)):
    return {
        "email": current_user.email,
        "name": current_user.name,
        "daily_target": current_user.daily_target,
        "telegram_id": current_user.telegram_id
    }

@app.post("/users/link-telegram")
def link_telegram(telegram_id: str, current_user: database.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    current_user.telegram_id = telegram_id
    db.commit()
    return {"status": "success", "linked": telegram_id}

# Fuel Share Routes
import uuid

@app.get("/share/status")
def get_share_status(current_user: database.User = Depends(auth.get_current_user)):
    return {
        "enabled": bool(current_user.share_enabled),
        "token": current_user.share_token
    }

@app.post("/share/toggle")
def toggle_share(enabled: bool, db: Session = Depends(database.get_db), current_user: database.User = Depends(auth.get_current_user)):
    current_user.share_enabled = 1 if enabled else 0
    if enabled and not current_user.share_token:
        current_user.share_token = str(uuid.uuid4())
    db.commit()
    return {"enabled": bool(current_user.share_enabled), "token": current_user.share_token}

@app.post("/share/reset")
def reset_share_token(db: Session = Depends(database.get_db), current_user: database.User = Depends(auth.get_current_user)):
    current_user.share_token = str(uuid.uuid4())
    db.commit()
    return {"token": current_user.share_token}

@app.get("/public/stats/{token}")
def get_public_stats(token: str, db: Session = Depends(database.get_db)):
    user = db.query(database.User).filter(database.User.share_token == token, database.User.share_enabled == 1).first()
    if not user:
        raise HTTPException(status_code=404, detail="Share link not found or disabled")
    
    # Reuse the logic from get_stats but for the shared user
    now_sg = get_sg_time()
    today_sg = now_sg.date()
    meals_today = [m for m in user.meals if m.timestamp.date() == today_sg]
    
    # For public view, we don't regenerate summary to avoid quota drain, 
    # we just show the latest one if it exists
    daily_summary = user.cached_summary if user.summary_date == today_sg.isoformat() else "No summary available."

    # Group meals by day
    from itertools import groupby
    sorted_meals = sorted(user.meals, key=lambda x: x.timestamp, reverse=True)
    grouped_history = []
    
    # Fetch all daily feedbacks and summaries for this user
    all_feedbacks = db.query(database.DailyFeedback).filter(database.DailyFeedback.user_id == user.id).all()
    feedback_map = {f.date: f.content for f in all_feedbacks}
    
    all_summaries = db.query(database.DailySummary).filter(database.DailySummary.user_id == user.id).all()
    summary_map = {s.date: s.content for s in all_summaries}
    
    for date, items in groupby(sorted_meals, key=lambda x: x.timestamp.date()):
        date_str = date.isoformat()
        meals_list = list(items)
        grouped_history.append({
            "date": date_str,
            "display_date": "Today" if date == today_sg else date.strftime("%d %b, %Y"),
            "trainer_feedback": feedback_map.get(date_str),
            "ai_summary": summary_map.get(date_str) or (user.cached_summary if date_str == user.summary_date else None),
            "totals": {
                "calories": sum(m.calories for m in meals_list),
                "protein": sum(m.protein for m in meals_list),
                "carbs": sum(m.carbs for m in meals_list),
                "fat": sum(m.fat for m in meals_list)
            },
            "meals": [
                {
                    "id": m.id, 
                    "food": m.food_name, 
                    "meal_type": m.meal_type,
                    "description": m.description,
                    "calories": m.calories, 
                    "protein": m.protein,
                    "carbs": m.carbs,
                    "fat": m.fat,
                    "items": json.loads(m.items_json) if m.items_json else [],
                    "trainer_notes": m.trainer_notes,
                    "time": m.timestamp.isoformat(),
                    "images": [f"/uploads/{os.path.basename(p)}" for p in json.loads(m.image_paths)] if m.image_paths and m.image_paths.startswith('[') else []
                }
                for m in meals_list
            ]
        })

    return {
        "user_name": user.name,
        "target": user.daily_target,
        "consumed": sum(m.calories for m in meals_today),
        "protein": sum(m.protein for m in meals_today),
        "carbs": sum(m.carbs for m in meals_today),
        "fat": sum(m.fat for m in meals_today),
        "daily_summary": daily_summary,
        "grouped_history": grouped_history[:7]
    }

@app.post("/public/daily-feedback/{token}/{date}")
def update_daily_feedback(token: str, date: str, note: Optional[str] = Form(None), db: Session = Depends(database.get_db)):
    user = db.query(database.User).filter(database.User.share_token == token, database.User.share_enabled == 1).first()
    if not user:
        raise HTTPException(status_code=404, detail="Unauthorized")
    
    feedback = db.query(database.DailyFeedback).filter(database.DailyFeedback.user_id == user.id, database.DailyFeedback.date == date).first()
    
    if not note or not note.strip():
        # If the note is empty or just whitespace, delete the feedback entry
        if feedback:
            db.delete(feedback)
    else:
        if feedback:
            feedback.content = note
        else:
            feedback = database.DailyFeedback(user_id=user.id, date=date, content=note)
            db.add(feedback)
    
    db.commit()
    return {"status": "success"}

# API Routes
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status, Form
...
from typing import Optional, Union, List
...
@app.post("/upload-meal-internal/{email}")
async def upload_meal_internal(
    email: str,
    files: List[UploadFile] = File(None),
    description: Optional[str] = Form(None),
    portion: float = Form(1.0),
    meal_type: Optional[str] = Form(None),
    db: Session = Depends(database.get_db)
):
    """Internal endpoint for Telegram Bot to upload meals."""
    try:
        user = db.query(database.User).filter(database.User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        saved_paths = []
        if files:
            os.makedirs("uploads", exist_ok=True)
            for file in files:
                file_path = f"uploads/{datetime.now().timestamp()}_{file.filename}"
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                saved_paths.append(file_path)
        
        food_name, cals, p, c, f, items = ai_engine.estimate_calories(saved_paths if saved_paths else None, description)
        
        # We now trust the AI for portion sizing within its calculation
        calories = int(cals)
        protein = int(p)
        carbs = int(c)
        fat = int(f)

        new_meal = database.Meal(
            user_id=user.id,
            food_name=food_name,
            meal_type=meal_type,
            description=description,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            image_paths=json.dumps(saved_paths),
            items_json=json.dumps(items),
            timestamp=get_sg_time()
        )
        db.add(new_meal)
        
        # Clear the persistent summary for today so it regenerates with the new data
        today_str = get_sg_time().date().isoformat()
        db.query(database.DailySummary).filter(
            database.DailySummary.user_id == user.id,
            database.DailySummary.date == today_str
        ).delete()
        
        user.cached_summary = None
        db.commit()
        
        today_sg = get_sg_time().date()
        return {
            "food": food_name,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "items": items,
            "total_today": sum(m.calories for m in user.meals if m.timestamp.date() == today_sg)
        }
    except Exception as e:
        if str(e) == "AI_QUOTA_REACHED":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="AI Quota limit reached. This is an external API limitation, not an app error. Please try again in a few minutes."
            )
        logger.exception(f"Error during internal meal upload for {email}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-meal")
async def upload_meal(
    files: List[UploadFile] = File(None), 
    description: Optional[str] = Form(None),
    portion: float = Form(1.0),
    meal_type: Optional[str] = Form(None),
    db: Session = Depends(database.get_db),
    current_user: database.User = Depends(auth.get_current_user)
):
    try:
        saved_paths = []
        if files:
            os.makedirs("uploads", exist_ok=True)
            for file in files:
                file_path = f"uploads/{datetime.now().timestamp()}_{file.filename}"
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                saved_paths.append(file_path)
        
        food_name, cals, p, c, f, items = ai_engine.estimate_calories(saved_paths if saved_paths else None, description)
        
        calories = int(cals)
        protein = int(p)
        carbs = int(c)
        fat = int(f)

        new_meal = database.Meal(
            user_id=current_user.id,
            food_name=food_name,
            meal_type=meal_type,
            description=description,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            image_paths=json.dumps(saved_paths),
            items_json=json.dumps(items),
            timestamp=get_sg_time()
        )
        db.add(new_meal)
        
        # Clear the persistent summary for today so it regenerates with the new data
        today_str = get_sg_time().date().isoformat()
        db.query(database.DailySummary).filter(
            database.DailySummary.user_id == current_user.id,
            database.DailySummary.date == today_str
        ).delete()
        
        current_user.cached_summary = None 
        db.commit()
        
        today_sg = get_sg_time().date()
        return {
            "food": food_name,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "items": items,
            "total_today": sum(m.calories for m in current_user.meals if m.timestamp.date() == today_sg)
        }
    except Exception as e:
        if str(e) == "AI_QUOTA_REACHED":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="AI Quota limit reached. This is an external API limitation, not an app error. Please try again in a few minutes."
            )
        logger.exception(f"Error during meal upload for {current_user.email}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
def get_stats(db: Session = Depends(database.get_db), current_user: database.User = Depends(auth.get_current_user)):
    now_sg = get_sg_time()
    today_sg = now_sg.date()
    today_str = today_sg.isoformat()
    meals_today = [m for m in current_user.meals if m.timestamp.date() == today_sg]
    
    # Calculate 7-day trend
    history_trend = []
    for i in range(6, -1, -1):
        day = today_sg - timedelta(days=i)
        day_total = sum(m.calories for m in current_user.meals if m.timestamp.date() == day)
        history_trend.append({
            "day": day.strftime("%a"),
            "amount": day_total
        })

    # Group meals by day
    from itertools import groupby
    sorted_meals = sorted(current_user.meals, key=lambda x: x.timestamp, reverse=True)
    grouped_history = []
    
    # Fetch all daily feedbacks and summaries for this user to avoid multiple queries
    all_feedbacks = db.query(database.DailyFeedback).filter(database.DailyFeedback.user_id == current_user.id).all()
    feedback_map = {f.date: f.content for f in all_feedbacks}
    
    all_summaries = db.query(database.DailySummary).filter(database.DailySummary.user_id == current_user.id).all()
    summary_map = {s.date: s.content for s in all_summaries}
    
    # 1. Get/Generate Today's AI Summary
    today_summary = summary_map.get(today_str)
    
    if not meals_today:
        today_summary = "Log your first meal to get insights!"
    elif not today_summary:
        # Try to generate
        generated = ai_engine.generate_daily_summary(meals_today, current_user.daily_target)
        if generated:
            new_summary = database.DailySummary(user_id=current_user.id, date=today_str, content=generated)
            db.add(new_summary)
            db.commit()
            today_summary = generated
        else:
            today_summary = "Generating your daily insights (AI is a bit busy)..."

    for date, items in groupby(sorted_meals, key=lambda x: x.timestamp.date()):
        date_str = date.isoformat()
        meals_list = list(items)
        
        grouped_history.append({
            "date": date_str,
            "display_date": "Today" if date == today_sg else date.strftime("%d %b, %Y"),
            "trainer_feedback": feedback_map.get(date_str),
            "ai_summary": summary_map.get(date_str),
            "totals": {
                "calories": sum(m.calories for m in meals_list),
                "protein": sum(m.protein for m in meals_list),
                "carbs": sum(m.carbs for m in meals_list),
                "fat": sum(m.fat for m in meals_list)
            },
            "meals": [
                {
                    "id": m.id, 
                    "food": m.food_name, 
                    "meal_type": m.meal_type,
                    "description": m.description,
                    "calories": m.calories, 
                    "protein": m.protein,
                    "carbs": m.carbs,
                    "fat": m.fat,
                    "items": json.loads(m.items_json) if m.items_json else [],
                    "time": m.timestamp.isoformat(),
                    "images": [f"/uploads/{os.path.basename(p)}" for p in json.loads(m.image_paths)] if m.image_paths and m.image_paths.startswith('[') else []
                }
                for m in meals_list
            ]
        })

    return {
        "target": current_user.daily_target,
        "consumed": sum(m.calories for m in meals_today),
        "protein": sum(m.protein for m in meals_today),
        "carbs": sum(m.carbs for m in meals_today),
        "fat": sum(m.fat for m in meals_today),
        "daily_summary": today_summary,
        "grouped_history": grouped_history[:7], # Last 7 days
        "trend": history_trend
    }

@app.delete("/meal/{meal_id}")
def delete_meal(
    meal_id: int, 
    db: Session = Depends(database.get_db),
    current_user: database.User = Depends(auth.get_current_user)
):
    meal = db.query(database.Meal).filter(
        database.Meal.id == meal_id, 
        database.Meal.user_id == current_user.id
    ).first()
    
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    
    # Identify the date of the meal to clear the daily summary
    meal_date = meal.timestamp.date().isoformat()
    
    db.delete(meal)
    
    # Clear the new persistent summary for that specific date
    db.query(database.DailySummary).filter(
        database.DailySummary.user_id == current_user.id,
        database.DailySummary.date == meal_date
    ).delete()
    
    current_user.cached_summary = None
    db.commit()
    return {"status": "success"}

@app.post("/settings")
def update_settings(
    daily_target: Optional[int] = None, 
    password: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: database.User = Depends(auth.get_current_user)
):
    if daily_target is not None:
        current_user.daily_target = daily_target
    if password is not None:
        current_user.hashed_password = auth.get_password_hash(password)
    db.commit()
    return {"status": "success"}

# Custom StaticFiles to add Cache-Control headers
class CachedStaticFiles(StaticFiles):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

@app.get("/admin/stats")
def get_admin_stats(db: Session = Depends(database.get_db), current_user: database.User = Depends(auth.get_current_user)):
    if current_user.email != "jhbong84@gmail.com":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    total_users = db.query(database.User).count()
    total_meals = db.query(database.Meal).count()
    
    # Today's stats
    today = get_sg_time().date()
    meals_today = db.query(database.Meal).filter(database.Meal.timestamp >= today).count()
    
    # User list with last meal
    users = db.query(database.User).all()
    user_list = []
    for u in users:
        last_meal = db.query(database.Meal).filter(database.Meal.user_id == u.id).order_by(database.Meal.timestamp.desc()).first()
        user_list.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "meal_count": len(u.meals),
            "last_active": last_meal.timestamp.isoformat() if last_meal else "Never"
        })
        
    # Recent logs (last 20)
    recent_meals = db.query(database.Meal).order_by(database.Meal.timestamp.desc()).limit(20).all()
    meal_logs = [{
        "id": m.id,
        "user": m.owner.name,
        "food": m.food_name,
        "calories": m.calories,
        "time": m.timestamp.isoformat(),
        "has_image": bool(m.image_paths and m.image_paths != "[]")
    } for m in recent_meals]

    return {
        "total_users": total_users,
        "total_meals": total_meals,
        "meals_today": meals_today,
        "users": user_list,
        "recent_logs": meal_logs
    }

# Serve Uploads
app.mount("/uploads", CachedStaticFiles(directory="uploads"), name="uploads")

# Serve Frontend
frontend_path = os.path.join(os.getcwd(), "../frontend/dist")
if os.path.exists(frontend_path):
    # Mount specific assets
    app.mount("/assets", CachedStaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")

    # Serve root-level static files (logo, manifest, etc.)
    @app.get("/logo.png")
    async def serve_logo():
        return FileResponse(
            os.path.join(frontend_path, "logo.png"),
            headers={"Cache-Control": "public, max-age=86400"}
        )

    @app.get("/manifest.json")
    async def serve_manifest():
        return FileResponse(os.path.join(frontend_path, "manifest.json"))

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Serve index.html for all non-API routes to handle SPA routing
        # Check if it's an API route first
        api_prefixes = ["auth/", "upload-meal", "stats", "meal/", "settings", "users/"]
        if any(full_path.startswith(p) for p in api_prefixes):
            raise HTTPException(status_code=404)
        
        return FileResponse(os.path.join(frontend_path, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
